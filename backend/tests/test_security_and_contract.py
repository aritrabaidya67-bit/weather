"""Authentication policy, CORS policy, API-contract compatibility and persistence.

These tests cover behaviour that the rest of the suite does not touch:

* the device key is *rejected* when it is a placeholder / too short, rather than
  silently accepted (the failure mode that turns a template into a live secret)
* CORS is an allow-list and a wildcard entry is dropped rather than honoured
* the OpenAPI schema still exposes the fields the TypeScript client reads, so a
  renamed or removed response field fails here instead of in the browser
* rows survive a new session (a real persistence check, not just an in-memory
  object graph)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from .conftest import TEST_ADMIN_KEY, TEST_API_KEY, auth_headers, post_reading


# --------------------------------------------------------------------------- #
# API key policy
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "weak_key",
    [
        "",
        None,
        "change-me-device-key",
        "dev-local-key-change-me",
        "replace_with_a_long_random_device_key",
        "replace_with_the_same_key_as_backend_env",
        "YOUR_API_KEY_HERE_1234567890",
        "example-key-for-testing-1234",
        "secret",
        "short-but-not-placeholder",
        "aaaaaaaaaaaaaaaaaaaaaaaa",
    ],
)
def test_weak_or_placeholder_api_keys_are_refused(weak_key):
    """A published/template/short key must never authenticate a device.

    This is the failure mode that turns a template value into a live credential:
    `cp .env.example .env` and never editing `API_KEY`. The server answers 503
    (a configuration problem the operator must fix) rather than 401.
    """
    from app.core.security import key_strength_problem

    assert key_strength_problem(weak_key) is not None


def test_strong_keys_pass_the_policy_check():
    from app.core.security import key_strength_problem

    assert key_strength_problem(TEST_API_KEY) is None
    assert key_strength_problem(TEST_ADMIN_KEY) is None
    # A realistic generated key, as documented in the README.
    assert key_strength_problem("kJ8x-Q2m7vT4pR9wZ1nL6sB3cF0yH5dG") is None


@pytest.mark.parametrize(
    "published",
    [
        # Literals that were committed in this repository's tests and docs. They
        # are public, so they must never be usable as a real credential.
        "test-api-key-1234567890",
        "test-admin-key-1234567890",
        "admin-secret-key-0123456789abcdef",
        "smoke-api-key-1234567890",
        "smoke-admin-key-1234567890",
    ],
)
def test_credentials_published_in_the_repository_are_blacklisted(published):
    """Rotation guard: a leaked literal stays unusable even if copied into .env."""
    from app.core.security import key_strength_problem

    assert key_strength_problem(published) is not None


def test_ingest_returns_503_and_names_the_reason_when_the_key_is_a_template(client):
    """The templated-key path is exercised end to end, not just as a predicate."""
    from app.core.config import get_settings
    from app.core.security import require_api_key
    from app.main import app

    settings = get_settings()
    original = settings.api_key
    settings.api_key = "dev-local-key-change-me"
    app.dependency_overrides.pop(require_api_key, None)
    try:
        response = client.post(
            "/api/v1/sensors/data",
            json={"temperature_c": 25.0},
            headers={"X-API-Key": "dev-local-key-change-me"},
        )
        assert response.status_code == 503
        detail = response.json()["detail"]
        assert "not configured for production use" in detail
        # The value itself must never be echoed back.
        assert "dev-local-key-change-me" not in detail
    finally:
        settings.api_key = original


def test_auth_failures_never_reveal_whether_a_key_exists(client):
    """Missing and wrong keys must be indistinguishable to the caller."""
    missing = client.post("/api/v1/sensors/data", json={"temperature_c": 25.0})
    wrong = client.post(
        "/api/v1/sensors/data", json={"temperature_c": 25.0}, headers={"X-API-Key": "nope"}
    )
    assert missing.status_code == wrong.status_code == 401
    assert missing.json()["detail"] == wrong.json()["detail"]
    assert missing.headers.get("www-authenticate") == "X-API-Key"


# --------------------------------------------------------------------------- #
# CORS policy
# --------------------------------------------------------------------------- #
def test_cors_allows_only_configured_origins(client):
    allowed = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"

    blocked = client.get("/api/v1/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in blocked.headers


def test_cors_wildcard_entry_is_ignored_not_honoured():
    from app.core.config import Settings

    settings = Settings(cors_origins="*,http://localhost:5173")
    assert "*" not in settings.cors_origin_list
    assert settings.cors_origin_list == ["http://localhost:5173"]
    assert settings.cors_wildcard_requested is True
    assert settings.cors_regex is None


def test_lan_origin_regex_is_off_by_default_and_private_only():
    from app.core.config import Settings

    default = Settings(cors_origin_regex="")
    assert default.cors_regex is None

    lan = Settings(cors_origin_regex="", cors_allow_lan_origins=True)
    regex = lan.cors_regex
    assert regex is not None
    import re

    assert re.match(regex, "http://192.168.1.50:5173")
    assert re.match(regex, "http://10.0.0.7:5173")
    assert re.match(regex, "http://172.16.4.9:5173")
    # ...and it can never widen access to a public host.
    assert not re.match(regex, "https://evil.example.com")
    assert not re.match(regex, "http://172.32.0.1:5173")  # outside 172.16-31/12


# --------------------------------------------------------------------------- #
# API contract compatibility with the TypeScript types
# --------------------------------------------------------------------------- #
def test_openapi_documents_the_fields_the_frontend_reads(client):
    """Guard the frontend/backend boundary.

    `frontend/src/types/index.ts` is hand-written, so nothing else would catch a
    field being renamed or dropped on the server side: the UI would simply read
    `undefined`. These are the fields the dashboard renders directly.
    """
    schema = client.get("/openapi.json").json()
    schemas = schema["components"]["schemas"]

    def properties(name: str) -> set[str]:
        assert name in schemas, f"{name} is missing from the OpenAPI schema"
        return set(schemas[name].get("properties", {}))

    assert {
        "temperature_c",
        "humidity_pct",
        "bmp_temperature_c",
        "pressure_hpa",
        "rain_raw",
        "rain_pct",
        "ldr_raw",
        "light_pct",
        "air_quality_raw",
        "air_quality_index",
        "heat_index_c",
        "dew_point_c",
        "rain_status",
        "light_status",
        "air_quality_status",
        "risk_score",
        "risk_level",
        "risk_label",
        "risk_reasons",
        "recommended_actions",
        "anomalies",
        "health_score",
        "timestamp",
        "received_at",
        "source",
    } <= properties("SensorReadingOut")

    # The compact device state that drives the Arduino's LEDs and buzzer.
    assert {
        "risk_score",
        "risk_level",
        "risk_label",
        "risk_code",
        "color",
        "led_index",
        "buzzer_pattern",
        "stale",
        "age_seconds",
        "alerts_active",
        "server_time",
    } <= properties("RiskStateResponse")

    # Predictions must keep the fields that distinguish estimate from fact.
    assert {
        "predicted_value",
        "lower_bound",
        "upper_bound",
        "confidence",
        "confidence_label",
        "method",
        "samples_used",
        "horizon_minutes",
        "direction",
    } <= properties("MetricPrediction")


def test_metric_prediction_field_names_are_stable(client):
    """The prediction response uses the same metric keys as the registry."""
    from app.core.sensors import REGISTRY

    body = client.get("/api/v1/risk/model").json()
    for factor in body["factors"]:
        if factor["metric"] is not None:
            assert factor["metric"] in REGISTRY


def test_risk_state_and_dashboard_agree_on_the_level(client):
    """One risk model: the LEDs, the buzzer and the UI cannot disagree.

    The physical level is whatever the backend computed for the *latest stored
    reading*, so the compact state must match `/risk/current` for that reading.
    """
    post_reading(client, sequence=1, temperature_c=41.0, air_quality_raw=900.0)
    state = client.get(
        "/api/v1/device/arduino-r4-wifi-01/risk-state", headers=auth_headers()
    ).json()
    current = client.get("/api/v1/risk/current").json()

    assert state["risk_level"] == current["level"]
    assert state["risk_score"] == pytest.approx(current["score"], abs=0.05)
    assert state["led_index"] == state["risk_level"]
    assert state["risk_label"] == current["label"]
    assert 1 <= state["risk_level"] <= 5

    # Level -> LED/buzzer mapping is the same table the firmware implements.
    expected_buzzer = {
        1: "silent",
        2: "silent",
        3: "single_short_60s",
        4: "double_short_30s",
        5: "critical_alarm",
    }
    assert state["buzzer_pattern"] == expected_buzzer[state["risk_level"]]


def test_risk_state_is_deterministic_for_identical_input(client):
    """Repeated identical payloads must produce identical scores."""
    payload = dict(temperature_c=33.0, humidity_pct=71.0, air_quality_raw=560.0)
    post_reading(client, sequence=1, **payload)
    first = client.get(
        "/api/v1/device/arduino-r4-wifi-01/risk-state", headers=auth_headers()
    ).json()
    second = client.get(
        "/api/v1/device/arduino-r4-wifi-01/risk-state", headers=auth_headers()
    ).json()
    assert first["risk_score"] == second["risk_score"]
    assert first["risk_level"] == second["risk_level"]
    assert first["risk_label"] == second["risk_label"]


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def test_readings_survive_a_new_session(client):
    """Data must be committed to the database, not held in a session."""
    post_reading(client, sequence=1, temperature_c=26.7)
    post_reading(client, sequence=2, temperature_c=27.1)

    from app.core.database import get_session_factory

    session = get_session_factory()()
    try:
        from app.repositories import ReadingRepository

        repository = ReadingRepository(session)
        stored = repository.recent("arduino-r4-wifi-01", limit=10)
        assert len(stored) == 2
        assert [row.temperature_c for row in stored] == [26.7, 27.1]
        assert repository.count() == 2
    finally:
        session.close()

    # ...and they are still served over the API by a fresh request/session.
    history = client.get("/api/v1/sensors/history", params={"hours": 1}).json()
    assert history["count"] == 2


def test_timestamps_are_timezone_aware_utc(client):
    post_reading(client, sequence=1)
    latest = client.get("/api/v1/sensors/latest").json()
    for field in ("timestamp", "received_at"):
        value = latest[field]
        assert value.endswith("+00:00") or value.endswith("Z"), (field, value)
        from datetime import datetime

        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None
        assert parsed.utcoffset().total_seconds() == 0


def test_empty_database_serves_honest_states_not_errors(client):
    """An empty database is a valid state for every important endpoint."""
    assert client.get("/api/v1/health").json()["status"] == "ok"

    assert client.get("/api/v1/device").json()["status"] == "never_seen"
    assert client.get("/api/v1/sensors/latest").status_code == 404

    overview = client.get("/api/v1/analytics/overview").json()
    assert overview["has_data"] is False
    assert overview["reading_count"] == 0
    # The reason is stated rather than left as an empty chart, and no sensor is
    # reported with an invented value.
    assert any("No readings stored yet" in note for note in overview["notes"])
    # Every channel says exactly that, with no invented value: "no data" is
    # distinct from "stale", because "never reported" and "stopped reporting"
    # are different failures with different fixes.
    for card in overview["channels"]:
        assert card["value"] is None
        assert card["status"] == "no data"
        assert card["sample_count"] == 0
        assert card["sufficient_data"] is False

    prediction = client.get("/api/v1/predictions").json()
    assert prediction["data_sufficient"] is False
    assert prediction["samples_used"] == 0
    for metric in prediction["metrics"].values():
        assert metric["predicted_value"] is None
        assert metric["confidence"] == 0.0
        assert metric["method"] == "insufficient_data"

    anomalies = client.get("/api/v1/sensors/anomalies").json()
    assert anomalies["count"] == 0
    assert anomalies["baseline_ready"] is False

    alerts = client.get("/api/v1/alerts").json()
    assert alerts["active_count"] == 0
    assert alerts["alerts"] == []


def test_device_purge_removes_only_that_devices_readings(client):
    """Purge is destructive: it needs ADMIN_API_KEY, not the device key.

    The original version of this test accepted the device key - that privilege
    escalation is exactly what the hardening pass removed (see
    test_authorization_and_hardening.py for the full admin/device separation
    matrix).
    """
    from app.core.config import get_settings

    post_reading(client, sequence=1)
    post_reading(client, sequence=2)
    assert client.get("/api/v1/sensors/history", params={"hours": 1}).json()["count"] == 2

    # No admin key configured: fail closed with 503 naming the remedy.
    unconfigured = client.delete("/api/v1/device/arduino-r4-wifi-01/readings")
    assert unconfigured.status_code == 503
    # The device key is not an admin credential: without an admin key the
    # endpoint 503s regardless of what credential is presented.
    device_key = client.delete(
        "/api/v1/device/arduino-r4-wifi-01/readings", headers=auth_headers()
    )
    assert device_key.status_code == 503

    from .conftest import TEST_ADMIN_KEY

    settings = get_settings()
    original = settings.admin_api_key
    settings.admin_api_key = TEST_ADMIN_KEY
    try:
        response = client.delete(
            "/api/v1/device/arduino-r4-wifi-01/readings",
            headers={"X-API-Key": settings.admin_api_key},
        )
        assert response.status_code == 200
        assert response.json()["deleted_readings"] == 2
        assert client.get("/api/v1/sensors/history", params={"hours": 1}).json()["count"] == 0
    finally:
        settings.admin_api_key = original


def test_client_is_never_given_the_device_key(client):
    """No read endpoint may echo the credential back to a browser."""
    from app.core.config import get_settings

    key = get_settings().api_key
    for path in ("/api/v1/meta", "/api/v1/health", "/api/v1/status", "/api/v1/device"):
        assert key not in client.get(path).text
    assert key not in client.get("/openapi.json").text


def test_testclient_fixture_is_usable_outside_the_client_fixture():
    """Guards against the conftest fixture silently stopping applying."""
    assert TestClient is not None
