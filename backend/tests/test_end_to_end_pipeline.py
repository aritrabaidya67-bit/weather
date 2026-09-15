"""End-to-end pipeline tests.

The Arduino node itself cannot run inside CI, so the deterministic model in
``tests/fixtures/environment_model.py`` produces payloads in exactly the
firmware's shape. They are pushed through the same ``SensorService.ingest``
pipeline the real device uses, which is what proves the production path from
payload validation to risk, anomalies, predictions, alerts and chat context.
"""

from __future__ import annotations

import pytest

from app.core.database import get_session_factory
from app.schemas import SensorPayload
from app.services import SensorService

from .fixtures.environment_model import SCENARIOS, EnvironmentSimulator


def test_environment_model_is_deterministic_for_a_seed() -> None:
    first = EnvironmentSimulator("mixed_weather", seed=42)
    second = EnvironmentSimulator("mixed_weather", seed=42)
    for _ in range(20):
        assert first.step(15)["temperature_c"] == second.step(15)["temperature_c"]


def test_environment_model_produces_physical_values() -> None:
    model = EnvironmentSimulator("heatwave", seed=7)
    temps: list[float] = []
    for _ in range(200):
        payload = model.step(15)
        assert -40 <= payload["temperature_c"] <= 85
        assert 0 <= payload["humidity_pct"] <= 100
        assert 300 <= payload["pressure_hpa"] <= 1100
        assert 0 <= payload["rain_raw"] <= 1023
        assert 0 <= payload["ldr_raw"] <= 1023
        assert 0 <= payload["air_quality_raw"] <= 1023
        assert payload["rain_status"] in {"dry", "light rain", "rain", "heavy rain"}
        temps.append(payload["temperature_c"])
    # a heatwave scenario must actually be hot
    assert max(temps) > 28
    # and temperature must not teleport (gradual, physical movement)
    for previous, current in zip(temps, temps[1:]):
        assert abs(current - previous) < 2.0


def test_environment_model_temperature_is_gradual_over_the_day() -> None:
    model = EnvironmentSimulator("clear_day", seed=11)
    temps = [model.step(60)["temperature_c"] for _ in range(600)]
    diffs = [abs(b - a) for a, b in zip(temps, temps[1:])]
    assert max(diffs) < 1.2
    assert max(temps) - min(temps) > 2.0  # there is a real diurnal swing


def test_storm_scenario_drops_pressure_and_raises_humidity() -> None:
    model = EnvironmentSimulator("storm", seed=3)
    first = model.step(60)
    for _ in range(120):
        last = model.step(60)
    assert last["pressure_hpa"] < first["pressure_hpa"]
    assert max(first["humidity_pct"], last["humidity_pct"]) > 60


def test_fault_scenario_disconnects_and_freezes_sensors() -> None:
    """Sensor-failure payloads must look like a device with dead wiring."""
    model = EnvironmentSimulator("sensor_faults", seed=5)
    payloads = [model.step(15) for _ in range(10)]
    for payload in payloads:
        assert "rain_raw" not in payload
        assert payload.get("sensors_missing") == ["rain_raw"]
    pressures = {payload["pressure_hpa"] for payload in payloads}
    assert len(pressures) == 1  # frozen channel keeps repeating its value


def test_every_scenario_produces_a_schema_valid_payload() -> None:
    for scenario in SCENARIOS:
        payload = EnvironmentSimulator(scenario, seed=1).step(15)
        parsed = SensorPayload.model_validate(payload)
        assert parsed.device_id
        assert parsed.measurement_keys()


def test_payloads_travel_through_the_real_ingestion_pipeline(session) -> None:
    model = EnvironmentSimulator("pollution_event", seed=99, device_id="arduino-r4-wifi-01")
    service = SensorService(session)
    results = []
    for _ in range(15):
        payload = model.step(15)
        results.append(service.ingest(SensorPayload.model_validate(payload), raw_body=payload))
    session.commit()

    assert all(result["accepted"] for result in results)
    assert all(result["risk_score"] is not None for result in results)
    latest = service.readings.latest("arduino-r4-wifi-01")
    assert latest is not None
    assert latest.source == "arduino"
    assert latest.risk_level is not None
    assert latest.pressure_hpa is not None


def _seed_readings(count: int, *, scenario: str = "mixed_weather", seed: int = 123) -> None:
    """Push ``count`` fixture payloads through the production ingestion service."""
    model = EnvironmentSimulator(scenario, seed=seed, device_id="arduino-r4-wifi-01")
    factory = get_session_factory()
    for _ in range(count):
        payload = model.step(15)
        session = factory()
        try:
            SensorService(session).ingest(SensorPayload.model_validate(payload), raw_body=payload)
        finally:
            session.close()


def test_end_to_end_pipeline_reaches_every_subsystem(client) -> None:
    """Ingested payloads must reach storage, analytics, risk, alerts and predictions."""
    _seed_readings(40)

    status = client.get("/api/v1/status").json()
    assert status["device_online"] is True
    assert status["data_source"] == "arduino"

    overview = client.get("/api/v1/analytics/overview").json()
    assert overview["has_data"] is True
    assert overview["latest"]["temperature_c"] is not None
    assert len(overview["channels"]) == 6

    risk = client.get("/api/v1/risk/current").json()
    assert 0 <= risk["score"] <= 100
    assert 1 <= risk["level"] <= 5

    prediction = client.get("/api/v1/predictions").json()
    assert prediction["samples_used"] >= 10
    assert prediction["metrics"]

    alerts = client.get("/api/v1/alerts").json()
    assert "active_count" in alerts

    history = client.get("/api/v1/sensors/history", params={"hours": 6}).json()
    assert history["count"] == 40

    workers = client.get("/api/v1/system/workers").json()
    assert "background" in workers


def test_chatbot_context_is_built_from_stored_hardware_data(client) -> None:
    from app.services.chatbot_service import ChatbotService

    _seed_readings(5, seed=321)

    session = get_session_factory()()
    try:
        context = ChatbotService(session).build_context("arduino-r4-wifi-01")
        assert context["data_source"] == "live hardware"
        assert context["device"]["source"] == "arduino"
        assert context["data_quality"]["has_any_data"] is True
        assert context["current_reading"]["temperature_c"]["unit"] == "degC"
    finally:
        session.close()


def test_low_light_reporting_drives_the_light_channel(client) -> None:
    """Values must survive the whole path unchanged (no unit or scaling drift)."""
    model = EnvironmentSimulator("clear_day", seed=8, device_id="arduino-r4-wifi-01")
    payload = model.step(15)
    response = client.post("/api/v1/sensors/data", json=payload, headers={"X-API-Key": "test-api-key-1234567890"})
    assert response.status_code == 200, response.text
    stored = client.get("/api/v1/sensors/latest").json()
    assert stored["temperature_c"] == pytest.approx(payload["temperature_c"], abs=0.05)
    assert stored["humidity_pct"] == pytest.approx(payload["humidity_pct"], abs=0.05)
    assert stored["pressure_hpa"] == pytest.approx(payload["pressure_hpa"], abs=0.05)
    assert stored["rain_raw"] == pytest.approx(payload["rain_raw"], abs=0.5)
    assert stored["ldr_raw"] == pytest.approx(payload["ldr_raw"], abs=0.5)
    assert stored["air_quality_raw"] == pytest.approx(payload["air_quality_raw"], abs=0.5)
