"""Health, metadata and API-key authentication tests."""

from __future__ import annotations

from .conftest import TEST_API_KEY, auth_headers, sample_payload


def test_root_and_health(client):
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["api"] == "/api/v1"

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["database"]["dialect"] == "sqlite"
    assert body["checks"]["database"] == "ok"
    assert body["device"]["online"] is False  # no data has been sent yet


def test_openapi_documents_the_versioned_api(client):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v1/sensors/data" in paths
    assert "/api/v1/analytics/overview" in paths
    assert "/api/v1/chat" in paths
    assert "/api/v1/predictions" in paths
    # request/response schemas are documented
    assert "SensorPayload" in schema["components"]["schemas"]
    assert "IngestionResponse" in schema["components"]["schemas"]


def test_meta_exposes_registry_and_risk_model(client):
    body = client.get("/api/v1/meta").json()
    assert body["api_version"] == "v1"
    sensor_keys = {sensor["key"] for sensor in body["sensors"]}
    assert {"temperature_c", "humidity_pct", "pressure_hpa", "air_quality_index"} <= sensor_keys
    assert len(body["risk_model"]["levels"]) == 5
    assert sum(body["risk_model"]["weights"].values()) == 100
    assert body["alert_rules"]


def test_ingest_requires_api_key(client):
    response = client.post("/api/v1/sensors/data", json=sample_payload())
    assert response.status_code == 401
    assert "API key" in response.json()["detail"]


def test_ingest_rejects_wrong_api_key(client):
    response = client.post(
        "/api/v1/sensors/data", json=sample_payload(), headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401


def test_ingest_accepts_correct_api_key(client):
    response = client.post(
        "/api/v1/sensors/data", json=sample_payload(), headers=auth_headers()
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_risk_state_endpoint_requires_key(client):
    assert client.get("/api/v1/device/arduino-r4-wifi-01/risk-state").status_code == 401
    ok = client.get(
        "/api/v1/device/arduino-r4-wifi-01/risk-state", headers={"X-API-Key": TEST_API_KEY}
    )
    assert ok.status_code == 200
    body = ok.json()
    assert 1 <= body["risk_level"] <= 5
    assert body["led_index"] == body["risk_level"]
    assert body["buzzer_pattern"] in {
        "silent",
        "single_short_60s",
        "double_short_30s",
        "critical_alarm",
    }


def test_read_endpoints_are_open_when_configured(client):
    assert client.get("/api/v1/device/list").status_code == 200
    assert client.get("/api/v1/risk/model").status_code == 200
    assert client.get("/api/v1/alerts/rules").status_code == 200
    assert client.get("/api/v1/realtime/status").status_code == 200


def test_unknown_device_returns_empty_state_not_an_error(client):
    body = client.get("/api/v1/device/never-seen-device").json()
    assert body["online"] is False
    assert body["status"] == "never_seen"
    assert "Waiting for the Arduino" in body["status_message"]
