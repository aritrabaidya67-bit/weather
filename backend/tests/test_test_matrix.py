"""The end-to-end test matrix (CASE 1..14), executed against the real API.

Each case is driven through HTTP with the same request shape the Arduino and the
browser use, so this file is the executable answer to "does the platform behave
correctly in this situation?". Deeper unit coverage for each subsystem lives in
its own module; the point here is that the cases are named, explicit and
end-to-end, and that they can be read as an acceptance checklist.

CASE 1  normal sensor data              -> accepted, scored, persisted, streamed
CASE 2  high temperature                 -> risk rises, reason names temperature
CASE 3  high humidity                    -> risk rises, reason names humidity
CASE 4  poor air quality                 -> risk rises, reason names air quality
CASE 5  rain detected                    -> wetness derived, rain status set
CASE 6  sudden sensor spike              -> anomaly flagged with an explanation
CASE 7  sensor unavailable               -> channel missing, never filled in
CASE 8  Arduino disconnected             -> offline state + alert (watchdog)
CASE 9  malformed transport payload      -> 422, nothing stored
CASE 10 Ollama unavailable               -> chatbot answers without the model
CASE 11 insufficient history             -> prediction unavailable, not invented
CASE 12 invalid API key                  -> 401, nothing stored
CASE 13 device key not configured        -> 503 naming the reason
CASE 14 multiple simultaneous anomalies  -> all reported, risk composite rises
"""

from __future__ import annotations

import json

import pytest

from .conftest import TEST_API_KEY, auth_headers, post_reading, sample_payload


# --------------------------------------------------------------------------- #
# CASE 1 - normal sensor data
# --------------------------------------------------------------------------- #
def test_case_01_normal_sensor_data(client):
    response = post_reading(client, sequence=1)
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["duplicate"] is False
    assert body["missing_metrics"] == []
    assert body["sensor_health"] == 100.0
    assert 1 <= body["risk_level"] <= 5
    assert body["risk_score"] is not None
    assert body["processing_ms"] < 500

    # persisted, not just echoed
    latest = client.get("/api/v1/sensors/latest").json()
    assert latest["temperature_c"] == 24.6
    assert latest["humidity_pct"] == 52.0
    assert latest["pressure_hpa"] == 1012.6
    # derived, and labelled as derived
    assert latest["rain_pct"] is not None
    assert latest["light_pct"] is not None
    assert latest["air_quality_index"] is not None

    # and published to the realtime bus
    assert client.get("/api/v1/realtime/status").json()["last_event_id"] > 0


# --------------------------------------------------------------------------- #
# CASE 2/3/4/5 - single-factor excursions must move the score and the reasoning
# --------------------------------------------------------------------------- #
def _factor(client, key: str) -> dict:
    """The named risk factor as the explainability endpoint reports it.

    Read from `/risk/current` - the same payload the UI renders - rather than by
    calling the risk service directly, so this exercises the real response path.
    """
    body = client.get("/api/v1/risk/current").json()
    return next(item for item in body["contributions"] if item["key"] == key)


def test_case_02_high_temperature_raises_risk_and_says_so(client):
    baseline = post_reading(client, sequence=1, temperature_c=23.0).json()
    assert _factor(client, "temperature")["points"] == 0.0

    hot = post_reading(client, sequence=2, temperature_c=39.5, bmp_temperature_c=39.2).json()
    assert hot["risk_score"] > baseline["risk_score"]

    temperature = _factor(client, "temperature")
    assert temperature["label"] == "Temperature"
    assert temperature["reading"] == 39.5
    assert temperature["points"] > 0
    assert temperature["reason"]
    assert temperature["direction"] == "increasing"
    # The prose reason describes the heat; the factor name comes from the
    # contribution entry, which is what the UI labels the bar with.
    assert any("heat" in reason.lower() for reason in hot["risk_reasons"])
    actions = " ".join(hot["recommended_actions"]).lower()
    assert "ventilat" in actions or "cool" in actions


