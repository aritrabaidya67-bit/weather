"""Time-series table for normalised sensor readings."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Float, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base, UTCDateTime


def utcnow() -> datetime:
    return datetime.now(UTC)


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    #: Timestamp reported by the device (may be absent -> falls back to received_at).
    measured_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    #: Timestamp the backend persisted the reading (authoritative for latency).
    received_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, index=True
    )
    source: Mapped[str] = mapped_column(String(16), default="arduino")
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- raw measurements (nullable: a disconnected sensor simply has no value) ---
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    bmp_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_hpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    rain_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    rain_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    ldr_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    light_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    air_quality_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    air_quality_index: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- derived environmental metrics ---
    heat_index_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    dew_point_c: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- classification strings reported/derived by the edge device ---
    rain_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    light_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    air_quality_status: Mapped[str | None] = mapped_column(String(24), nullable=True)

    # --- assessment results (denormalised for fast history queries) ---
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    risk_level: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    risk_label: Mapped[str | None] = mapped_column(String(24), nullable=True)
    risk_factors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    risk_reasons: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    recommended_actions: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    anomalies: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    health_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- device telemetry -------------------------------------------------
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uptime_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    transmission_interval_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- audit ------------------------------------------------------------
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_reading_device_received", "device_id", "received_at"),
        Index("ix_reading_device_measured", "device_id", "measured_at"),
    )

    def as_series_point(self) -> dict[str, Any]:
        """Compact representation used by charts."""
        return {
            "id": self.id,
            "timestamp": (self.measured_at or self.received_at).isoformat(),
            "received_at": self.received_at.isoformat(),
            "source": self.source,
            "temperature_c": self.temperature_c,
            "humidity_pct": self.humidity_pct,
            "bmp_temperature_c": self.bmp_temperature_c,
            "pressure_hpa": self.pressure_hpa,
            "rain_raw": self.rain_raw,
            "rain_pct": self.rain_pct,
            "ldr_raw": self.ldr_raw,
            "light_pct": self.light_pct,
            "air_quality_raw": self.air_quality_raw,
            "air_quality_index": self.air_quality_index,
            "heat_index_c": self.heat_index_c,
            "dew_point_c": self.dew_point_c,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "risk_label": self.risk_label,
        }
