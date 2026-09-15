"""Registered edge devices and their last known telemetry."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base, UTCDateTime
from .reading import utcnow


class Device(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uptime_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transmission_interval_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="arduino")
    sensors_available: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    sensors_missing: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Internal bookkeeping only: set to OFFLINE_FLAGGED when the watchdog has
    # already raised an offline alert for this device, and cleared on the next
    # payload. This is NOT the API's ``notes`` field -- ``DeviceOut.notes`` is a
    # list of human-readable strings. The two must never be conflated: leaking
    # this sentinel into the response broke ``GET /device/list`` with a
    # validation error, so the attribute is named explicitly for its purpose
    # while the physical column name (``notes``) is kept to avoid schema drift.
    offline_flag: Mapped[str | None] = mapped_column("notes", Text, nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_payload_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    total_readings: Mapped[int] = mapped_column(Integer, default=0)
    rejected_payloads: Mapped[int] = mapped_column(Integer, default=0)
    missed_intervals: Mapped[int] = mapped_column(Integer, default=0)
    last_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_risk_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_risk_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    def as_dict(
        self,
        online: bool,
        seconds_since_seen: float | None,
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Serialise for the API.

        ``notes`` is the human-readable list built by ``DeviceService``; the
        internal ``offline_flag`` sentinel is deliberately never exposed.
        """
        return {
            "device_id": self.device_id,
            "display_name": self.display_name,
            "firmware_version": self.firmware_version,
            "ip_address": self.ip_address,
            "rssi": self.rssi,
            "uptime_ms": self.uptime_ms,
            "transmission_interval_ms": self.transmission_interval_ms,
            "source": self.source,
            "sensors_available": self.sensors_available or [],
            "sensors_missing": self.sensors_missing or [],
            "notes": list(notes or []),
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "last_payload_at": self.last_payload_at.isoformat() if self.last_payload_at else None,
            "total_readings": self.total_readings,
            "rejected_payloads": self.rejected_payloads,
            "missed_intervals": self.missed_intervals,
            "last_sequence": self.last_sequence,
            "last_risk_level": self.last_risk_level,
            "online": online,
            "seconds_since_last_payload": seconds_since_seen,
        }
