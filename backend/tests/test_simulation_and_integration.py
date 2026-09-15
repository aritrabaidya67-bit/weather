"""Simulator + end-to-end pipeline tests (the same path real hardware uses)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import get_session_factory  # noqa: E402
from app.schemas import SensorPayload  # noqa: E402
from app.services import SensorService  # noqa: E402
from simulator.environment_model import SCENARIOS, EnvironmentSimulator  # noqa: E402


def test_simulator_is_deterministic_for_a_seed():
    first = EnvironmentSimulator("mixed_weather", seed=42)
    second = EnvironmentSimulator("mixed_weather", seed=42)
    for _ in range(20):
        assert first.step(15)["temperature_c"] == second.step(15)["temperature_c"]


def test_simulator_produces_physical_values():
    simulator = EnvironmentSimulator("heatwave", seed=7)
    temps: list[float] = []
    for _ in range(200):
        payload = simulator.step(15)
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


def test_simulator_temperature_is_gradual_and_correlated_with_time_of_day():
    simulator = EnvironmentSimulator("clear_day", seed=11)
    temps = [simulator.step(60)["temperature_c"] for _ in range(600)]
    diffs = [abs(b - a) for a, b in zip(temps, temps[1:])]
    assert max(diffs) < 1.2
    assert max(temps) - min(temps) > 2.0  # there is a real diurnal swing


def test_storm_scenario_drops_pressure_and_raises_humidity():
    simulator = EnvironmentSimulator("storm", seed=3)
    first = simulator.step(60)
    for _ in range(120):
        last = simulator.step(60)
    assert last["pressure_hpa"] < first["pressure_hpa"]
    assert max(first["humidity_pct"], last["humidity_pct"]) > 60


def test_sensor_faults_scenario_disconnects_and_freezes_sensors():
    simulator = EnvironmentSimulator("sensor_faults", seed=5)
    payloads = [simulator.step(15) for _ in range(10)]
    for payload in payloads:
        assert "rain_raw" not in payload
        assert payload.get("sensors_missing") == ["rain_raw"]
    pressures = {payload["pressure_hpa"] for payload in payloads}
    assert len(pressures) == 1  # frozen channel keeps repeating its value


def test_all_scenarios_produce_valid_payloads():
    for scenario in SCENARIOS:
        simulator = EnvironmentSimulator(scenario, seed=1)
        payload = simulator.step(15)
        parsed = SensorPayload.model_validate(payload)
        assert parsed.device_id
        assert parsed.measurement_keys()


def test_simulated_payloads_go_through_the_real_ingestion_pipeline(session):
    simulator = EnvironmentSimulator("pollution_event", seed=99, device_id="simulator-test-01")
    service = SensorService(session)
    results = []
    for index in range(15):
        payload = simulator.step(15)
        parsed = SensorPayload.model_validate(payload)
        results.append(service.ingest(parsed, raw_body=payload, source_override="simulation"))
    session.commit()

    assert all(result["accepted"] for result in results)
    assert all(result["risk_score"] is not None for result in results)
    # stored with the simulation marker, not faked as hardware
    latest = service.readings.latest("simulator-test-01")
    assert latest is not None
    assert latest.source == "simulation"
    assert latest.risk_level is not None
    assert latest.pressure_hpa is not None


def test_end_to_end_pipeline_from_simulation_to_every_subsystem(client):
    """Simulated data must reach storage, analytics, risk, alerts, predictions and chat."""
    from app.api.routes import chatbot as chatbot_routes

    class _Stub:
        async def chat(self, messages, *, model=None, temperature=None, json_mode=False):  # noqa: ANN001, ARG002
            return "grounded", "qwen3:4b"

        async def status(self, *, refresh: bool = False):  # noqa: ANN001, ARG002
            from app.services.ollama_client import OllamaStatus

            return OllamaStatus(installed=True, running=True, models=["qwen3:4b"], selected_model="qwen3:4b")

        async def ensure_available(self):  # noqa: ANN201
            return await self.status()

    # Feed 40 simulated readings through the real ingestion service.
    simulator = EnvironmentSimulator("mixed_weather", seed=123, device_id="simulator-e2e")
    factory = get_session_factory()
    for _ in range(40):
        payload = simulator.step(15)
        session = factory()
        try:
            SensorService(session).ingest(
                SensorPayload.model_validate(payload), raw_body=payload, source_override="simulation"
            )
        finally:
            session.close()

    status = client.get("/api/v1/status").json()
    assert status["device_online"] is True
    assert status["data_source"] == "simulation"

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
    assert "simulation" in workers


@pytest.mark.asyncio
async def test_chatbot_context_for_simulated_data_states_it_is_simulated(client):
    from app.core.database import get_session_factory
    from app.services.chatbot_service import ChatbotService

    simulator = EnvironmentSimulator("mixed_weather", seed=321, device_id="simulator-chat")
    factory = get_session_factory()
    for _ in range(5):
        payload = simulator.step(15)
        session = factory()
        try:
            SensorService(session).ingest(
                SensorPayload.model_validate(payload), raw_body=payload, source_override="simulation"
            )
        finally:
            session.close()

    session = factory()
    try:
        context = ChatbotService(session).build_context("simulator-chat")
        assert context["data_source"] == "simulated"
        assert context["device"]["source"] == "simulation"
    finally:
        session.close()
