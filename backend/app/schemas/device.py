"""Device / hardware-page schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SensorHealthOut(BaseModel):
    key: str
    label: str
    channel: str | None = None
    status: str = "unknown"
    last_value: float | None = None
    unit: str | None = None
    last_seen_at: str | None = None
    age_seconds: float | None = None
    expected_rate_per_minute: float | None = None
    observed_rate_per_minute: float | None = None
    coverage_pct: float | None = None
    message: str | None = None


class DeviceOut(BaseModel):
    device_id: str
    display_name: str | None = None
    online: bool = False
    status: str = "unknown"
    status_message: str = ""
    source: str = "arduino"
    firmware_version: str | None = None
    ip_address: str | None = None
    rssi: int | None = None
    rssi_quality: str | None = None
    uptime_ms: int | None = None
    uptime_human: str | None = None
    transmission_interval_ms: int | None = None
    transmission_interval_seconds: float | None = None
    expected_interval_seconds: float | None = None
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    last_payload_at: str | None = None
    seconds_since_last_payload: float | None = None
    total_readings: int = 0
    rejected_payloads: int = 0
    missed_intervals: int = 0
    estimated_delivery_rate_pct: float | None = None
    sensors_available: list[str] = Field(default_factory=list)
    sensors_missing: list[str] = Field(default_factory=list)
    sensor_health: list[SensorHealthOut] = Field(default_factory=list)
    last_risk_score: float | None = None
    last_risk_level: int | None = None
    last_reading_at: str | None = None
    notes: list[str] = Field(default_factory=list)


class DeviceListResponse(BaseModel):
    count: int = 0
    devices: list[DeviceOut] = Field(default_factory=list)
    primary_device_id: str | None = None
    offline_message: str = (
        "Waiting for the Arduino UNO R4 Wi-Fi to send sensor data. "
        "Check that the node is powered, on the same Wi-Fi network and pointed at this backend."
    )


class RiskStateResponse(BaseModel):
    """Compact endpoint polled by the Arduino to drive LEDs and the buzzer."""

    device_id: str
    risk_score: float
    risk_level: int
    risk_label: str
    risk_code: str
    color: str
    led_index: int
    buzzer_pattern: str
    reasons: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    stale: bool = False
    age_seconds: float | None = None
    data_source: str = "unknown"
    evaluated_at: str | None = None
    alerts_active: int = 0
    server_time: str | None = None


class HeartbeatResponse(BaseModel):
    success: bool
    device_id: str
    server_time: str
    ack: str = "ok"
    expected_interval_seconds: int
    commands: list[str] = Field(default_factory=list)


class MetaResponse(BaseModel):
    app_name: str
    version: str
    environment: str
    server_time: str
    api_version: str
    risk_model: dict[str, Any]
    sensors: list[dict[str, Any]] = Field(default_factory=list)
    channels: list[dict[str, Any]] = Field(default_factory=list)
    alert_rules: list[dict[str, Any]] = Field(default_factory=list)
    features: dict[str, Any] = Field(default_factory=dict)
    local_addresses: list[str] = Field(default_factory=list)
    recommended_backend_url: str | None = None
