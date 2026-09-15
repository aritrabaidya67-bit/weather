"""Sensor payload validation and ingestion tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .conftest import auth_headers, post_reading, sample_payload


def test_full_payload_is_normalised_and_derived(client):
    response = post_reading(client, rain_raw=940.0, ldr_raw=700.0, air_quality_raw=205.0)
    body = response.json()
    assert body["accepted"] is True
    assert body["reading_id"] is not None
    assert body["sensor_health"] == 100.0
    assert body["missing_metrics"] == []

    latest = client.get("/api/v1/sensors/latest").json()
    assert latest["temperature_c"] == 24.6
    assert latest["rain_status"] == "dry"
    # derived values are computed from the raw ADC counts (940 counts ~ nearly dry)
    assert latest["rain_pct"] is not None and latest["rain_pct"] <= 5.0
    assert latest["air_quality_index"] is not None
    assert latest["light_pct"] is not None
    assert latest["heat_index_c"] is None  # below the heat-index validity domain


def test_legacy_flat_payload_shape_is_accepted(client):
    payload = {
        "device_id": "arduino-r4-wifi-01",
        "temperature_dht": 25.4,
        "humidity": 61.2,
        "temperature_bmp": 25.1,
        "pressure": 1013.2,
        "rain_raw": 930,
        "rain_status": "dry",
        "ldr_raw": 780,
        "light_level": "high",
        "air_quality_raw": 310,
        "air_quality_status": "good",
    }
    response = client.post("/api/v1/sensors/data", json=payload, headers=auth_headers())
    assert response.status_code == 200
    latest = client.get("/api/v1/sensors/latest").json()
    assert latest["temperature_c"] == 25.4
    assert latest["humidity_pct"] == 61.2
    assert latest["bmp_temperature_c"] == 25.1
    assert latest["pressure_hpa"] == 1013.2


def test_impossible_values_are_rejected_per_field(client):
    response = post_reading(client, humidity_pct=150.0, pressure_hpa=5000.0)
    body = response.json()
    assert body["accepted"] is True  # other measurements survive
    assert "humidity_pct" in body["rejected_fields"]
    assert "pressure_hpa" in body["rejected_fields"]
    assert any("Rejected" in warning for warning in body["warnings"])

    latest = client.get("/api/v1/sensors/latest").json()
    assert latest["humidity_pct"] is None
    assert latest["temperature_c"] == 24.6


def test_non_numeric_value_is_rejected(client):
    response = client.post(
        "/api/v1/sensors/data",
        json=sample_payload(temperature_c="not-a-number"),
        headers=auth_headers(),
    )
    body = response.json()
    assert body["rejected_fields"]["temperature_c"] == "not a number"
    assert body["accepted"] is True


def test_payload_without_any_measurement_is_rejected(client):
    response = client.post(
        "/api/v1/sensors/data",
        json={"device_id": "arduino-r4-wifi-01", "rain_status": "dry"},
        headers=auth_headers(),
    )
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert "no usable measurements" in body["detail"].lower()


def test_missing_measurements_are_recorded_as_missing_not_filled(client):
    payload = sample_payload()
    for key in ("rain_raw", "ldr_raw"):
        payload.pop(key)
    response = client.post("/api/v1/sensors/data", json=payload, headers=auth_headers())
    body = response.json()
    assert "rain" in body["missing_metrics"]
    assert "light" in body["missing_metrics"]
    assert any("No value for" in warning for warning in body["warnings"])

    latest = client.get("/api/v1/sensors/latest").json()
    assert latest["rain_pct"] is None
    assert latest["light_pct"] is None
    assert "rain" in latest["missing_metrics"]


def test_duplicate_sequence_is_acknowledged_but_not_stored_twice(client):
    first = post_reading(client, sequence=77)
    second = post_reading(client, sequence=77)
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert second.json()["accepted"] is False
    assert second.json()["reading_id"] == first.json()["reading_id"]
    history = client.get("/api/v1/sensors/history", params={"hours": 1}).json()
    assert history["count"] == 1


def test_stale_timestamp_is_corrected_and_flagged(client):
    stale = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    response = post_reading(client, timestamp=stale, sequence=5)
    body = response.json()
    assert body["accepted"] is True
    assert any("clock drift" in warning for warning in body["warnings"])
    latest = client.get("/api/v1/sensors/latest").json()
    assert latest["age_seconds"] < 60


def test_unknown_fields_are_reported(client):
    response = client.post(
        "/api/v1/sensors/data",
        json=sample_payload(bogus_field=123),
        headers=auth_headers(),
    )
    body = response.json()
    assert any("bogus_field" in warning for warning in body["warnings"])


def test_device_telemetry_is_tracked(client):
    post_reading(client, sequence=10, ip_address="192.168.1.50", rssi=-52)
    post_reading(client, sequence=14)  # gap of 3 missed intervals
    device = client.get("/api/v1/device").json()
    assert device["online"] is True
    assert device["total_readings"] == 2
    assert device["missed_intervals"] == 3
    assert device["estimated_delivery_rate_pct"] < 100
    assert device["rssi_quality"] in {"good", "excellent"}


def test_calibration_mismatch_between_firmware_and_backend_is_surfaced(client):
    # 420 counts reads as wet with the default calibration, the firmware says "dry"
    response = post_reading(client, rain_raw=420, rain_status="dry")
    body = response.json()
    assert any("calibration" in warning.lower() for warning in body["warnings"])


def test_ingestion_is_fast(client):
    body = post_reading(client).json()
    assert body["processing_ms"] < 250
