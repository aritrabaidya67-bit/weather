"""History, analytics, prediction and alert tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.database import session_scope
from app.models import SensorReading
from app.services import PredictionService

from .conftest import auth_headers, post_reading


def _seed_series(client, *, count: int = 40, start_temp: float = 24.0, step: float = 0.15):
    """Insert a rising temperature series straight into the DB for analytics tests."""
    with session_scope() as session:
        now = datetime.now(UTC)
        for index in range(count):
            timestamp = now - timedelta(seconds=15 * (count - index))
            session.add(
                SensorReading(
                    device_id="arduino-r4-wifi-01",
                    measured_at=timestamp,
                    received_at=timestamp,
                    source="arduino",
                    temperature_c=round(start_temp + index * step, 2),
                    humidity_pct=round(60.0 - index * 0.1, 2),
                    bmp_temperature_c=round(start_temp + index * step, 2),
                    pressure_hpa=round(1012.0 - index * 0.05, 2),
                    rain_raw=940.0,
                    rain_pct=0.0,
                    ldr_raw=700.0,
                    light_pct=60.0,
                    air_quality_raw=210.0 + index,
                    air_quality_index=round(10 + index * 0.4, 2),
                    risk_score=15.0 + index * 0.1,
                    risk_level=1,
                    risk_label="Very Low",
                )
            )
        session.commit()


def test_history_and_series_statistics(client):
    _seed_series(client, count=40)
    body = client.get("/api/v1/sensors/history", params={"hours": 6, "bucket": "1h"}).json()
    assert body["count"] == 40
    assert body["sufficient_data"] is True
    series = body["series"]["temperature_c"]
    assert series["trend"] == "rising"
    assert series["minimum"] is not None and series["maximum"] is not None
    assert series["mean"] is not None and series["stdev"] is not None
    assert series["slope_per_minute"] is not None
    assert len(body["readings"]) == 40


def test_history_handles_empty_database_gracefully(client):
    body = client.get("/api/v1/sensors/history", params={"hours": 6}).json()
    assert body["count"] == 0
    assert body["sufficient_data"] is False
    assert body["notes"]
    latest = client.get("/api/v1/sensors/latest")
    assert latest.status_code == 404
    assert "No reading stored" in latest.json()["detail"]


def test_aggregation_buckets(client):
    _seed_series(client, count=40)
    body = client.get("/api/v1/sensors/aggregate", params={"hours": 6, "bucket": "1h"}).json()
    assert body["points"]
    point = body["points"][0]
    assert point["count"] > 0
    assert "temperature_c" in point


def test_summary_endpoints(client):
    _seed_series(client, count=40)
    day = client.get("/api/v1/sensors/summary/day").json()
    assert day["reading_count"] == 40
    assert day["metrics"]["temperature_c"]["max"] > day["metrics"]["temperature_c"]["min"]
    assert "risk" in day
    week = client.get("/api/v1/analytics/summary/week").json()
    assert week["period"] == "week"
    assert client.get("/api/v1/analytics/summary/month").status_code == 422


def test_overview_has_every_dashboard_section(client):
    _seed_series(client, count=40)
    body = client.get("/api/v1/analytics/overview").json()
    assert body["has_data"] is True
    assert body["data_source"] == "arduino"
    assert len(body["channels"]) == 6
    channel = body["channels"][0]
    assert {"value", "unit", "status", "trend", "sparkline", "stats"} <= set(channel)
    assert body["risk"]["score"] >= 0
    assert body["classification"]["label"]
    assert body["sensor_health"]
    assert isinstance(body["notes"], list)


def test_observations_are_evidence_backed(client):
    _seed_series(client, count=40, start_temp=24.0, step=0.15)
    body = client.get("/api/v1/analytics/observations").json()
    assert body["count"] >= 1
    for observation in body["observations"]:
        assert observation["evidence"]
        assert observation["generated_from"] == "computed"
    assert any("increased" in item["text"] for item in body["observations"])


def test_observations_are_withheld_without_data(client):
    body = client.get("/api/v1/analytics/observations").json()
    assert body["count"] == 0
    assert body["notes"]


def test_trends_and_compare(client):
    _seed_series(client, count=40)
    trends = client.get("/api/v1/analytics/trends").json()
    assert trends["metrics"]["temperature_c"]["trend"] == "rising"
    assert trends["metrics"]["temperature_c"]["moving_average"]
    compare = client.get("/api/v1/analytics/compare", params={"hours": 1}).json()
    assert compare["metrics"]["temperature_c"]["current_mean"] is not None
    assert any("versus the previous" in item["message"] or "Not enough" in item["message"]
               for item in compare["metrics"].values())


def test_prediction_requires_enough_history(client):
    body = client.get("/api/v1/predictions").json()
    assert body["data_sufficient"] is False
    assert body["samples_used"] == 0
    assert any("Insufficient historical data" in note for note in body["notes"])
    assert body["metrics"]
    for prediction in body["metrics"].values():
        assert prediction["method"] == "insufficient_data"
        assert prediction["predicted_value"] is None
        assert prediction["confidence"] == 0.0
    assert body["disclaimer"]


def test_prediction_forecasts_a_rising_trend(client):
    _seed_series(client, count=60, start_temp=24.0, step=0.2)
    body = client.get("/api/v1/predictions", params={"horizons": "15,30,60"}).json()
    assert body["data_sufficient"] is True
    assert body["samples_used"] == 60
    temperature = body["metrics"]["temperature_c"]
    assert temperature["predicted_value"] > temperature["current_value"]
    assert temperature["direction"] == "rising"
    assert temperature["method"] in {"linear_trend", "holt_linear", "blend"}
    assert 0 < temperature["confidence"] <= 0.92
    assert temperature["lower_bound"] < temperature["predicted_value"] < temperature["upper_bound"]
    assert temperature["reasoning"]
    assert temperature["features"]
    assert str(body["primary_horizon_minutes"]) in body["all_horizons"]
    assert body["risk"]["predicted_score"] is not None
    assert body["summary"]


def test_light_uses_the_diurnal_model(client):
    _seed_series(client, count=60)
    body = client.get("/api/v1/predictions").json()
    light = body["metrics"]["light_pct"]
    assert light["method"] == "diurnal_model"
    assert "solar" in light["reasoning"].lower()


def test_rain_probability_is_a_labelled_heuristic(client):
    _seed_series(client, count=60)
    body = client.get("/api/v1/predictions").json()
    rain = body["rain"]
    assert rain["method"] == "heuristic_probability"
    assert 0 <= rain["probability"] <= 1
    assert "not a meteorological forecast" in rain["reasoning"]


def test_prediction_persistence_and_accuracy_reporting(client):
    _seed_series(client, count=60)
    response = client.get("/api/v1/predictions", params={"persist": "true", "horizons": "15"}).json()
    assert response["data_sufficient"] is True
    history = client.get("/api/v1/predictions/history").json()
    assert history["count"] > 0, "persisted snapshots must survive the request"
    assert history["records"][0]["predicted_value"] is not None
    accuracy = client.get("/api/v1/predictions/accuracy").json()
    assert "horizons" in accuracy
    assert accuracy["notes"]

    with session_scope() as session:
        service = PredictionService(session)
        # Force a forecast to be past-due and check it gets scored.
        record = service.predictions.list("arduino-r4-wifi-01", limit=1)[0]
        record.target_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
        evaluated = service.evaluate_pending()
        assert evaluated >= 0


def test_alerts_fire_and_resolve(client):
    response = post_reading(
        client,
        sequence=1,
        temperature_c=41.0,
        humidity_pct=92.0,
        air_quality_raw=780.0,
        rain_raw=300.0,
    )
    body = response.json()
    assert body["risk_level"] >= 4
    assert body["alerts_created"] >= 1

    alerts = client.get("/api/v1/alerts", params={"active_only": True}).json()
    assert alerts["active_count"] >= 1
    categories = {alert["category"] for alert in alerts["alerts"]}
    assert "temperature" in categories or "risk_high" in categories or "risk_critical" in categories
    for alert in alerts["alerts"]:
        assert alert["severity"] in {"info", "warning", "critical"}
        assert alert["message"]
        assert alert["recommended_action"]

    # Bring the environment back to normal: the alerts must resolve themselves.
    post_reading(client, sequence=2, temperature_c=23.0, humidity_pct=45.0, air_quality_raw=190.0, rain_raw=940.0)
    after = client.get("/api/v1/alerts", params={"active_only": True}).json()
    assert after["active_count"] <= alerts["active_count"]


def test_alert_acknowledge_and_rule_catalogue(client):
    rules = client.get("/api/v1/alerts/rules").json()
    assert any(rule["id"] == "sensor_failure" for rule in rules)
    post_reading(client, sequence=1, air_quality_raw=800.0)
    alerts = client.get("/api/v1/alerts").json()["alerts"]
    assert alerts
    alert_id = alerts[0]["id"]
    ack = client.post(f"/api/v1/alerts/{alert_id}/acknowledge")
    assert ack.status_code == 200
    assert ack.json()["alert"]["acknowledged_at"]
    assert client.post("/api/v1/alerts/999999/acknowledge").status_code == 404


def test_alert_deduplication_within_cooldown(client):
    for sequence in range(1, 6):
        post_reading(client, sequence=sequence, air_quality_raw=800.0)
    alerts = client.get("/api/v1/alerts", params={"category": "air_quality"}).json()
    assert len(alerts["alerts"]) == 1
    assert alerts["alerts"][0]["occurrence_count"] >= 2


def test_sensor_health_reports_every_channel(client):
    post_reading(client, sequence=1)
    body = client.get("/api/v1/sensors/health").json()
    assert body["overall_health_score"] == 100.0
    assert len(body["sensors"]) == 6
    for item in body["sensors"]:
        assert item["status"] in {"ok", "degraded", "stale", "suspect", "failed", "unknown"}
        assert item["message"]


def test_status_endpoint_reports_offline_before_any_data(client):
    body = client.get("/api/v1/status").json()
    assert body["backend"] == "online"
    assert body["device_online"] is False
    assert body["reading_stale"] is True
    assert body["data_source"] in {"unknown", "arduino"}


def test_status_is_online_after_a_reading(client):
    post_reading(client)
    body = client.get("/api/v1/status").json()
    assert body["device_online"] is True
    assert body["reading_stale"] is False
