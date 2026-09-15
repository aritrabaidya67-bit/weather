"""Sensor ingestion pipeline.

One code path handles every source: real Arduino firmware, the standalone
simulator process and the built-in demo generator all POST the same payload shape
into :meth:`SensorService.ingest`, so validation, normalisation, risk scoring,
anomaly detection, alerting, persistence and realtime publication cannot diverge
between "real" and "demo" operation.

Rejection policy (never silently accept garbage):

* a non-numeric value -> the field is rejected and reported
* a value outside the sensor's physical range -> the field is rejected and reported
* a payload with no usable measurement at all -> HTTP 422 with per-field reasons
* a duplicated payload (same sequence inside the duplicate window) -> acknowledged,
  not stored twice
* a stale or drifting timestamp -> corrected to server time with a warning
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.logging import get_logger
from ..core.realtime import bus
from ..core.sensors import CHANNELS, HARDWARE_FIELDS, REGISTRY
from ..models import SensorReading
from ..repositories import ReadingRepository
from ..schemas import SensorPayload
from ..utils import environment
from ..utils.timeutils import ensure_utc, parse_timestamp, utcnow
from .alert_service import AlertService
from .analytics_service import AnalyticsService
from .anomaly_service import AnomalyService
from .device_service import DeviceService
from .risk_service import RiskInputs, RiskService

logger = get_logger("app.ingest")


class IngestionRejected(Exception):
    """Raised when a payload cannot be used at all."""

    def __init__(
        self,
        detail: str,
        *,
        status_code: int = 422,
        rejected_fields: dict[str, str] | None = None,
        warnings: list[str] | None = None,
        device_id: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.rejected_fields = rejected_fields or {}
        self.warnings = warnings or []
        self.device_id = device_id


@dataclass
class _Normalised:
    metrics: dict[str, float | None] = field(default_factory=dict)
    statuses: dict[str, str | None] = field(default_factory=dict)
    rejected: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    unknown_fields: list[str] = field(default_factory=list)

    @property
    def reported_metrics(self) -> list[str]:
        return [key for key, value in self.metrics.items() if value is not None]

    @property
    def missing_channels(self) -> list[str]:
        return [
            channel
            for channel, spec in CHANNELS.items()
            if self.metrics.get(str(spec["primary"])) is None
        ]


class SensorService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.readings = ReadingRepository(session)
        self.analytics = AnalyticsService(session)
        self.risk = RiskService()
        self.anomalies = AnomalyService()
        self.devices = DeviceService(session)
        self.alerts = AlertService(session)

    # ------------------------------------------------------------------ ingest
    def ingest(
        self,
        payload: SensorPayload,
        *,
        raw_body: Mapping[str, Any] | None = None,
        client_ip: str | None = None,
        source_override: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        device_id = payload.device_id or self.settings.device_id
        source = source_override or payload.source or (
            "simulation" if device_id.startswith("simulator") else "arduino"
        )

        received_at = utcnow()
        measured_at, timestamp_warnings = self._resolve_timestamp(payload, received_at)
        normalised = self._normalise(payload)
        if not normalised.reported_metrics:
            self.devices.note_rejected(device_id, "no usable measurements")
            self.session.commit()
            raise IngestionRejected(
                "No usable measurements in payload.",
                status_code=422,
                rejected_fields=normalised.rejected,
                warnings=normalised.warnings,
                device_id=device_id,
            )

        device = self.devices.ensure(
            device_id,
            source=source,
            firmware_version=payload.firmware_version,
            ip_address=payload.ip_address,
        )

        if payload.sequence is not None:
            duplicate = self.readings.duplicate_exists(
                device_id, payload.sequence, self.settings.duplicate_window_seconds
            )
            if duplicate is not None:
                logger.info("duplicate_payload_ignored", device_id=device_id, sequence=payload.sequence)
                self.devices.mark_online(device_id)
                self.session.commit()
                return {
                    "success": True,
                    "accepted": False,
                    "message": "Duplicate payload ignored (same sequence inside the duplicate window).",
                    "device_id": device_id,
                    "reading_id": duplicate.id,
                    "timestamp": (ensure_utc(duplicate.received_at) or received_at).isoformat(),
                    "duplicate": True,
                    "warnings": ["Duplicate sequence number."],
                    "rejected_fields": {},
                    "missing_metrics": [],
                    "risk_score": duplicate.risk_score,
                    "risk_level": duplicate.risk_level,
                    "risk_label": duplicate.risk_label,
                    "risk_reasons": list(duplicate.risk_reasons or []),
                    "recommended_actions": list(duplicate.recommended_actions or []),
                    "anomalies": [],
                    "alerts_created": 0,
                    "processing_ms": round((time.perf_counter() - started) * 1000, 2),
                    "server_time": utcnow().isoformat(),
                }

        metrics = normalised.metrics
        derived = self._derive(metrics)
        # numeric derivations feed the analytics/risk engine, status strings are
        # only kept for the persisted row (the backend is authoritative).
        metrics.update({key: value for key, value in derived.items() if key in REGISTRY})
        # The backend-derived label wins (it is computed from the value we store),
        # and the firmware's own label is only used when a derivation was impossible.
        statuses = {
            key: derived.get(key) or normalised.statuses.get(key)
            for key in ("rain_status", "light_status", "air_quality_status")
        }

        # --- anomaly detection against the recent baseline ------------------
        history = self.readings.recent(device_id, limit=self.settings.anomaly.window_points + 5)
        anomalies = self.anomalies.detect(history, metrics)
        for anomaly in anomalies:
            bus.publish("anomaly", {"device_id": device_id, **anomaly})

        # --- risk scoring ---------------------------------------------------
        trend = self.analytics.trend_context(device_id, hours=3.0)
        missing_channels = normalised.missing_channels
        risk_inputs = RiskInputs(
            metrics=metrics,
            anomalies=anomalies,
            trend=trend,
            missing_metrics=[str(name) for name in missing_channels],
            data_age_seconds=0.0,
            source=source,
            heat_index_c=metrics.get("heat_index_c"),
        )
        assessment = self.risk.assess(risk_inputs)
        available_metrics = self._available_metrics(missing_channels)

        # --- persist --------------------------------------------------------
        reading = SensorReading(
            device_id=device_id,
            measured_at=measured_at,
            received_at=received_at,
            source=source,
            sequence=payload.sequence,
            temperature_c=metrics.get("temperature_c"),
            humidity_pct=metrics.get("humidity_pct"),
            bmp_temperature_c=metrics.get("bmp_temperature_c"),
            pressure_hpa=metrics.get("pressure_hpa"),
            rain_raw=metrics.get("rain_raw"),
            rain_pct=metrics.get("rain_pct"),
            ldr_raw=metrics.get("ldr_raw"),
            light_pct=metrics.get("light_pct"),
            air_quality_raw=metrics.get("air_quality_raw"),
            air_quality_index=metrics.get("air_quality_index"),
            heat_index_c=metrics.get("heat_index_c"),
            dew_point_c=metrics.get("dew_point_c"),
            rain_status=statuses.get("rain_status"),
            light_status=statuses.get("light_status"),
            air_quality_status=statuses.get("air_quality_status"),
            risk_score=assessment["score"],
            risk_level=assessment["level"],
            risk_label=assessment["label"],
            risk_factors=assessment["contributions"],
            risk_reasons=assessment["reasons"],
            recommended_actions=assessment["recommended_actions"],
            anomalies=anomalies,
            health_score=assessment["context"].get("health_score"),
            ip_address=payload.ip_address or client_ip,
            rssi=payload.rssi,
            uptime_ms=payload.uptime_ms,
            firmware_version=payload.firmware_version,
            transmission_interval_ms=payload.transmission_interval_ms,
            payload_bytes=len(str(raw_body)) if raw_body else None,
            raw_payload=dict(raw_body) if raw_body else None,
        )
        self.readings.add(reading)
        self.devices.record_payload(
            device,
            reading=reading,
            sensors_available=available_metrics,
            sensors_missing=[str(name) for name in missing_channels],
            risk_level=assessment["level"],
            risk_score=assessment["score"],
            now=received_at,
        )

        # --- alerts ---------------------------------------------------------
        created_alerts = self.alerts.evaluate(
            device_id,
            risk=assessment,
            metrics=metrics,
            trend=trend,
            anomalies=anomalies,
            sensor_health=self.analytics.sensor_health(device_id),
            source=source,
        )
        self.alerts.resolve_device_offline(device_id)
        if self.settings.simulation_mode and source == "simulation":
            self.alerts.raise_simulation_mode(device_id)

        self.session.commit()

        warnings = list(timestamp_warnings) + normalised.warnings
        warnings.extend(
            self._calibration_warnings(
                reported={
                    "rain_status": payload.rain_status,
                    "light_status": payload.light_status,
                    "air_quality_status": payload.air_quality_status,
                },
                derived={key: derived.get(key) for key in statuses},
            )
        )
        if normalised.rejected:
            warnings.insert(
                0,
                "Rejected "
                + ", ".join(f"{key} ({reason})" for key, reason in normalised.rejected.items()),
            )
        if missing_channels:
            warnings.append(
                "No value for: "
                + ", ".join(str(CHANNELS[channel]["label"]) for channel in missing_channels)
                + ". Those channels are recorded as missing rather than filled in."
            )

        processing_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "sensor_payload_ingested",
            device_id=device_id,
            reading_id=reading.id,
            source=source,
            metrics=len(normalised.reported_metrics),
            rejected=sorted(normalised.rejected),
            risk_score=assessment["score"],
            risk_level=assessment["level"],
            anomalies=len(anomalies),
            alerts=len(created_alerts),
            processing_ms=processing_ms,
        )

        response = {
            "success": True,
            "accepted": True,
            "message": "Sensor data accepted",
            "device_id": device_id,
            "reading_id": reading.id,
            "timestamp": measured_at.isoformat(),
            "duplicate": False,
            "warnings": warnings,
            "rejected_fields": normalised.rejected,
            "missing_metrics": [str(name) for name in missing_channels],
            "sensor_health": assessment["context"].get("health_score"),
            "risk_score": assessment["score"],
            "risk_level": assessment["level"],
            "risk_label": assessment["label"],
            "risk_reasons": assessment["reasons"],
            "recommended_actions": assessment["recommended_actions"],
            "anomalies": anomalies,
            "alerts_created": len(created_alerts),
            "processing_ms": processing_ms,
            "server_time": utcnow().isoformat(),
        }

        self._publish(
            device_id=device_id,
            source=source,
            reading=reading,
            assessment=assessment,
            anomalies=anomalies,
            created_alerts=created_alerts,
            metrics=metrics,
            statuses=statuses,
        )
        return response

    # ------------------------------------------------------------- normalise
    def _normalise(self, payload: SensorPayload) -> _Normalised:
        out = _Normalised()
        unknown = self._unknown_fields(payload)
        if unknown:
            out.unknown_fields = unknown
            out.warnings.append(
                "Ignored unrecognised field(s): " + ", ".join(sorted(unknown))
            )

        for key, spec in REGISTRY.items():
            raw = getattr(payload, key, None)
            if raw is None:
                out.metrics[key] = None
                continue
            value, error = self._coerce(raw, key)
            if error:
                out.rejected[key] = error
                out.metrics[key] = None
                continue
            assert value is not None
            if spec.minimum is not None and value < spec.minimum:
                out.rejected[key] = f"below physical minimum {spec.minimum} {spec.unit}"
                out.metrics[key] = None
                continue
            if spec.maximum is not None and value > spec.maximum:
                out.rejected[key] = f"above physical maximum {spec.maximum} {spec.unit}"
                out.metrics[key] = None
                continue
            out.metrics[key] = value

        # firmware-provided status strings are kept only if the matching
        # measurement is missing (otherwise the backend derives them itself)
        out.statuses = {
            "rain_status": payload.rain_status if out.metrics.get("rain_pct") is None else None,
            "light_status": payload.light_status if out.metrics.get("light_pct") is None else None,
            "air_quality_status": (
                payload.air_quality_status if out.metrics.get("air_quality_index") is None else None
            ),
        }
        return out

    def _unknown_fields(self, payload: SensorPayload) -> list[str]:
        known = set(REGISTRY) | set(HARDWARE_FIELDS) | {
            "device_id",
            "timestamp",
            "sequence",
            "firmware_version",
            "uptime_ms",
            "ip_address",
            "rssi",
            "transmission_interval_ms",
            "source",
            "sensors_available",
            "sensors_missing",
            "rain_status",
            "light_status",
            "air_quality_status",
        }
        extra = getattr(payload, "model_extra", None) or {}
        return [key for key in extra if key not in known]

    def _coerce(self, raw: Any, key: str) -> tuple[float | None, str | None]:
        if isinstance(raw, bool):
            return None, "boolean value is not a measurement"
        if isinstance(raw, (int, float)):
            value = float(raw)
        elif isinstance(raw, str):
            try:
                value = float(raw.strip())
            except ValueError:
                return None, "not a number"
        else:
            return None, f"unsupported type {type(raw).__name__}"
        if math.isnan(value) or math.isinf(value):
            return None, "not a finite number"
        spec = REGISTRY[key]
        value = round(value, max(0, spec.decimals + 2))
        return value, None

    def _resolve_timestamp(
        self, payload: SensorPayload, received_at: Any
    ) -> tuple[Any, list[str]]:
        warnings: list[str] = []
        parsed = parse_timestamp(payload.timestamp)
        if parsed is None:
            if payload.timestamp is not None:
                warnings.append(
                    "Unparsable timestamp provided; server receive time was used instead."
                )
            return received_at, warnings
        drift = (parsed - received_at).total_seconds()
        skew = self.settings.max_timestamp_skew_seconds
        if abs(drift) > skew:
            warnings.append(
                f"Device clock drift of {drift:.0f} s ignored (limit {skew} s); "
                "server receive time was used."
            )
            return received_at, warnings
        if drift > 0:
            # A device clock slightly ahead of the server is fine but confusing
            # for charts; record the server time instead.
            return received_at, warnings
        return parsed, warnings

    def _derive(self, metrics: dict[str, float | None]) -> dict[str, float | None]:
        settings = self.settings
        rain_pct = metrics.get("rain_pct")
        if rain_pct is None:
            rain_pct = environment.rain_pct_from_raw(
                metrics.get("rain_raw"), settings.rain_dry_adc, settings.rain_wet_adc
            )
        light_pct = metrics.get("light_pct")
        if light_pct is None:
            light_pct = environment.light_pct_from_raw(
                metrics.get("ldr_raw"), settings.light_dark_adc, settings.light_bright_adc
            )
        air_index = metrics.get("air_quality_index")
        if air_index is None:
            air_index = environment.air_quality_index_from_raw(
                metrics.get("air_quality_raw"),
                settings.air_quality_clean_baseline,
                settings.air_quality_max_reference,
            )
        temperature = metrics.get("temperature_c")
        humidity = metrics.get("humidity_pct")
        return {
            "rain_pct": rain_pct,
            "rain_status": environment.rain_status(rain_pct),
            "light_pct": light_pct,
            "light_status": environment.light_status(light_pct),
            "air_quality_index": air_index,
            "air_quality_status": environment.air_quality_status(air_index),
            "heat_index_c": environment.heat_index_c(temperature, humidity),
            "dew_point_c": environment.dew_point_c(temperature, humidity),
        }

    def _calibration_warnings(
        self, *, reported: dict[str, str | None], derived: dict[str, str | None]
    ) -> list[str]:
        """Surface firmware/backend calibration disagreements instead of hiding them.

        The backend derives rain/light/air-quality labels from raw ADC counts using
        configurable calibration constants. If the firmware's own label disagrees, the
        most likely cause is that the calibration constants do not match the physical
        board yet - saying so is far more useful than silently overwriting either value.
        """
        messages: list[str] = []
        pairs = (
            ("rain_status", "rain", "RAIN_DRY_ADC / RAIN_WET_ADC"),
            ("light_status", "light", "LIGHT_DARK_ADC / LIGHT_BRIGHT_ADC"),
            (
                "air_quality_status",
                "air quality",
                "AIR_QUALITY_CLEAN_BASELINE / AIR_QUALITY_MAX_REFERENCE",
            ),
        )
        for key, label, settings_names in pairs:
            device_value = (reported.get(key) or "").strip().lower()
            derived_value = (derived.get(key) or "").strip().lower()
            if not device_value or not derived_value or device_value == derived_value:
                continue
            messages.append(
                f"Firmware reported {label} status '{device_value}' while the backend derived "
                f"'{derived_value}' from the raw value. Check the {settings_names} calibration "
                "in backend/.env against the physical board."
            )
        return messages

    def _available_metrics(self, missing_channels: list[str]) -> list[str]:
        return [
            str(CHANNELS[channel]["primary"])
            for channel in CHANNELS
            if channel not in missing_channels
        ]

    # -------------------------------------------------------------- realtime
    def _publish(
        self,
        *,
        device_id: str,
        source: str,
        reading: SensorReading,
        assessment: dict[str, Any],
        anomalies: list[dict[str, Any]],
        created_alerts: list[dict[str, Any]],
        metrics: dict[str, float | None],
        statuses: dict[str, str | None],
    ) -> None:
        served_statuses = {key: value for key, value in statuses.items() if value}
        bus.publish(
            "reading",
            {
                "device_id": device_id,
                "reading_id": reading.id,
                "source": source,
                "timestamp": reading.measured_at.isoformat(),
                "received_at": reading.received_at.isoformat(),
                "simulated": source == "simulation",
                "metrics": {
                    key: metrics.get(key)
                    for key in (
                        "temperature_c",
                        "humidity_pct",
                        "bmp_temperature_c",
                        "pressure_hpa",
                        "rain_raw",
                        "rain_pct",
                        "ldr_raw",
                        "light_pct",
                        "air_quality_raw",
                        "air_quality_index",
                        "heat_index_c",
                        "dew_point_c",
                    )
                },
                "statuses": served_statuses,
                "risk_score": assessment["score"],
                "risk_level": assessment["level"],
                "risk_label": assessment["label"],
                "health_score": assessment["context"].get("health_score"),
                "anomalies": anomalies,
            },
        )
        bus.publish("risk", {"device_id": device_id, **assessment})
        if created_alerts:
            bus.publish(
                "alert",
                {"device_id": device_id, "created": len(created_alerts), "alerts": created_alerts},
            )
        bus.publish(
            "device",
            {
                "device_id": device_id,
                "online": True,
                "status": "online",
                "source": source,
                "last_payload_at": reading.received_at.isoformat(),
            },
        )