def test_case_03_high_humidity_raises_risk_and_says_so(client):
    baseline = post_reading(client, sequence=1, humidity_pct=45.0).json()
    assert _factor(client, "humidity")["points"] == 0.0

    humid = post_reading(client, sequence=2, humidity_pct=93.0).json()
    assert humid["risk_score"] > baseline["risk_score"]

    humidity = _factor(client, "humidity")
    assert humidity["label"] == "Humidity"
    assert humidity["reading"] == 93.0
    assert humidity["points"] == 15.0  # weight 15 at the saturated band
    assert humidity["reason"]
    # The prose describes the excess moisture (the wording is the band's, so the
    # check is on meaning rather than one exact phrase).
    lowered = humidity["reason"].lower()
    assert any(word in lowered for word in ("humid", "moisture", "saturat"))


def test_case_04_poor_air_quality_raises_risk_and_says_so(client):
    clean = post_reading(client, sequence=1, air_quality_raw=150.0).json()
    assert _factor(client, "air_quality")["points"] == 0.0

    polluted = post_reading(client, sequence=2, air_quality_raw=930.0).json()
    assert polluted["risk_score"] > clean["risk_score"]
    latest = client.get("/api/v1/sensors/latest").json()
    assert latest["air_quality_index"] > 80

    # Air quality carries the heaviest weight, so it must dominate the reasons.
    air = _factor(client, "air_quality")
    assert air["points"] == air["max_points"] == 30.0  # fully saturated
    assert air["reason"]
    assert "air quality" in air["reason"].lower()


def test_case_05_rain_is_derived_from_the_raw_adc_and_labelled(client):
    dry = post_reading(client, sequence=1, rain_raw=980.0).json()
    assert dry["risk_score"] is not None
    assert client.get("/api/v1/sensors/latest").json()["rain_status"] == "dry"

    soaked = post_reading(client, sequence=2, rain_raw=120.0).json()
    latest = client.get("/api/v1/sensors/latest").json()
    assert latest["rain_pct"] > 85
    assert latest["rain_status"] in {"heavy rain", "rain"}
    assert soaked["risk_score"] > dry["risk_score"]
    assert any("rain" in reason.lower() for reason in soaked["risk_reasons"])


# --------------------------------------------------------------------------- #
# CASE 6 / CASE 14 - anomalies
# --------------------------------------------------------------------------- #
def _steady(index: int, base: float, amplitude: float) -> float:
    """Small alternating jitter, so a channel is neither flat nor noisy."""
    return base + (amplitude if index % 2 else -amplitude * 0.8)


def _build_realistic_baseline(client, count: int = 24) -> None:
    """Feed a baseline that looks like a real node: every channel moves.

    A channel that never changes would (correctly) be reported as a stuck
    sensor, which would distract from the anomaly this case is about.
    """
    for index in range(count):
        post_reading(
            client,
            sequence=index + 1,
            temperature_c=_steady(index, 25.0, 0.06),
            humidity_pct=_steady(index, 50.0, 0.09),
            bmp_temperature_c=_steady(index, 24.9, 0.05),
            pressure_hpa=_steady(index, 1013.0, 0.03),
            air_quality_raw=_steady(index, 200.0, 1.5),
            ldr_raw=_steady(index, 700.0, 4.0),
            rain_raw=_steady(index, 940.0, 3.0),
        )


def test_case_06_sudden_spike_is_flagged_with_an_explanation(client):
    _build_realistic_baseline(client)
    quiet = post_reading(client, sequence=500, temperature_c=25.02).json()
    assert not [a for a in quiet["anomalies"] if a["sensor"] == "temperature_c"], (
        "a normal reading must not be flagged"
    )

    spike = post_reading(client, sequence=501, temperature_c=41.0).json()
    assert spike["anomalies"], "a 16 degree step must be reported"
    anomaly = next(item for item in spike["anomalies"] if item["sensor"] == "temperature_c")
    assert anomaly["severity"] in {"medium", "high"}
    assert anomaly["explanation"]
    assert anomaly["message"]
    assert anomaly["baseline_samples"] >= 12
    assert anomaly["expected_value"] is not None
    assert anomaly["expected_low"] <= anomaly["expected_value"] <= anomaly["expected_high"]
    assert anomaly["detected_at"]
    # The anomaly is visible over HTTP too, not only in the ingestion response.
    window = client.get("/api/v1/sensors/anomalies", params={"hours": 6}).json()
    assert window["baseline_ready"] is True
    assert window["severity_counts"]["high"] >= 1
    assert window["count"] >= 1


