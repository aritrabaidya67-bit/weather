"""Device registration, telemetry tracking and online/offline determination."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.logging import get_logger
from ..core.realtime import bus
from ..models import Device, SensorReading
from ..repositories import DeviceRepository
from ..utils.timeutils import ensure_utc, humanize_seconds, utcnow

logger = get_logger("app.device")


def rssi_quality(rssi: int | None) -> str | None:
    """Rough Wi-Fi signal quality buckets (typical 2.4 GHz indoor figures)."""
    if rssi is None:
        return None
    if rssi >= -55:
        return "excellent"
    if rssi >= -65:
        return "good"
    if rssi >= -72:
        return "fair"
    if rssi >= -80:
        return "weak"
    return "very weak"


def humanize_uptime(uptime_ms: int | None) -> str | None:
    if uptime_ms is None:
        return None
    return humanize_seconds(uptime_ms / 1000.0)


class DeviceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.repository = DeviceRepository(session)

    # ------------------------------------------------------------------ writes
    def ensure(
        self,
        device_id: str,
        *,
        source: str = "arduino",
        display_name: str | None = None,
        firmware_version: str | None = None,
        ip_address: str | None = None,
    ) -> Device:
        defaults: dict[str, Any] = {
            "source": source,
            "display_name": display_name or self.settings.device_display_name,
        }
        if firmware_version:
            defaults["firmware_version"] = firmware_version
        if ip_address:
            defaults["ip_address"] = ip_address
        device = self.repository.get_or_create(device_id, **defaults)
        if source and device.source != source:
            device.source = source
        return device

    def record_payload(
        self,
        device: Device,
        *,
        reading: SensorReading,
        sensors_available: Sequence[str],
        sensors_missing: Sequence[str],
        risk_level: int | None,
        risk_score: float | None,
        now: datetime | None = None,
    ) -> None:
        now = now or utcnow()
        if device.last_sequence is not None and reading.sequence is not None:
            gap = reading.sequence - device.last_sequence - 1
            if gap > 0:
                device.missed_intervals += gap
                logger.warning(
                    "payload_sequence_gap",
                    device_id=device.device_id,
                    gap=gap,
                    expected_sequence=device.last_sequence + 1,
                    received_sequence=reading.sequence,
                )
        device.last_seen_at = now
        device.last_payload_at = now
        device.total_readings += 1
        device.sensors_available = list(sensors_available)
        device.sensors_missing = list(sensors_missing)
        device.source = reading.source
        device.last_risk_level = risk_level
        device.last_risk_score = risk_score
        device.last_risk_at = now
        if reading.firmware_version:
            device.firmware_version = reading.firmware_version
        if reading.ip_address:
            device.ip_address = reading.ip_address
        if reading.rssi is not None:
            device.rssi = reading.rssi
        if reading.uptime_ms is not None:
            device.uptime_ms = reading.uptime_ms
        if reading.transmission_interval_ms is not None:
            device.transmission_interval_ms = reading.transmission_interval_ms
        if reading.sequence is not None:
            device.last_sequence = reading.sequence
        device.notes = None
        self.session.flush()

    def note_rejected(self, device_id: str, reason: str) -> None:
        device = self.repository.get(device_id)
        if device is None:
            device = self.ensure(device_id)
        device.rejected_payloads += 1
        logger.warning("payload_rejected", device_id=device_id, reason=reason)
        self.session.flush()

    # ------------------------------------------------------------------- reads
    def _online(self, device: Device, now: datetime) -> tuple[bool, float | None]:
        last = ensure_utc(device.last_payload_at) or ensure_utc(device.last_seen_at)
        if last is None:
            return False, None
        age = (now - last).total_seconds()
        return age <= self.settings.device_online_threshold_seconds, age

    def status(self, device_id: str, *, include_sensor_health: bool = True) -> dict[str, Any]:
        from .analytics_service import AnalyticsService

        device = self.repository.get(device_id)
        now = utcnow()
        if device is None:
            return self._virtual_status(device_id, now)

        online, age = self._online(device, now)
        sensor_health = (
            AnalyticsService(self.session).sensor_health(device_id) if include_sensor_health else []
        )
        expected_interval = self.settings.expected_transmission_interval_seconds
        if device.transmission_interval_ms:
            expected_interval = max(1.0, device.transmission_interval_ms / 1000.0)
        delivered = device.total_readings
        expected_readings = delivered + max(0, device.missed_intervals)
        delivery_rate = (
            round(delivered / expected_readings * 100, 2) if expected_readings else None
        )
        notes: list[str] = []
        if not online:
            notes.append(
                "No payload received within the expected interval "
                f"({expected_interval:.0f} s). Check power, Wi-Fi and the backend address."
            )
        missing = list(device.sensors_missing or [])
        if missing:
            notes.append(
                "Sensors with no recent values: "
                + ", ".join(missing)
                + ". Check wiring/power for those sensors."
            )
        if device.source == "simulation":
            notes.append("This device is the built-in simulator, not physical hardware.")

        return {
            "device_id": device.device_id,
            "display_name": device.display_name,
            "online": online,
            "status": "online" if online else "offline",
            "status_message": (
                "Receiving data normally."
                if online
                else "Waiting for the Arduino UNO R4 Wi-Fi to send sensor data."
            ),
            "source": device.source,
            "firmware_version": device.firmware_version,
            "ip_address": device.ip_address,
            "rssi": device.rssi,
            "rssi_quality": rssi_quality(device.rssi),
            "uptime_ms": device.uptime_ms,
            "uptime_human": humanize_uptime(device.uptime_ms),
            "transmission_interval_ms": device.transmission_interval_ms,
            "transmission_interval_seconds": (
                round(device.transmission_interval_ms / 1000.0, 2)
                if device.transmission_interval_ms
                else None
            ),
            "expected_interval_seconds": expected_interval,
            "first_seen_at": (
                (ensure_utc(device.first_seen_at) or now).isoformat() if device.first_seen_at else None
            ),
            "last_seen_at": (
                (ensure_utc(device.last_seen_at) or now).isoformat() if device.last_seen_at else None
            ),
            "last_payload_at": (
                (ensure_utc(device.last_payload_at) or now).isoformat()
                if device.last_payload_at
                else None
            ),
            "seconds_since_last_payload": round(age, 1) if age is not None else None,
            "total_readings": device.total_readings,
            "rejected_payloads": device.rejected_payloads,
            "missed_intervals": device.missed_intervals,
            "estimated_delivery_rate_pct": delivery_rate,
            "sensors_available": list(device.sensors_available or []),
            "sensors_missing": missing,
            "sensor_health": sensor_health,
            "last_risk_score": device.last_risk_score,
            "last_risk_level": device.last_risk_level,
            "last_reading_at": (
                (ensure_utc(device.last_payload_at) or now).isoformat()
                if device.last_payload_at
                else None
            ),
            "notes": notes,
        }

    def _virtual_status(self, device_id: str, now: datetime) -> dict[str, Any]:
        """Status for a device that has never sent anything."""
        return {
            "device_id": device_id,
            "display_name": self.settings.device_display_name,
            "online": False,
            "status": "never_seen",
            "status_message": (
                "Waiting for the Arduino UNO R4 Wi-Fi to send sensor data. "
                "This is expected until the firmware is flashed or the simulator is started."
            ),
            "source": "unknown",
            "firmware_version": None,
            "ip_address": None,
            "rssi": None,
            "rssi_quality": None,
            "uptime_ms": None,
            "uptime_human": None,
            "transmission_interval_ms": None,
            "transmission_interval_seconds": None,
            "expected_interval_seconds": self.settings.expected_transmission_interval_seconds,
            "first_seen_at": None,
            "last_seen_at": None,
            "last_payload_at": None,
            "seconds_since_last_payload": None,
            "total_readings": 0,
            "rejected_payloads": 0,
            "missed_intervals": 0,
            "estimated_delivery_rate_pct": None,
            "sensors_available": [],
            "sensors_missing": [],
            "sensor_health": [],
            "last_risk_score": None,
            "last_risk_level": None,
            "last_reading_at": None,
            "notes": ["No data has ever been received from this device identifier."],
        }

    def list_devices(self) -> dict[str, Any]:
        devices = self.repository.list()
        now = utcnow()
        out = []
        for device in devices:
            online, age = self._online(device, now)
            payload = device.as_dict(online, round(age, 1) if age is not None else None)
            payload["rssi_quality"] = rssi_quality(device.rssi)
            payload["uptime_human"] = humanize_uptime(device.uptime_ms)
            payload["status"] = "online" if online else "offline"
            out.append(payload)
        if not out:
            out.append(self._virtual_status(self.settings.device_id, now))
        return {
            "count": len(out),
            "devices": out,
            "primary_device_id": self.primary_device_id(),
            "offline_message": (
                "Waiting for the Arduino UNO R4 Wi-Fi to send sensor data. "
                "Start the simulator or flash the firmware to populate the dashboard."
            ),
        }

    def primary_device_id(self) -> str:
        devices = self.repository.list()
        if not devices:
            return self.settings.device_id
        configured = self.repository.get(self.settings.device_id)
        if configured is not None:
            return configured.device_id
        return devices[0].device_id

    def offline_transitions(self) -> list[dict[str, Any]]:
        """Detect devices that just went offline (used by the watchdog task)."""
        now = utcnow()
        transitions: list[dict[str, Any]] = []
        for device in self.repository.list():
            online, age = self._online(device, now)
            if online or age is None:
                continue
            if device.notes == "OFFLINE_FLAGGED":
                continue
            device.notes = "OFFLINE_FLAGGED"
            transitions.append({"device_id": device.device_id, "age_seconds": age})
            logger.warning("device_went_offline", device_id=device.device_id, age_seconds=round(age, 1))
            bus.publish(
                "device",
                {
                    "device_id": device.device_id,
                    "online": False,
                    "status": "offline",
                    "seconds_since_last_payload": round(age, 1),
                },
            )
        if transitions:
            self.session.flush()
        return transitions

    def mark_online(self, device_id: str) -> None:
        device = self.repository.get(device_id)
        if device is not None and device.notes == "OFFLINE_FLAGGED":
            device.notes = None
            self.session.flush()
