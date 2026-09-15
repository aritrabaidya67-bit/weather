"""Rule-based alert engine.

Rules are declarative (see :data:`ALERT_RULES`) so the alert catalogue exposed at
``/api/v1/alerts/rules`` is generated from the same definitions that actually
fire. Alerts are de-duplicated by fingerprint with a cooldown window, increment an
occurrence counter instead of flooding the UI, and are automatically resolved
once the underlying condition stops holding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.logging import get_logger
from ..repositories import AlertRepository
from ..core.realtime import bus
from ..utils.timeutils import ensure_utc, humanize_seconds, utcnow

logger = get_logger("app.alerts")


@dataclass(frozen=True)
class AlertRule:
    id: str
    category: str
    severity: str
    title: str
    description: str
    condition: str
    default_action: str


ALERT_RULES: tuple[AlertRule, ...] = (
    AlertRule(
        id="risk_critical",
        category="risk_critical",
        severity="critical",
        title="Critical environmental risk",
        description="The composite risk score reached the critical band.",
        condition="risk_level >= 5",
        default_action="Act immediately and verify the readings on the physical device.",
    ),
    AlertRule(
        id="risk_high",
        category="risk_high",
        severity="warning",
        title="High environmental risk",
        description="The composite risk score reached the high band.",
        condition="risk_level == 4",
        default_action="Review the risk breakdown and apply the recommended actions.",
    ),
    AlertRule(
        id="air_quality_poor",
        category="air_quality",
        severity="warning",
        title="Air quality degraded",
        description="Relative air-quality index above the configured threshold.",
        condition="air_quality_index >= 50",
        default_action="Ventilate the space and remove pollutant sources.",
    ),
    AlertRule(
        id="air_quality_deteriorating",
        category="air_quality_trend",
        severity="warning",
        title="Air quality deteriorating",
        description="Air quality has been worsening continuously over the recent window.",
        condition="air_quality slope > 0.25 index/min",
        default_action="Increase ventilation and monitor the trend closely.",
    ),
    AlertRule(
        id="temperature_extreme",
        category="temperature",
        severity="warning",
        title="Abnormal temperature",
        description="Temperature outside the safe operating range.",
        condition="temperature >= 38 C or <= 0 C",
        default_action="Apply cooling/heating and check the sensor placement.",
    ),
    AlertRule(
        id="heat_stress",
        category="heat_stress",
        severity="warning",
        title="Heat stress conditions",
        description="Heat index (temperature x humidity combination) above 32 C.",
        condition="heat_index >= 32 C",
        default_action="Reduce heat load, increase hydration and ventilation.",
    ),
    AlertRule(
        id="humidity_extreme",
        category="humidity",
        severity="warning",
        title="Abnormal humidity",
        description="Humidity outside the 20-90 %RH band.",
        condition="humidity >= 90 %RH or <= 20 %RH",
        default_action="Ventilate or humidify as appropriate and watch for condensation.",
    ),
    AlertRule(
        id="pressure_rapid_drop",
        category="pressure",
        severity="warning",
        title="Rapid pressure drop",
        description="Barometric pressure falling quickly, typical of incoming weather.",
        condition="pressure change <= -4 hPa over 3 h",
        default_action="Secure outdoor equipment and expect unsettled weather.",
    ),
    AlertRule(
        id="rain_detected",
        category="rain",
        severity="info",
        title="Rain detected",
        description="The rain sensor reports wetness above the detection threshold.",
        condition="rain_pct >= 40",
        default_action="Protect the electronics enclosure from water ingress.",
    ),
    AlertRule(
        id="anomaly_detected",
        category="anomaly",
        severity="warning",
        title="Sensor anomaly detected",
        description="A reading deviates significantly from its recent baseline.",
        condition="anomaly severity == high",
        default_action="Verify the affected sensor wiring and placement.",
    ),
    AlertRule(
        id="sensor_failure",
        category="sensor_failure",
        severity="warning",
        title="Sensor not reporting",
        description="One or more sensors stopped delivering values.",
        condition="sensor health in (failed, stale, suspect)",
        default_action="Check the sensor wiring, power and connection.",
    ),
    AlertRule(
        id="device_offline",
        category="device_offline",
        severity="critical",
        title="Device offline",
        description="No sensor payload received within the expected interval.",
        condition="payload age > 3 x transmission interval",
        default_action="Check device power, Wi-Fi credentials and the backend IP/port.",
    ),
    AlertRule(
        id="prediction_warning",
        category="prediction",
        severity="info",
        title="Conditions forecast to worsen",
        description="The forecast projects a higher risk level than the current one.",
        condition="predicted risk level > current risk level",
        default_action="Prepare for deteriorating conditions over the forecast horizon.",
    ),
    AlertRule(
        id="simulation_mode",
        category="mode",
        severity="info",
        title="Simulation mode active",
        description="The backend is generating synthetic readings instead of receiving hardware data.",
        condition="SIMULATION_MODE=true",
        default_action="Remember that displayed values are simulated, not physical measurements.",
    ),
)

RULES_BY_ID = {rule.id: rule for rule in ALERT_RULES}


@dataclass
class AlertCandidate:
    category: str
    severity: str
    title: str
    message: str
    recommended_action: str
    sensor: str | None = None
    metric_value: float | None = None
    risk_level: int | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        return f"{self.category}:{self.sensor or 'device'}"


class AlertService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.repository = AlertRepository(session)

    # ------------------------------------------------------------------ public
    def evaluate(
        self,
        device_id: str,
        *,
        risk: dict[str, Any],
        metrics: dict[str, float | None],
        trend: dict[str, float | None],
        anomalies: Sequence[dict[str, Any]],
        sensor_health: Sequence[dict[str, Any]],
        predictions: dict[str, Any] | None = None,
        source: str = "arduino",
    ) -> list[dict[str, Any]]:
        candidates = self._candidates(
            risk=risk,
            metrics=metrics,
            trend=trend,
            anomalies=anomalies,
            sensor_health=sensor_health,
            predictions=predictions,
            source=source,
        )
        created = self._upsert(device_id, candidates)
        seen = {candidate.category for candidate in candidates}
        resolved = self.repository.resolve_missing(device_id, seen)
        if resolved:
            logger.info("alerts_resolved", device_id=device_id, count=resolved)
        return created

    def raise_device_offline(self, device_id: str, age_seconds: float | None) -> dict[str, Any] | None:
        rule = RULES_BY_ID["device_offline"]
        candidate = AlertCandidate(
            category=rule.category,
            severity=rule.severity,
            title=rule.title,
            message=(
                f"No sensor payload has been received for {humanize_seconds(age_seconds)} "
                f"(expected every {self.settings.expected_transmission_interval_seconds} s)."
            ),
            recommended_action=rule.default_action,
            context={"age_seconds": age_seconds},
        )
        created = self._upsert(device_id, [candidate])
        return created[0] if created else None

    def resolve_device_offline(self, device_id: str) -> int:
        alerts = self.repository.active_by_category(device_id, "device_offline")
        now = utcnow()
        for alert in alerts:
            alert.is_active = False
            alert.resolved_at = now
        if alerts:
            self.session.flush()
        return len(alerts)

    def raise_simulation_mode(self, device_id: str) -> dict[str, Any] | None:
        rule = RULES_BY_ID["simulation_mode"]
        candidate = AlertCandidate(
            category=rule.category,
            severity=rule.severity,
            title=rule.title,
            message=(
                "SIMULATION_MODE is enabled: readings are produced by the built-in simulator "
                "and are clearly marked as simulated throughout the API and UI."
            ),
            recommended_action=rule.default_action,
            context={"source": "simulation"},
        )
        created = self._upsert(device_id, [candidate])
        return created[0] if created else None

    def acknowledge(self, alert_id: int) -> dict[str, Any] | None:
        alert = self.repository.get(alert_id)
        if alert is None:
            return None
        alert.acknowledged_at = utcnow()
        self.session.flush()
        return alert.as_dict()

    # --------------------------------------------------------------- internals
    def _candidates(
        self,
        *,
        risk: dict[str, Any],
        metrics: dict[str, float | None],
        trend: dict[str, float | None],
        anomalies: Sequence[dict[str, Any]],
        sensor_health: Sequence[dict[str, Any]],
        predictions: dict[str, Any] | None,
        source: str,
    ) -> list[AlertCandidate]:
        candidates: list[AlertCandidate] = []
        level = int(risk.get("level", 1))
        score = float(risk.get("score", 0.0))

        if level >= 5:
            rule = RULES_BY_ID["risk_critical"]
            candidates.append(
                AlertCandidate(
                    category=rule.category,
                    severity=rule.severity,
                    title=rule.title,
                    message=(
                        f"Risk score {score:.0f}/100 ({risk.get('label')}). "
                        + "; ".join(risk.get("reasons", [])[:3])
                    ),
                    recommended_action="; ".join(risk.get("recommended_actions", [])[:2])
                    or rule.default_action,
                    risk_level=level,
                    metric_value=score,
                    context={"reasons": risk.get("reasons", [])},
                )
            )
        elif level == 4:
            rule = RULES_BY_ID["risk_high"]
            candidates.append(
                AlertCandidate(
                    category=rule.category,
                    severity=rule.severity,
                    title=rule.title,
                    message=(
                        f"Risk score {score:.0f}/100 ({risk.get('label')}). "
                        + "; ".join(risk.get("reasons", [])[:3])
                    ),
                    recommended_action="; ".join(risk.get("recommended_actions", [])[:2])
                    or rule.default_action,
                    risk_level=level,
                    metric_value=score,
                    context={"reasons": risk.get("reasons", [])},
                )
            )

        air = metrics.get("air_quality_index")
        if air is not None and air >= 50:
            rule = RULES_BY_ID["air_quality_poor"]
            candidates.append(
                AlertCandidate(
                    category=rule.category,
                    severity="critical" if air >= 80 else rule.severity,
                    title=rule.title,
                    message=(
                        f"Relative air-quality index is {air:.0f}/100 "
                        f"({'hazardous' if air >= 80 else 'poor'}). "
                        "This is a relative index from the MQ-135, not a calibrated ppm value."
                    ),
                    recommended_action=rule.default_action,
                    sensor="air_quality_index",
                    metric_value=air,
                    risk_level=level,
                )
            )
        slope = trend.get("air_quality_slope_per_minute")
        if slope is not None and slope > 0.25:
            rule = RULES_BY_ID["air_quality_deteriorating"]
            candidates.append(
                AlertCandidate(
                    category=rule.category,
                    severity=rule.severity,
                    title=rule.title,
                    message=(
                        f"The air-quality index is rising by {slope * 60:.1f} points per hour "
                        "over the recent window."
                    ),
                    recommended_action=rule.default_action,
                    sensor="air_quality_index",
                    metric_value=slope,
                    risk_level=level,
                    context={"slope_per_minute": slope},
                )
            )

        temperature = metrics.get("temperature_c")
        if temperature is not None and (temperature >= 38 or temperature <= 0):
            rule = RULES_BY_ID["temperature_extreme"]
            candidates.append(
                AlertCandidate(
                    category=rule.category,
                    severity="critical" if temperature >= 42 or temperature <= -10 else rule.severity,
                    title=rule.title,
                    message=f"Temperature is {temperature:.1f} degC, outside the safe operating range.",
                    recommended_action=rule.default_action,
                    sensor="temperature_c",
                    metric_value=temperature,
                    risk_level=level,
                )
            )

        heat_index = metrics.get("heat_index_c")
        if heat_index is not None and heat_index >= 32:
            rule = RULES_BY_ID["heat_stress"]
            candidates.append(
                AlertCandidate(
                    category=rule.category,
                    severity="critical" if heat_index >= 40 else rule.severity,
                    title=rule.title,
                    message=(
                        f"Heat index is {heat_index:.1f} degC (temperature {temperature:.1f} degC with "
                        f"{metrics.get('humidity_pct') or 0:.0f} %RH)."
                    ),
                    recommended_action=rule.default_action,
                    sensor="heat_index_c",
                    metric_value=heat_index,
                    risk_level=level,
                )
            )

        humidity = metrics.get("humidity_pct")
        if humidity is not None and (humidity >= 90 or humidity <= 20):
            rule = RULES_BY_ID["humidity_extreme"]
            candidates.append(
                AlertCandidate(
                    category=rule.category,
                    severity=rule.severity,
                    title=rule.title,
                    message=f"Relative humidity is {humidity:.0f} %RH.",
                    recommended_action=rule.default_action,
                    sensor="humidity_pct",
                    metric_value=humidity,
                    risk_level=level,
                )
            )

        pressure_change = trend.get("pressure_change_hpa_3h")
        if pressure_change is not None and pressure_change <= -4:
            rule = RULES_BY_ID["pressure_rapid_drop"]
            candidates.append(
                AlertCandidate(
                    category=rule.category,
                    severity="critical" if pressure_change <= -8 else rule.severity,
                    title=rule.title,
                    message=(
                        f"Pressure dropped {abs(pressure_change):.1f} hPa in the last 3 hours "
                        f"(currently {metrics.get('pressure_hpa') or 0:.1f} hPa)."
                    ),
                    recommended_action=rule.default_action,
                    sensor="pressure_hpa",
                    metric_value=pressure_change,
                    risk_level=level,
                )
            )

        rain = metrics.get("rain_pct")
        if rain is not None and rain >= 40:
            rule = RULES_BY_ID["rain_detected"]
            candidates.append(
                AlertCandidate(
                    category=rule.category,
                    severity="warning" if rain >= 75 else rule.severity,
                    title=rule.title if rain < 75 else "Heavy rain detected",
                    message=f"Rain sensor wetness is {rain:.0f} %.",
                    recommended_action=rule.default_action,
                    sensor="rain_pct",
                    metric_value=rain,
                    risk_level=level,
                )
            )

        high_anomalies = [a for a in anomalies if str(a.get("severity")) == "high"]
        if high_anomalies:
            rule = RULES_BY_ID["anomaly_detected"]
            for anomaly in high_anomalies[:3]:
                candidates.append(
                    AlertCandidate(
                        category=rule.category,
                        severity=rule.severity,
                        title=f"Anomaly: {anomaly.get('label', anomaly.get('sensor'))}",
                        message=str(anomaly.get("message", "Significant deviation from baseline.")),
                        recommended_action=rule.default_action,
                        sensor=str(anomaly.get("sensor")),
                        metric_value=anomaly.get("current_value"),
                        risk_level=level,
                        context={"anomaly": anomaly},
                    )
                )

        unhealthy = [
            item for item in sensor_health if str(item.get("status")) in ("failed", "stale", "suspect")
        ]
        if unhealthy:
            rule = RULES_BY_ID["sensor_failure"]
            for item in unhealthy[:4]:
                candidates.append(
                    AlertCandidate(
                        category=rule.category,
                        severity=rule.severity,
                        title=f"Sensor issue: {item.get('label')}",
                        message=str(item.get("message") or "Sensor is not reporting normally."),
                        recommended_action=rule.default_action,
                        sensor=str(item.get("key")),
                        risk_level=level,
                        context={"status": item.get("status")},
                    )
                )

        if predictions:
            risk_forecast = predictions.get("risk") or {}
            predicted_level = risk_forecast.get("predicted_level")
            current_level = risk_forecast.get("current_level")
            if (
                predicted_level is not None
                and current_level is not None
                and int(predicted_level) > int(current_level)
            ):
                rule = RULES_BY_ID["prediction_warning"]
                candidates.append(
                    AlertCandidate(
                        category=rule.category,
                        severity="warning" if int(predicted_level) >= 4 else rule.severity,
                        title=rule.title,
                        message=(
                            f"Forecast horizon {risk_forecast.get('horizon_minutes')} min: risk is expected "
                            f"to rise from level {current_level} to level {predicted_level} "
                            f"({risk_forecast.get('predicted_label')}). Drivers: "
                            f"{', '.join(risk_forecast.get('drivers') or ['mixed factors'])}."
                        ),
                        recommended_action=rule.default_action,
                        risk_level=int(predicted_level),
                        context={"forecast": risk_forecast},
                    )
                )
        _ = source
        return candidates

    def _upsert(self, device_id: str, candidates: Sequence[AlertCandidate]) -> list[dict[str, Any]]:
        created: list[dict[str, Any]] = []
        cooldown = self.settings.alerts.cooldown_minutes * 60
        now = utcnow()
        for candidate in candidates:
            existing = self.repository.find_recent_by_fingerprint(candidate.fingerprint, cooldown)
            if existing is not None:
                existing.occurrence_count += 1
                existing.last_seen_at = now
                existing.message = candidate.message
                existing.metric_value = candidate.metric_value
                existing.risk_level = candidate.risk_level
                existing.context = candidate.context
                existing.is_active = True
                existing.resolved_at = None
                self.session.flush()
                continue
            alert = self.repository.add(
                self._build_alert(device_id, candidate, now)
            )
            created.append(alert.as_dict())
            logger.info(
                "alert_created",
                category=candidate.category,
                severity=candidate.severity,
                device_id=device_id,
                sensor=candidate.sensor,
            )
            bus.publish("alert", alert.as_dict())
        if created:
            self.session.flush()
        return created

    def _build_alert(self, device_id: str, candidate: AlertCandidate, now):
        from ..models import Alert

        return Alert(
            fingerprint=candidate.fingerprint,
            device_id=device_id,
            category=candidate.category,
            severity=candidate.severity,
            title=candidate.title,
            message=candidate.message,
            sensor=candidate.sensor,
            metric_value=candidate.metric_value,
            risk_level=candidate.risk_level,
            recommended_action=candidate.recommended_action,
            context=candidate.context,
            is_active=True,
            occurrence_count=1,
            triggered_at=now,
            last_seen_at=now,
        )

    def catalogue(self) -> list[dict[str, Any]]:
        return [
            {
                "id": rule.id,
                "category": rule.category,
                "severity": rule.severity,
                "title": rule.title,
                "description": rule.description,
                "condition": rule.condition,
                "default_action": rule.default_action,
                "enabled": True,
            }
            for rule in ALERT_RULES
        ]

    def list(
        self,
        device_id: str | None,
        *,
        active_only: bool = False,
        severity: str | None = None,
        category: str | None = None,
        hours: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        since = None
        if hours:
            from datetime import timedelta

            since = utcnow() - timedelta(hours=hours)
        alerts = self.repository.list(
            device_id,
            active_only=active_only,
            severity=severity,
            category=category,
            since=since,
            limit=limit,
            offset=offset,
        )
        return {
            "device_id": device_id or "all",
            "active_count": self.repository.count(device_id, active_only=True),
            "total_count": self.repository.count(device_id),
            "severity_counts": self.repository.severity_counts(device_id, active_only=active_only),
            "category_counts": self.repository.category_counts(device_id),
            "alerts": [alert.as_dict() for alert in alerts],
            "notes": [] if alerts else ["No alerts match the current filter."],
        }

    def prune(self, older_than_days: int = 30) -> int:
        from datetime import timedelta

        cutoff = utcnow() - timedelta(days=older_than_days)
        rows = self.repository.list(limit=10000)
        removed = 0
        for alert in rows:
            last_seen = ensure_utc(alert.last_seen_at) or utcnow()
            if not alert.is_active and last_seen < cutoff:
                self.session.delete(alert)
                removed += 1
        if removed:
            self.session.flush()
        return removed