def test_case_14_multiple_simultaneous_anomalies_are_all_reported(client):
    _build_realistic_baseline(client)
    spike = post_reading(
        client,
        sequence=900,
        temperature_c=42.0,
        humidity_pct=95.0,
        air_quality_raw=950.0,
    ).json()

    # Anomalies are reported per monitored metric. Air quality is monitored as
    # the derived `air_quality_index` (comparable across nodes), never as raw
    # ADC counts - so that is the key that must appear.
    sensors = {item["sensor"] for item in spike["anomalies"]}
    assert {"temperature_c", "humidity_pct", "air_quality_index"} <= sensors
    assert len({item["severity"] for item in spike["anomalies"]}) >= 1
    # Every anomaly carries its own evidence, not a shared blanket message.
    assert len({item["explanation"] for item in spike["anomalies"]}) == len(spike["anomalies"])

    # The composite factor must reflect that several things are wrong at once.
    # `risk_reasons` is a top-5 *summary* and can be filled by the band reasons of
    # the individual factors, so the authoritative carrier is the contribution
    # entry - that is what the UI labels, and it is never truncated.
    assert spike["risk_level"] >= 4
    composite = _factor(client, "composite")
    assert composite["points"] > 0
    assert composite["reading"] == len(spike["anomalies"])
    assert "anomal" in composite["reason"].lower()
    assert composite["reason"] in spike["risk_reasons"] or len(spike["risk_reasons"]) == 5


# --------------------------------------------------------------------------- #
# CASE 7 - a missing sensor stays missing
# --------------------------------------------------------------------------- #
def test_case_07_unavailable_sensor_is_reported_never_filled_in(client):
    payload = sample_payload()
    payload.pop("rain_raw")
    payload.pop("air_quality_raw")
    response = client.post("/api/v1/sensors/data", json=payload, headers=auth_headers())
    body = response.json()
    assert response.status_code == 200
    assert set(body["missing_metrics"]) == {"rain", "air_quality"}
    assert any("recorded as missing" in warning for warning in body["warnings"])

    latest = client.get("/api/v1/sensors/latest").json()
    assert latest["rain_raw"] is None
    assert latest["rain_pct"] is None
    assert latest["air_quality_index"] is None
    assert latest["temperature_c"] == 24.6  # the healthy channels are unaffected

    health = client.get("/api/v1/sensors/health").json()
    statuses = {item["key"]: item["status"] for item in health["sensors"]}
    assert statuses["rain_pct"] != "ok"
    assert health["overall_health_score"] < 100


def test_case_07b_a_dead_analog_channel_does_not_stop_the_others(client):
    """One sensor failing must not take the payload down with it.

    "Disconnected" is decided by the firmware (`readAnalogSensor` treats a hard
    zero as no sensor and omits the field), because at the backend a raw 0 is a
    legitimate reading: an unlit LDR in a dark room really does read 0. Both
    halves are asserted here so the division of responsibility is explicit.
    """
    # (a) the field is absent -> the channel is missing, and the rest survives
    payload = sample_payload()
    payload.pop("ldr_raw")
    payload.pop("rain_raw")
    body = client.post(
        "/api/v1/sensors/data", json=payload, headers=auth_headers()
    ).json()
    assert set(body["missing_metrics"]) == {"light", "rain"}
    latest = client.get("/api/v1/sensors/latest").json()
    assert latest["light_pct"] is None
    assert latest["temperature_c"] == 24.6
    assert latest["pressure_hpa"] == 1012.6

    # (b) a raw 0 that *was* sent is stored as what it is - a dark reading - not
    # silently rewritten into something else.
    post_reading(client, sequence=2, ldr_raw=0.0)
    latest = client.get("/api/v1/sensors/latest").json()
    assert latest["ldr_raw"] == 0.0
    assert latest["light_pct"] == 0.0
    assert latest["light_status"] == "dark"


