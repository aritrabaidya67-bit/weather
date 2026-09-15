"""Risk scoring explainability and anomaly detection tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.database import session_scope
from app.models import SensorReading
from app.services import AnomalyService, RiskService
from app.services.risk_service import RiskInputs

from .conftest import auth_headers, post_reading, sample_payload


def _assess(metrics: dict, **kwargs):
    return RiskService().assess(RiskInputs(metrics=metrics, **kwargs))


def test_clean_conditions_score_very_low():
    assessment = _assess(
        {
            "temperature_c": 23.0,
            "humidity_pct": 45.0,
            "pressure_hpa": 1015.0,
            "air_quality_index": 8.0,
            "rain_pct": 0.0,
            "light_pct": 60.0,
            "heat_index_c": None,
        }
    )
    assert assessment["score"] < 20
    assert assessment["level"] == 1
    assert assessment["label"] == "Very Low"
    assert assessment["reducing_factors"]
    assert assessment["context"]["buzzer_pattern"] == "silent"


def test_contributions_sum_to_the_score():
    assessment = _assess(
        {
            "temperature_c": 34.0,
            "humidity_pct": 82.0,
            "pressure_hpa": 996.0,
            "air_quality_index": 72.0,
            "rain_pct": 55.0,
            "light_pct": 30.0,
            "heat_index_c": 41.0,
        }
    )
    contributions = sum(item["points"] for item in assessment["contributions"])
    assert abs(contributions - assessment["score"]) <= 0.6
    assert assessment["level"] >= 4
    assert assessment["reasons"]
    assert assessment["recommended_actions"]


def test_worst_case_conditions_reach_critical():
    assessment = _assess(
        {
            "temperature_c": 42.0,
            "humidity_pct": 95.0,
            "pressure_hpa": 970.0,
            "air_quality_index": 95.0,
            "rain_pct": 90.0,
            "light_pct": 0.0,
            "heat_index_c": 55.0,
        },
        missing_metrics=["rain"],
        anomalies=[
            {"severity": "high", "sensor": "air_quality_index"},
            {"severity": "high", "sensor": "temperature_c"},
        ],
    )
    assert assessment["level"] == 5
    assert assessment["score"] >= 80
    assert assessment["context"]["buzzer_pattern"] == "critical_alarm"
    assert assessment["context"]["led_index"] == 5


def test_combination_rule_fires_for_heat_stress():
    assessment = _assess(
        {
            "temperature_c": 31.0,
            "humidity_pct": 65.0,
            "pressure_hpa": 1010.0,
            "air_quality_index": 10.0,
            "rain_pct": 0.0,
            "light_pct": 50.0,
            "heat_index_c": 34.0,
        }
    )
    keys = {item["key"] for item in assessment["contributions"]}
    assert "heat_stress" in keys
    reasons = " ".join(assessment["reasons"]).lower()
    assert "heat" in reasons


def test_rapid_pressure_drop_escalates_the_pressure_factor():
    base = {
        "temperature_c": 22.0,
        "humidity_pct": 50.0,
        "air_quality_index": 10.0,
        "rain_pct": 0.0,
        "light_pct": 50.0,
    }
    steady = _assess({**base, "pressure_hpa": 1012.0}, trend={"pressure_change_hpa_3h": -0.5})
    falling = _assess({**base, "pressure_hpa": 1008.0}, trend={"pressure_change_hpa_3h": -7.5})
    steady_points = next(c["points"] for c in steady["contributions"] if c["key"] == "pressure")
    falling_points = next(c["points"] for c in falling["contributions"] if c["key"] == "pressure")
    assert falling_points > steady_points
    assert any("dropped" in reason.lower() for reason in falling["reasons"])


def test_deteriorating_air_quality_escalates_its_factor():
    base = {
        "temperature_c": 22.0,
        "humidity_pct": 50.0,
        "pressure_hpa": 1012.0,
        "rain_pct": 0.0,
        "light_pct": 50.0,
    }
    stable = _assess({**base, "air_quality_index": 20.0})
    worsening = _assess(
        {**base, "air_quality_index": 20.0}, trend={"air_quality_slope_per_minute": 0.4}
    )
    stable_points = next(c["points"] for c in stable["contributions"] if c["key"] == "air_quality")
    worsening_points = next(
        c["points"] for c in worsening["contributions"] if c["key"] == "air_quality"
    )
    assert worsening_points > stable_points


def test_missing_sensors_reduce_coverage_and_add_risk():
    complete = _assess(
        {
            "temperature_c": 23.0,
            "humidity_pct": 45.0,
            "pressure_hpa": 1013.0,
            "air_quality_index": 10.0,
            "rain_pct": 0.0,
            "light_pct": 50.0,
        }
    )
    partial = _assess(
        {"temperature_c": 23.0, "humidity_pct": 45.0},
        missing_metrics=["pressure", "air_quality", "light", "rain"],
    )
    assert partial["data_coverage"] < complete["data_coverage"]
    assert partial["score"] > complete["score"]
    assert any("not reporting" in reason for reason in partial["reasons"])


def test_risk_state_payload_matches_led_and_buzzer_contract():
    service = RiskService()
    assessment = _assess(
        {
            "temperature_c": 40.0,
            "humidity_pct": 80.0,
            "pressure_hpa": 990.0,
            "air_quality_index": 85.0,
            "rain_pct": 80.0,
            "light_pct": 10.0,
        }
    )
    state = service.to_state_payload(
        assessment,
        device_id="arduino-r4-wifi-01",
        stale=False,
        age_seconds=1.0,
        data_source="arduino",
        alerts_active=2,
    )
    assert state["led_index"] == state["risk_level"]
    assert 1 <= state["led_index"] <= 5
    assert state["risk_code"] in {"VERY_LOW", "LOW", "MODERATE", "HIGH", "CRITICAL"}


def _seed_history(session, values: dict[str, list[float]], device_id="arduino-r4-wifi-01"):
    """Seed realistic (non-constant) history for every monitored metric.

    Constant channels would (correctly) be reported as stuck sensors by the
    detector, so the seed values always carry a small amount of jitter.
    """
    now = datetime.now(UTC)
    for index, value in enumerate(values["temperature_c"]):
        timestamp = now - timedelta(seconds=15 * (len(values["temperature_c"]) - index))
        session.add(
            SensorReading(
                device_id=device_id,
                measured_at=timestamp,
                received_at=timestamp,
                temperature_c=value,
                humidity_pct=50.0 + index * 0.03,
                pressure_hpa=1013.0 + index * 0.02,
                air_quality_index=10.0 + index * 0.05,
                rain_pct=0.0,
                light_pct=50.0 + (index % 5) * 0.4,
            )
        )
    session.commit()


def test_anomaly_detector_flags_a_spike_and_stays_quiet_on_noise(client):
    detector = AnomalyService()
    with session_scope() as session:
        baseline = [24.0 + (0.05 if index % 2 else -0.05) for index in range(40)]
        _seed_history(session, {"temperature_c": baseline})
        history = session.query(SensorReading).order_by(SensorReading.received_at).all()
        quiet = detector.detect(history, {"temperature_c": 24.05})
        assert quiet == []
        spike = detector.detect(history, {"temperature_c": 33.5})
        assert spike, "a 9.5 degree jump must be reported"
        anomaly = next(item for item in spike if item["sensor"] == "temperature_c")
        assert anomaly["severity"] in {"medium", "high"}
        assert anomaly["expected_value"] is not None
        assert anomaly["baseline_samples"] >= 12
        assert "baseline" in anomaly["explanation"].lower()


def test_anomaly_detector_needs_enough_history(client):
    detector = AnomalyService()
    with session_scope() as session:
        _seed_history(session, {"temperature_c": [24.0, 24.1, 24.2]})
        history = session.query(SensorReading).order_by(SensorReading.received_at).all()
        assert detector.detect(history, {"temperature_c": 40.0}) == []


def test_stuck_sensor_is_detected(client):
    detector = AnomalyService()
    with session_scope() as session:
        now = datetime.now(UTC)
        for index in range(30):
            timestamp = now - timedelta(seconds=15 * (30 - index))
            session.add(
                SensorReading(
                    device_id="arduino-r4-wifi-01",
                    measured_at=timestamp,
                    received_at=timestamp,
                    temperature_c=26.4,  # frozen channel
                    humidity_pct=50.0 + index * 0.04,
                    pressure_hpa=1013.0 + index * 0.02,
                    air_quality_index=10.0 + index * 0.05,
                    light_pct=50.0 + (index % 4) * 0.5,
                )
            )
        session.commit()
        history = session.query(SensorReading).order_by(SensorReading.received_at).all()
        found = detector.detect(history, {"temperature_c": 26.4})
        stuck = [item for item in found if item["kind"] == "stuck"]
        assert stuck
        assert "constant" in stuck[0]["message"].lower()


def test_risk_endpoint_reports_contributions(client):
    post_reading(client, temperature_c=36.0, humidity_pct=85.0, air_quality_raw=760.0)
    body = client.get("/api/v1/risk/current").json()
    assert body["score"] > 0
    assert body["contributions"]
    assert body["recommended_actions"]
    assert body["model_version"]

    analysis = client.get("/api/v1/risk/analysis").json()
    assert analysis["assessment"]["level"] == body["level"]
    assert "trend_direction" in analysis


def test_anomaly_endpoint_reports_baseline_state(client):
    body = client.get("/api/v1/sensors/anomalies").json()
    assert body["baseline_ready"] is False
    assert body["notes"]
    for index in range(20):
        post_reading(client, sequence=index + 900, temperature_c=25.0 + (index % 3) * 0.1)
    body = client.get("/api/v1/sensors/anomalies").json()
    assert body["baseline_ready"] is True
    assert body["severity_counts"]["high"] == 0

    response = post_reading(client, sequence=9999, temperature_c=41.0)
    assert response.json()["anomalies"]
    body = client.get("/api/v1/sensors/anomalies").json()
    assert body["severity_counts"]["high"] >= 1
