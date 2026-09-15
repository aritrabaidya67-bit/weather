"""Sensor ingestion and history schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..core.sensors import REGISTRY, resolve_alias

MeasurementValue = float | int | str | bool | None

#: Status strings are free-form because the firmware decides the wording, but we
#: keep them short so they cannot be used as a smuggling channel.
_STATUS_FIELDS = ("rain_status", "light_status", "air_quality_status")


class SensorPayload(BaseModel):
    """Payload accepted from the Arduino node.

    Both shapes are accepted:

    * canonical (nested): ``{"device_id": ..., "measurements": {...}}``
    * legacy flat (the original project's shape): ``{"temperature_dht": 25.4,
      "humidity": 61.2, "rain_raw": 420, ...}``

    Legacy names are mapped onto canonical registry keys, so an old sketch keeps
    working while new firmware can use explicit units.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    device_id: str = Field(min_length=3, max_length=64)
    timestamp: datetime | str | float | int | None = None
    sequence: int | None = Field(default=None, ge=0, le=2**31 - 1)
    firmware_version: str | None = Field(default=None, max_length=32)
    uptime_ms: int | None = Field(default=None, ge=0)
    ip_address: str | None = Field(default=None, max_length=64)
    rssi: int | None = Field(default=None, ge=-127, le=10)
    transmission_interval_ms: int | None = Field(default=None, ge=100, le=3_600_000)
    #: ``arduino`` is the normal edge-device value; ``api``/``manual`` cover
    #: integrations and tests that post through the documented endpoint.
    source: Literal["arduino", "api", "manual"] | None = None
    sensors_available: list[str] | None = None
    sensors_missing: list[str] | None = None

    # canonical measurement fields (all optional: a failed sensor omits its value)
    temperature_c: MeasurementValue = None
    humidity_pct: MeasurementValue = None
    bmp_temperature_c: MeasurementValue = None
    pressure_hpa: MeasurementValue = None
    rain_raw: MeasurementValue = None
    rain_pct: MeasurementValue = None
    ldr_raw: MeasurementValue = None
    light_pct: MeasurementValue = None
    air_quality_raw: MeasurementValue = None
    air_quality_index: MeasurementValue = None

    rain_status: str | None = Field(default=None, max_length=24)
    light_status: str | None = Field(default=None, max_length=24)
    air_quality_status: str | None = Field(default=None, max_length=24)

    @model_validator(mode="before")
    @classmethod
    def _flatten_and_alias(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        merged: dict[str, Any] = dict(data)

        # 1. merge nested containers ("sensors", "measurements", "data")
        for container in ("sensors", "measurements", "readings", "data"):
            nested = merged.pop(container, None)
            if isinstance(nested, dict):
                for key, value in nested.items():
                    merged.setdefault(key, value)

        # 2. resolve legacy aliases onto canonical keys
        for key in list(merged.keys()):
            canonical = resolve_alias(key)
            if canonical and canonical != key and merged.get(canonical) is None:
                merged[canonical] = merged[key]
                merged.pop(key, None)

        # 2b. the original sketch sent "light_level": "high" (a label, not a value)
        legacy_light = merged.pop("light_level", None)
        if legacy_light is not None:
            try:
                merged.setdefault("light_pct", float(str(legacy_light)))
            except ValueError:
                merged.setdefault("light_status", str(legacy_light)[:24])

        # 3. accept a couple of common metadata spellings
        if "device_id" not in merged or merged.get("device_id") in (None, ""):
            for alt in ("deviceId", "device", "id"):
                if merged.get(alt):
                    merged["device_id"] = merged[alt]
                    break
        if "ip_address" not in merged:
            for alt in ("ip", "local_ip", "wifi_ip"):
                if merged.get(alt):
                    merged["ip_address"] = merged[alt]
                    break
        return merged

    def measurement_keys(self) -> list[str]:
        keys: list[str] = []
        for key in REGISTRY:
            value = getattr(self, key, None)
            if value is not None:
                keys.append(key)
        return keys


class SensorReadingOut(BaseModel):
    id: int | None = None
    device_id: str
    timestamp: str
    received_at: str
    source: str = "arduino"
    temperature_c: float | None = None
    humidity_pct: float | None = None
    bmp_temperature_c: float | None = None
    pressure_hpa: float | None = None
    rain_raw: float | None = None
    rain_pct: float | None = None
    ldr_raw: float | None = None
    light_pct: float | None = None
    air_quality_raw: float | None = None
    air_quality_index: float | None = None
    heat_index_c: float | None = None
    dew_point_c: float | None = None
    rain_status: str | None = None
    light_status: str | None = None
    air_quality_status: str | None = None
    risk_score: float | None = None
    risk_level: int | None = None
    risk_label: str | None = None
    risk_reasons: list[str] | None = None
    recommended_actions: list[str] | None = None
    risk_factors: list[dict[str, Any]] | None = None
    anomalies: list[dict[str, Any]] | None = None
    health_score: float | None = None
    is_stale: bool = False
    age_seconds: float | None = None
    missing_metrics: list[str] = Field(default_factory=list)


class IngestionResponse(BaseModel):
    """Response returned to the Arduino after POST /sensors/data."""

    success: bool
    accepted: bool
    message: str
    device_id: str
    reading_id: int | None = None
    timestamp: str | None = None
    duplicate: bool = False
    warnings: list[str] = Field(default_factory=list)
    rejected_fields: dict[str, str] = Field(default_factory=dict)
    missing_metrics: list[str] = Field(default_factory=list)
    sensor_health: float | None = None
    risk_score: float | None = None
    risk_level: int | None = None
    risk_label: str | None = None
    risk_reasons: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    alerts_created: int = 0
    processing_ms: float | None = None
    server_time: str | None = None


class SeriesPoint(BaseModel):
    timestamp: str
    value: float | None = None
    risk_score: float | None = None
    risk_level: int | None = None


class MetricSeries(BaseModel):
    metric: str
    label: str
    unit: str
    points: list[SeriesPoint] = Field(default_factory=list)
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    median: float | None = None
    p95: float | None = None
    stdev: float | None = None
    latest: float | None = None
    change: float | None = None
    change_pct: float | None = None
    slope_per_minute: float | None = None
    trend: str = "unknown"
    sample_count: int = 0
    r_squared: float | None = None


class HistoryResponse(BaseModel):
    device_id: str
    range_hours: float
    bucket: str | None = None
    count: int = 0
    from_timestamp: str | None = None
    to_timestamp: str | None = None
    readings: list[SensorReadingOut] = Field(default_factory=list)
    series: dict[str, MetricSeries] = Field(default_factory=dict)
    sufficient_data: bool = True
    notes: list[str] = Field(default_factory=list)


class AggregatePoint(BaseModel):
    bucket_start: str
    count: int
    temperature_c: float | None = None
    humidity_pct: float | None = None
    pressure_hpa: float | None = None
    air_quality_index: float | None = None
    light_pct: float | None = None
    rain_pct: float | None = None
    risk_score: float | None = None
    risk_level: float | None = None


class SummaryResponse(BaseModel):
    device_id: str
    period: str
    from_timestamp: str | None = None
    to_timestamp: str | None = None
    reading_count: int = 0
    coverage_pct: float | None = None
    #: metric -> {min, max, mean, median, p95, stdev, latest, change, trend}
    metrics: dict[str, dict[str, Any]] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)
    alerts: dict[str, int] = Field(default_factory=dict)
    anomalies_by_sensor: dict[str, int] = Field(default_factory=dict)
    highlights: list[str] = Field(default_factory=list)
