"""Explainable, configurable environmental risk scoring.

The score is deliberately transparent: every factor earns a fraction of a fixed
weight budget and the per-factor points are returned to the client, so a user can
always answer "why is the score 78?". Weights and bands live in
:class:`~app.core.config.RiskConfig` and can be replaced wholesale through the
``RISK_CONFIG_FILE`` environment variable.

Score construction::

    score = clamp( sum(weight_i * fraction_i) + sum(combination_points) , 0, 100 )

where ``fraction_i`` is looked up in the factor's band table, optionally
escalated by a trend rule (rapid pressure drop, steadily worsening air quality).
The nominal weights sum to exactly 100, so a score of 100 means "every factor at
its worst" and the factor points visible in the UI add up to the score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.config import RiskConfig, RiskLevelSpec, get_risk_config
from ..core.logging import get_logger
from ..core.sensors import CHANNELS, REGISTRY
from ..utils.stats import clamp
from ..utils.timeutils import utcnow

logger = get_logger("app.risk")

#: Physical indicator mapping. The firmware implements the same table, so LED 4
#: always means "high risk" on the device and on the dashboard.
#:
#: 1 silent | 2 silent | 3 one short beep every 60 s | 4 two short beeps every 30 s
#: 5 continuous critical alarm pattern (repeating 3-tone burst)
BUZZER_PATTERNS: dict[int, str] = {
    1: "silent",
    2: "silent",
    3: "single_short_60s",
    4: "double_short_30s",
    5: "critical_alarm",
}

FACTOR_METRIC: dict[str, str] = {
    "air_quality": "air_quality_index",
    "temperature": "temperature_c",
    "humidity": "humidity_pct",
    "pressure": "pressure_hpa",
    "rain": "rain_pct",
    "light": "light_pct",
}

FACTOR_FALLBACK: dict[str, str] = {"temperature": "bmp_temperature_c"}

ACTION_LIBRARY: dict[str, dict[str, str]] = {
    "air_quality": {
        "high": "Improve ventilation and remove pollutant sources (smoke, aerosols, cooking fumes)",
        "medium": "Monitor air quality closely and ventilate the space periodically",
        "calibration": (
            "If the air-quality index stays high in demonstrably clean air, "
            "re-calibrate the MQ-135 baseline"
        ),
    },
    "temperature": {
        "high": "Reduce the heat load: ventilate, shade or cool the space",
        "low": "Heat the space and check insulation / drafts",
        "watch": "Watch the temperature trend and keep the space in the comfort band",
    },
    "humidity": {
        "high": "Ventilate to bring humidity down and consider a dehumidifier",
        "low": "Raise humidity slightly (plants, humidifier) and stay hydrated",
        "watch": "Keep humidity inside the 30-60 %RH comfort band",
    },
    "pressure": {
        "falling": "Monitor the weather: a rapid pressure drop often precedes a storm",
        "low": "Expect unsettled weather; secure outdoor equipment and the sensor node",
        "watch": "Track the pressure trend for early warning of weather changes",
    },
    "rain": {
        "rain": "Protect electronics and the sensor enclosure from water ingress",
        "watch": "Check the rain sensor shield and drains around the node",
    },
    "light": {
        "low": "Light level is low; this is informational unless work requires illumination",
        "watch": "Check the LDR is not blocked or covered if the reading looks wrong",
    },
    "composite": {
        "anomaly": "Investigate the flagged sensor: verify wiring and calibration",
        "missing": "Check the disconnected sensor(s) and their wiring",
        "stale": "No fresh data: verify the Arduino is powered and on the same Wi-Fi network",
    },
}

LEVEL_GENERIC_ACTIONS: dict[int, str] = {
    3: "Keep monitoring; no immediate action required unless conditions worsen",
    4: "Review the alert centre and confirm the readings on the physical device",
    5: "Treat as an emergency: act now and re-check the device LEDs and buzzer",
}


@dataclass
class RiskInputs:
    metrics: dict[str, float | None]
    anomalies: list[dict[str, Any]] = field(default_factory=list)
    trend: dict[str, float | None] = field(default_factory=dict)
    missing_metrics: list[str] = field(default_factory=list)
    data_age_seconds: float | None = None
    source: str = "arduino"
    heat_index_c: float | None = None


class RiskService:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or get_risk_config()

    # ------------------------------------------------------------------ levels
    def level_for(self, score: float) -> RiskLevelSpec:
        ordered = sorted(self.config.levels, key=lambda item: item.min_score)
        chosen = ordered[0]
        for level in ordered:
            if score >= level.min_score:
                chosen = level
        return chosen

    def level_by_number(self, level: int) -> RiskLevelSpec:
        for spec in self.config.levels:
            if spec.level == level:
                return spec
        return sorted(self.config.levels, key=lambda item: item.min_score)[0]

    @property
    def led_count(self) -> int:
        return len(self.config.levels)

    def max_score_for(self, level: int) -> float:
        ordered = sorted(self.config.levels, key=lambda item: item.min_score)
        for index, spec in enumerate(ordered):
            if spec.level == level:
                if index + 1 < len(ordered):
                    return ordered[index + 1].min_score - 1
                return 100.0
        return 100.0

    # ----------------------------------------------------------------- assess
    def assess(self, inputs: RiskInputs) -> dict[str, Any]:
        metrics = inputs.metrics
        contributions: list[dict[str, Any]] = []
        reasons: list[str] = []
        reducing: list[str] = []
        actions: list[str] = []
        score = 0.0

        for factor in self.config.factors:
            if factor.key == "composite":
                continue
            metric_key = FACTOR_METRIC.get(factor.key)
            if metric_key is None:
                continue
            reading = metrics.get(metric_key)
            if reading is None:
                reading = metrics.get(FACTOR_FALLBACK.get(factor.key, ""))
            spec = REGISTRY.get(metric_key)
            if reading is None or spec is None:
                continue

            fraction, reason = self._band_fraction(factor.bands, reading)
            reason_texts: list[str] = []
            if reason:
                reason_texts.append(reason)

            boosted = self._escalate(factor.key, fraction, inputs.trend)
            if boosted is not None:
                fraction, boost_reason = boosted
                if boost_reason:
                    reason_texts.append(boost_reason)

            fraction = clamp(fraction, 0.0, 1.0)
            points = round(factor.weight * fraction, 2)
            score += points
            label, severity = spec.interpret(reading)
            contributions.append(
                {
                    "key": factor.key,
                    "label": factor.label,
                    "points": points,
                    "max_points": factor.weight,
                    "weight": factor.weight,
                    "normalised": round(fraction, 3),
                    "reading": round(float(reading), 3),
                    "unit": spec.unit,
                    "severity": severity,
                    "reason": reason_texts[0] if reason_texts else None,
                    "direction": "increasing" if points > 0.5 else "reducing",
                }
            )
            if points > 0.5:
                reasons.extend(reason_texts or [f"{factor.label} is outside its comfort band"])
            else:
                reducing.append(reason_texts[0] if reason_texts else f"{factor.label} is in range")

            self._append_actions(actions, factor.key, reading, points)

        # --- cross-sensor combination rules -------------------------------
        for rule in self.config.combination_rules:
            if not self._rule_matches(rule.conditions, metrics):
                continue
            # ``format_map`` with a permissive mapping: a rule template may
            # reference a metric that is missing from a partial payload, and a
            # missing value must never take the whole assessment down.
            reason = rule.reason.format_map(_MetricFormatMap(metrics))
            score += rule.points
            contributions.append(
                {
                    "key": rule.id,
                    "label": rule.label,
                    "points": round(rule.points, 2),
                    "max_points": rule.points,
                    "weight": rule.points,
                    "normalised": 1.0,
                    "reading": None,
                    "unit": None,
                    "severity": "warning",
                    "reason": reason,
                    "direction": "increasing",
                }
            )
            reasons.append(reason)
            if rule.action not in actions:
                actions.append(rule.action)

        # --- composite factor: anomalies, sensor health, staleness --------
        composite_points, composite_reasons, composite_actions = self._composite(inputs)
        score += composite_points
        composite_factor = next((f for f in self.config.factors if f.key == "composite"), None)
        contributions.append(
            {
                "key": "composite",
                "label": composite_factor.label if composite_factor else "Anomalies & sensor health",
                "points": round(composite_points, 2),
                "max_points": composite_factor.weight if composite_factor else 10.0,
                "weight": composite_factor.weight if composite_factor else 10.0,
                "normalised": round(
                    composite_points / (composite_factor.weight if composite_factor else 10.0), 3
                ),
                "reading": len(inputs.anomalies) or None,
                "unit": None,
                "severity": "critical" if composite_points > 6 else ("watch" if composite_points > 0 else "good"),
                "reason": composite_reasons[0] if composite_reasons else "No anomalies and all sensors reporting",
                "direction": "increasing" if composite_points > 0.5 else "reducing",
            }
        )
        if composite_points > 0.5:
            reasons.extend(composite_reasons)
        else:
            reducing.append("No anomalies detected and all expected sensors are reporting")
        actions.extend(composite_actions)

        score = round(clamp(score, 0.0, 100.0), 1)
        level_spec = self.level_for(score)

        # --- description of the data we actually had ----------------------
        present = [key for key in CHANNELS if metrics.get(CHANNELS[key]["primary"]) is not None]
        coverage = round(len(present) / len(CHANNELS), 3)
        health = self._health_score(inputs)
        stale = (
            inputs.data_age_seconds is not None
            and inputs.data_age_seconds > max(90.0, 3 * 15)
        )
        confidence = round(clamp(coverage * (0.75 if stale else 1.0), 0.15, 1.0), 3)

        if level_spec.level >= 4:
            extra = LEVEL_GENERIC_ACTIONS.get(level_spec.level)
            if extra:
                actions.append(extra)
        elif level_spec.level == 3:
            actions.append(LEVEL_GENERIC_ACTIONS[3])

        deduped_actions = _dedupe_preserve_order(actions)[:6]
        top_reasons = _dedupe_preserve_order(reasons)[:5]
        reduce_list = _dedupe_preserve_order(reducing)[:3]

        if not top_reasons:
            top_reasons = ["All monitored factors are inside their comfort bands"]

        assessment = {
            "score": score,
            "level": level_spec.level,
            "label": level_spec.label,
            "code": level_spec.code,
            "color": level_spec.color,
            "description": level_spec.description,
            "confidence": confidence,
            "reasons": top_reasons,
            "reducing_factors": reduce_list,
            "recommended_actions": deduped_actions,
            "contributions": sorted(contributions, key=lambda c: c["points"], reverse=True),
            "data_coverage": coverage,
            "missing_metrics": inputs.missing_metrics,
            "model_version": self.config.version,
            "evaluated_at": utcnow().isoformat(),
            "context": {
                "source": inputs.source,
                "health_score": health,
                "stale": stale,
                "data_age_seconds": inputs.data_age_seconds,
                "heat_index_c": inputs.heat_index_c,
                "led_index": level_spec.level,
                "buzzer_pattern": BUZZER_PATTERNS.get(level_spec.level, "silent"),
            },
        }
        logger.debug(
            "risk_calculated",
            score=score,
            level=level_spec.level,
            label=level_spec.label,
            reasons=len(top_reasons),
        )
        return assessment

    # ---------------------------------------------------------------- helpers
    def _band_fraction(self, bands: list[Any], reading: float) -> tuple[float, str | None]:
        for band in bands:
            if reading <= band.until:
                return band.points, band.reason
        if bands:
            return bands[-1].points, bands[-1].reason
        return 0.0, None

    def _escalate(
        self, factor_key: str, fraction: float, trend: dict[str, float | None]
    ) -> tuple[float, str] | None:
        """Trend-based escalation. Returns (fraction, reason) when it applies."""
        if factor_key == "pressure":
            change = trend.get("pressure_change_hpa_3h")
            if change is not None and change < 0:
                drop = -change
                for rule in sorted(
                    self.config.pressure_drop_escalation, key=lambda r: r["drop_hpa"]
                ):
                    if drop >= rule["drop_hpa"] and fraction < rule["points"]:
                        return (
                            rule["points"],
                            f"Pressure has dropped {drop:.1f} hPa in the last 3 hours",
                        )
        if factor_key == "air_quality":
            slope = trend.get("air_quality_slope_per_minute")
            if slope is not None and slope > 0:
                for rule in sorted(
                    self.config.air_quality_worsening_escalation,
                    key=lambda r: r["slope_per_minute"],
                ):
                    if slope >= rule["slope_per_minute"] and fraction < rule["points"]:
                        return (
                            rule["points"],
                            "Air quality has been deteriorating continuously over the recent window",
                        )
        return None

    def _rule_matches(
        self, conditions: dict[str, dict[str, float]], metrics: dict[str, float | None]
    ) -> bool:
        for metric, bounds in conditions.items():
            value = metrics.get(metric)
            if value is None:
                return False
            if "min" in bounds and value < bounds["min"]:
                return False
            if "max" in bounds and value > bounds["max"]:
                return False
        return True

    def _composite(self, inputs: RiskInputs) -> tuple[float, list[str], list[str]]:
        reasons: list[str] = []
        actions: list[str] = []
        points = 0.0
        weight = next((f.weight for f in self.config.factors if f.key == "composite"), 10.0)

        per_severity = {"high": 0, "medium": 0, "low": 0}
        for anomaly in inputs.anomalies:
            severity = str(anomaly.get("severity", "low"))
            per_severity[severity] = per_severity.get(severity, 0) + 1

        if per_severity["high"]:
            points += per_severity["high"] * self.config.anomaly_penalty_per_high * weight
            reasons.append(
                f"{per_severity['high']} high-severity sensor anomal"
                f"{'y' if per_severity['high'] == 1 else 'ies'} detected"
            )
            actions.append(ACTION_LIBRARY["composite"]["anomaly"])
        if per_severity["medium"]:
            points += per_severity["medium"] * self.config.anomaly_penalty_per_medium * weight
            reasons.append(
                f"{per_severity['medium']} moderate sensor anomal"
                f"{'y' if per_severity['medium'] == 1 else 'ies'} detected"
            )
        if per_severity["low"]:
            points += per_severity["low"] * self.config.anomaly_penalty_per_low * weight

        missing = [m for m in inputs.missing_metrics if m in CHANNELS]
        if missing:
            points += len(missing) * self.config.sensor_failure_penalty_per_sensor * weight
            labels = ", ".join(str(CHANNELS[m]["label"]) for m in missing)
            reasons.append(f"Sensor(s) not reporting: {labels}")
            actions.append(ACTION_LIBRARY["composite"]["missing"])

        if (
            inputs.data_age_seconds is not None
            and inputs.data_age_seconds > 120
        ):
            points += self.config.stale_data_penalty * weight
            reasons.append("Latest reading is stale (data may not reflect current conditions)")
            actions.append(ACTION_LIBRARY["composite"]["stale"])

        return clamp(min(points, weight), 0.0, weight), reasons, actions

    def _health_score(self, inputs: RiskInputs) -> float:
        present = sum(
            1 for key in CHANNELS if inputs.metrics.get(CHANNELS[key]["primary"]) is not None
        )
        base = (present / len(CHANNELS)) * 100
        penalty = min(40.0, len(inputs.anomalies) * 8.0)
        return round(clamp(base - penalty, 0.0, 100.0), 1)

    def _append_actions(
        self, actions: list[str], factor_key: str, reading: float, points: float
    ) -> None:
        if points <= 0.5:
            return
        library = ACTION_LIBRARY.get(factor_key, {})
        if factor_key == "temperature":
            actions.append(library["high"] if reading >= 26 else library["low"])
        elif factor_key == "humidity":
            actions.append(library["high"] if reading > 60 else library["low"])
        elif factor_key == "pressure":
            if reading < 1000:
                actions.append(library["low"])
            else:
                actions.append(library["watch"])
        elif factor_key == "rain":
            actions.append(library["rain"] if reading >= 40 else library["watch"])
        elif factor_key == "light":
            actions.append(library["low"])
        elif factor_key == "air_quality":
            actions.append(library["high"] if reading >= 50 else library["medium"])
            if reading >= 75:
                actions.append(library["calibration"])

    # ------------------------------------------------------------- responses
    def to_state_payload(
        self,
        assessment: dict[str, Any],
        *,
        device_id: str,
        stale: bool,
        age_seconds: float | None,
        data_source: str,
        alerts_active: int = 0,
    ) -> dict[str, Any]:
        level = int(assessment.get("level", 1))
        return {
            "device_id": device_id,
            "risk_score": float(assessment.get("score", 0.0)),
            "risk_level": level,
            "risk_label": str(assessment.get("label", "Unknown")),
            "risk_code": str(assessment.get("code", "UNKNOWN")),
            "color": str(assessment.get("color", "#22c55e")),
            "led_index": min(max(level, 1), self.led_count),
            "buzzer_pattern": BUZZER_PATTERNS.get(level, "silent"),
            "reasons": list(assessment.get("reasons", [])),
            "recommended_actions": list(assessment.get("recommended_actions", [])),
            "stale": stale,
            "age_seconds": age_seconds,
            "data_source": data_source,
            "evaluated_at": assessment.get("evaluated_at"),
            "alerts_active": alerts_active,
            "server_time": utcnow().isoformat(),
        }

    def model_description(self) -> dict[str, Any]:
        levels = []
        ordered = sorted(self.config.levels, key=lambda item: item.min_score)
        for index, spec in enumerate(ordered):
            upper = (
                ordered[index + 1].min_score - 1
                if index + 1 < len(ordered)
                else 100.0
            )
            levels.append(
                {
                    "level": spec.level,
                    "code": spec.code,
                    "label": spec.label,
                    "min_score": spec.min_score,
                    "max_score": upper,
                    "description": spec.description,
                    "color": spec.color,
                    "led_index": spec.level,
                    "buzzer_pattern": BUZZER_PATTERNS.get(spec.level, "silent"),
                }
            )
        factors = []
        for factor in self.config.factors:
            entry: dict[str, Any] = {
                "key": factor.key,
                "label": factor.label,
                "weight": factor.weight,
                "metric": FACTOR_METRIC.get(factor.key),
                "bands": [band.model_dump() for band in factor.bands],
                "note": factor.note,
            }
            factors.append(entry)
        return {
            "version": self.config.version,
            "description": self.config.description,
            "levels": levels,
            "factors": factors,
            "weights": {f.key: f.weight for f in self.config.factors},
            "combination_rules": [rule.model_dump() for rule in self.config.combination_rules],
            "notes": [
                "Weights sum to 100 so the per-factor points add up to the final score.",
                "Bands are engineering heuristics anchored on published comfort and air-quality guidance, not regulatory limits.",
                "Trend rules can escalate a factor above its band (rapid pressure drop, worsening air quality).",
                "The same model, levels and colours drive the five LEDs on the Arduino.",
            ],
        }


class _MetricFormatMap(dict):
    """Format mapping that tolerates absent metrics (renders 0.0)."""

    def __init__(self, metrics: dict[str, Any]) -> None:
        super().__init__({key: (value if value is not None else 0.0) for key, value in metrics.items()})

    def __missing__(self, key: str) -> float:  # pragma: no cover - defensive
        return 0.0


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