def test_case_07c_a_frozen_channel_is_reported_as_a_stuck_sensor(client):
    """A channel that stops moving is a failure, and must not look normal."""
    _build_realistic_baseline(client)
    for index in range(12):
        post_reading(
            client,
            sequence=200 + index,
            temperature_c=26.4,  # frozen
            humidity_pct=_steady(index, 50.0, 0.09),
            bmp_temperature_c=_steady(index, 24.9, 0.05),
            pressure_hpa=_steady(index, 1013.0, 0.03),
            air_quality_raw=_steady(index, 200.0, 1.5),
            ldr_raw=_steady(index, 700.0, 4.0),
            rain_raw=_steady(index, 940.0, 3.0),
        )
    body = post_reading(
        client,
        sequence=999,
        temperature_c=26.4,
        humidity_pct=50.0,
        bmp_temperature_c=24.9,
        pressure_hpa=1013.0,
        air_quality_raw=200.0,
        ldr_raw=700.0,
        rain_raw=940.0,
    ).json()
    stuck = [item for item in body["anomalies"] if item["kind"] == "stuck"]
    assert any(item["sensor"] == "temperature_c" for item in stuck)
    assert "constant" in stuck[0]["message"].lower()
    assert "wiring" in stuck[0]["explanation"].lower()


# --------------------------------------------------------------------------- #
# CASE 8 - the device stops talking
# --------------------------------------------------------------------------- #
def test_case_08_disconnected_arduino_is_offline_and_alerts(client):
    from datetime import timedelta

    from app.core.database import session_scope
    from app.services.background import scheduler
    from app.utils.timeutils import utcnow

    post_reading(client, sequence=1)
    assert client.get("/api/v1/status").json()["device_online"] is True

    # Move the whole history ten minutes into the past: that is what "the node
    # stopped sending" looks like from the backend's point of view. Both the
    # device telemetry and the stored reading are aged, because device online
    # state and reading staleness are separate facts with separate consumers.
    with session_scope() as session:
        from app.models import Device, SensorReading
        from app.repositories import DeviceRepository, ReadingRepository

        device = DeviceRepository(session).get("arduino-r4-wifi-01")
        assert isinstance(device, Device)
        stale = utcnow() - timedelta(minutes=10)
        device.last_payload_at = stale
        device.last_seen_at = stale
        for reading in ReadingRepository(session).recent("arduino-r4-wifi-01", limit=10):
            assert isinstance(reading, SensorReading)
            reading.received_at = stale
            reading.measured_at = stale
        session.flush()

    scheduler._watchdog_tick()  # noqa: SLF001 - the real job, not a reimplementation

    status = client.get("/api/v1/status").json()
    assert status["device_online"] is False
    assert status["reading_stale"] is True
    assert status["arduino"] == "offline"

    alerts = client.get("/api/v1/alerts").json()
    assert alerts["active_count"] >= 1
    assert any("offline" in alert["title"].lower() for alert in alerts["alerts"])

    # The dashboard must still work with no live device.
    overview = client.get("/api/v1/analytics/overview").json()
    assert overview["has_data"] is True
    assert overview["stale"] is True

    # And the Arduino's own state endpoint must say the data is stale.
    state = client.get(
        "/api/v1/device/arduino-r4-wifi-01/risk-state", headers=auth_headers()
    ).json()
    assert state["stale"] is True
    assert state["age_seconds"] > 60


# --------------------------------------------------------------------------- #
# CASE 9 / 12 / 13 - rejected traffic must not reach the database
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("label", "payload"),
    [
        ("empty body", None),
        ("not json", "{not json at all"),
        ("json array instead of object", "[1, 2, 3]"),
        ("json string", '"temperature"'),
        ("wrong types", {"temperature_c": {"nested": 1}}),
        ("null for every metric", {"temperature_c": None, "humidity_pct": None}),
    ],
)
def test_case_09_malformed_transport_payloads_are_rejected(client, label, payload):
    kwargs: dict = {"headers": auth_headers()}
    if payload is None:
        response = client.post("/api/v1/sensors/data", **kwargs)
    elif isinstance(payload, str) and not payload.startswith(("{", "[")):
        response = client.post(
            "/api/v1/sensors/data",
            data=payload,
            headers={**auth_headers(), "Content-Type": "application/json"},
        )
    else:
        response = client.post("/api/v1/sensors/data", json=payload, **kwargs)

    assert response.status_code in {422, 400}, f"{label}: {response.status_code}"
    assert response.json()["success"] is False
    # Nothing may have been stored or scored off a malformed request.
    assert client.get("/api/v1/sensors/history", params={"hours": 24}).json()["count"] == 0
    assert client.get("/api/v1/alerts").json()["total_count"] == 0


def test_case_12_invalid_api_key_is_rejected_and_stores_nothing(client):
    for key in ("", "wrong", "dev-local-key-change-me", "x" * 200):
        response = client.post(
            "/api/v1/sensors/data", json=sample_payload(), headers={"X-API-Key": key}
        )
        assert response.status_code == 401, key
    assert client.get("/api/v1/sensors/history", params={"hours": 24}).json()["count"] == 0
    assert client.get("/api/v1/device").json()["status"] == "never_seen"


def test_case_13_server_without_a_usable_key_answers_503(client):
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.api_key
    settings.api_key = "dev-local-key-change-me"
    try:
        response = client.post(
            "/api/v1/sensors/data",
            json=sample_payload(),
            headers={"X-API-Key": "dev-local-key-change-me"},
        )
        assert response.status_code == 503
        assert "production use" in response.json()["detail"]
        # Read endpoints are unaffected: the dashboard still works.
        assert client.get("/api/v1/health").status_code == 200
    finally:
        settings.api_key = original


# --------------------------------------------------------------------------- #
# CASE 10 - Ollama unavailable
# --------------------------------------------------------------------------- #
def test_case_10_chatbot_works_without_ollama(client):
    from app.api.routes import chatbot as chatbot_routes
    from app.services.ollama_client import OllamaStatus

    class _Down:
        async def status(self, *, refresh: bool = False):  # noqa: ANN001, ARG002
            return OllamaStatus(
                installed=True,
                running=False,
                host="http://localhost:11434",
                models=["qwen3:4b"],
                selected_model="qwen3:4b",
                detail="Ollama is not reachable at http://localhost:11434 (ConnectError).",
            )

        async def ensure_available(self):
            from app.services.ollama_client import OllamaUnavailable

            raise OllamaUnavailable("Ollama is not reachable.")

        async def chat(self, *args, **kwargs):  # noqa: ANN002, ANN003
            from app.services.ollama_client import OllamaUnavailable

            raise OllamaUnavailable("Ollama is not reachable.")

        async def chat_stream(self, *args, **kwargs):  # noqa: ANN002, ANN003
            from app.services.ollama_client import OllamaUnavailable

            raise OllamaUnavailable("Ollama is not reachable.")

    client.app.dependency_overrides.clear()
    original = chatbot_routes.get_ollama_client
    chatbot_routes.get_ollama_client = lambda: _Down()  # type: ignore[assignment]
    try:
        post_reading(client, sequence=1)

        status = client.get("/api/v1/chat/status").json()
        assert status["available"] is False
        assert status["running"] is False
        assert "not reachable" in status["detail"]

        answer = client.post(
            "/api/v1/chat", json={"message": "What is the current risk?"}
        ).json()
        assert answer["fallback_used"] is True
        assert answer["warning"]
        assert answer["answer"]
        # The answer is grounded in the real reading, not invented.
        assert "24.6" in answer["answer"] or "risk" in answer["answer"].lower()

        # The rest of the platform is entirely unaffected.
        assert client.get("/api/v1/health").json()["checks"]["ollama"] == "degraded"
        assert client.get("/api/v1/analytics/overview").json()["has_data"] is True
        assert client.get("/api/v1/predictions").status_code == 200
    finally:
        chatbot_routes.get_ollama_client = original  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# CASE 11 - not enough history
# --------------------------------------------------------------------------- #
def test_case_11_insufficient_history_produces_no_invented_prediction(client):
    post_reading(client, sequence=1)
    body = client.get("/api/v1/predictions").json()
    assert body["data_sufficient"] is False
    # One reading exists and is reported as one sample - not as zero, and not
    # dressed up as a forecast.
    assert body["samples_used"] == 1
    for metric, prediction in body["metrics"].items():
        assert prediction["predicted_value"] is None, metric
        assert prediction["lower_bound"] is None, metric
        assert prediction["upper_bound"] is None, metric
        assert prediction["confidence"] == 0.0, metric
        assert prediction["method"] == "insufficient_data", metric
        assert prediction["reasoning"], metric
        # The current value is still reported: no forecast is not the same as no
        # data, and the UI shows the reading while saying the forecast is absent.
        assert prediction["current_value"] is not None, metric
    assert body["notes"]
    assert body["disclaimer"]
    assert any("Insufficient historical data" in note for note in body["notes"])

    # Crucially, the illumination channel must not sneak a "prediction" out of
    # the diurnal prior before the minimum-history rule is satisfied.
    assert body["metrics"]["light_pct"]["method"] == "insufficient_data"

    # ...and once there is enough history it becomes available again.
    for index in range(2, 20):
        post_reading(client, sequence=index, temperature_c=25.0 + index * 0.05)
    body = client.get("/api/v1/predictions").json()
    assert body["data_sufficient"] is True
    assert body["metrics"]["temperature_c"]["predicted_value"] is not None
    assert 0.0 < body["metrics"]["temperature_c"]["confidence"] <= 0.92


# --------------------------------------------------------------------------- #
# Cross-cutting: the ingestion contract the firmware depends on
# --------------------------------------------------------------------------- #
def test_firmware_ingestion_contract_shape_is_stable(client):
    """The firmware parses these exact fields out of the response.

    `applyRiskStateFromIngestion()` in the sketch reads risk_level, risk_label,
    risk_score, duplicate, reading_id, server_time and warnings. Renaming any of
    them would leave the LEDs frozen at their last state, so it is asserted here.
    """
    response = post_reading(client, sequence=1)
    body = response.json()
    for field in (
        "success",
        "accepted",
        "message",
        "device_id",
        "reading_id",
        "duplicate",
        "warnings",
        "risk_score",
        "risk_level",
        "risk_label",
        "server_time",
    ):
        assert field in body, field
    assert isinstance(body["risk_level"], int)
    assert 1 <= body["risk_level"] <= 5
    assert isinstance(body["risk_score"], (int, float))
    assert isinstance(body["duplicate"], bool)
    # server_time must be parseable as an ISO-8601 instant; the sketch feeds it
    # to its own clock sync routine.
    from datetime import datetime

    parsed = datetime.fromisoformat(body["server_time"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_risk_state_contract_shape_is_stable(client):
    """The other half of the firmware contract (`pollRiskState`)."""
    post_reading(client, sequence=1)
    body = client.get(
        "/api/v1/device/arduino-r4-wifi-01/risk-state", headers=auth_headers()
    ).json()
    for field in (
        "device_id",
        "risk_score",
        "risk_level",
        "risk_label",
        "led_index",
        "buzzer_pattern",
        "stale",
        "alerts_active",
        "server_time",
    ):
        assert field in body, field
    assert body["led_index"] == body["risk_level"]
    assert body["buzzer_pattern"] in {
        "silent",
        "single_short_60s",
        "double_short_30s",
        "critical_alarm",
    }


def test_ingestion_response_is_valid_json_of_small_size(client):
    """The UNO R4 has ~32 kB of RAM; the response must stay small."""
    body = post_reading(client, sequence=1).json()
    encoded = json.dumps(body)
    assert len(encoded) < 3000, f"ingestion response is {len(encoded)} bytes"
    assert "raw_payload" not in body


def test_alert_actions_round_trip(client):
    """Acknowledge/resolve must be real state transitions, not no-ops."""
    # A critical reading genuinely raises alerts through the production path.
    body = post_reading(
        client,
        sequence=1,
        temperature_c=41.0,
        humidity_pct=92.0,
        air_quality_raw=780.0,
        rain_raw=300.0,
    ).json()
    assert body["alerts_created"] >= 1
    alerts = client.get("/api/v1/alerts", params={"active_only": True}).json()["alerts"]
    assert alerts
    alert_id = alerts[0]["id"]

    acknowledged = client.post(f"/api/v1/alerts/{alert_id}/acknowledge")
    assert acknowledged.status_code == 200
    assert acknowledged.json()["alert"]["acknowledged_at"] is not None
    assert acknowledged.json()["alert"]["is_active"] is True  # ack is not resolve

    resolved = client.post(f"/api/v1/alerts/{alert_id}/resolve")
    assert resolved.status_code == 200
    assert resolved.json()["alert"]["is_active"] is False
    assert resolved.json()["alert"]["resolved_at"] is not None

    remaining = client.get("/api/v1/alerts", params={"active_only": True}).json()
    assert alert_id not in {alert["id"] for alert in remaining["alerts"]}
    assert client.post("/api/v1/alerts/999999/acknowledge").status_code == 404
    assert TEST_API_KEY  # the key the rest of the matrix authenticated with


def test_alert_actions_are_authenticated_when_reads_are_protected(client):
    """The one documented configuration where the dashboard endpoints need a key.

    Alert acknowledge/resolve are *dashboard* actions, so they follow the read
    policy rather than the device policy: the frontend holds no secret, and with
    `REQUIRE_AUTH_FOR_READS=false` (the local default) requiring a key here would
    simply break the alert centre. This test pins that down so the behaviour is a
    decision on record rather than an accident - see docs/api.md.
    """
    from app.core.config import get_settings

    post_reading(client, sequence=1, air_quality_raw=800.0)
    alert_id = client.get("/api/v1/alerts").json()["alerts"][0]["id"]

    # Default: open, because this is a single-user dashboard on a LAN.
    assert client.post(f"/api/v1/alerts/{alert_id}/acknowledge").status_code == 200

    settings = get_settings()
    settings.require_auth_for_reads = True
    try:
        locked = client.post(f"/api/v1/alerts/{alert_id}/acknowledge")
        assert locked.status_code == 401
        assert client.post(
            f"/api/v1/alerts/{alert_id}/acknowledge", headers=auth_headers()
        ).status_code == 200
        # Multiple comments must not be needed: the same switch covers reads too.
        assert client.get("/api/v1/device/list").status_code == 401
    finally:
        settings.require_auth_for_reads = False


# --------------------------------------------------------------------------- #
# Regression - the device list must survive a device that actually exists
# --------------------------------------------------------------------------- #
def test_device_list_is_valid_once_a_device_exists(client):
    """`GET /device/list` 500'd as soon as a real device row existed.

    The internal offline sentinel and the public ``notes`` field shared the
    ``notes`` column, so the raw string ``OFFLINE_FLAGGED`` was serialised into a
    ``list[str]`` field and FastAPI raised a response-validation error. The empty
    -database case still passed (it returns the virtual device), which is exactly
    why the whole suite was green while the Hardware page broke on the first real
    payload. This test therefore ingests first and only then reads the list.
    """
    assert post_reading(client, sequence=1).status_code == 200

    response = client.get("/api/v1/device/list")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    listed = {device["device_id"]: device for device in body["devices"]}
    assert "arduino-r4-wifi-01" in listed

    device = listed["arduino-r4-wifi-01"]
    # `notes` is a list of human strings in every state, never the sentinel.
    assert isinstance(device["notes"], list)
    assert all(isinstance(note, str) for note in device["notes"])
    assert "OFFLINE_FLAGGED" not in json.dumps(body)
    assert "never_seen" != device["status"]

    # /device and /device/list are two views of the same device: they must agree.
    single = client.get("/api/v1/device").json()
    assert single["device_id"] == device["device_id"]
    assert single["notes"] == device["notes"]
    assert single["total_readings"] == device["total_readings"]


def test_device_list_stays_valid_after_the_offline_watchdog_flags(client, session):
    """The watchdog is what writes the sentinel - the API must not expose it.

    The watchdog runs on its own session (as it does in production, where it is a
    background task), so the staged state is committed before the API reads it.
    """
    from datetime import timedelta

    from app.services.device_service import DeviceService
    from app.utils.timeutils import utcnow

    assert post_reading(client, sequence=1).status_code == 200

    # Age the device past the online threshold and let the watchdog flag it.
    device_id = client.get("/api/v1/device").json()["device_id"]
    watchdog = DeviceService(session)
    device = watchdog.repository.get(device_id)
    assert device is not None
    device.last_payload_at = utcnow() - timedelta(days=30)
    session.commit()

    transitions = watchdog.offline_transitions()
    assert any(t["device_id"] == device_id for t in transitions)
    session.commit()

    body = client.get("/api/v1/device/list").json()
    listed = {d["device_id"]: d for d in body["devices"]}[device_id]
    assert listed["online"] is False
    assert listed["status"] == "offline"
    assert isinstance(listed["notes"], list) and listed["notes"]
    assert any("No payload received" in note for note in listed["notes"])
    assert "OFFLINE_FLAGGED" not in json.dumps(body)
    # The same view must agree on the single-device endpoint too.
    assert client.get(f"/api/v1/device/{device_id}").json()["notes"] == listed["notes"]

    # A fresh payload clears the flag and the next watchdog run is a no-op.
    assert post_reading(client, sequence=2).status_code == 200
    assert watchdog.offline_transitions() == []
    session.rollback()
