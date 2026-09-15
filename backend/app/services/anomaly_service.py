"""Robust anomaly detection.

Deliberately statistical rather than "AI": with a handful of samples per minute a
rolling median/MAD baseline plus a z-score and a first-difference (sudden change)
test is more honest and far easier to explain than a black-box model. A stuck
sensor test is included because a frozen value is the most common real-world
IoT failure and it looks perfectly normal to a threshold check.

Everything a detection returns is explainable: the baseline, the deviation, the
z-score and the number of samples that produced the baseline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..core.config import AnomalyConfig, get_settings
from ..core.logging import get_logger
from ..core.sensors import REGISTRY
from ..models import SensorReading
from ..utils.stats import mean, median, robust_sigma, stdev
from ..utils.timeutils import ensure_utc, utcnow

logger = get_logger("app.anomaly")

#: Metrics monitored for anomalies (derived, normalised indices - comparable
#: values - rather than raw ADC counts, so the thresholds mean something).
MONITORED_METRICS = (
    "temperature_c",
    "humidity_pct",
    "pressure_hpa",
    "air_quality_index",
    "light_pct",
    "rain_pct",
)

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3}


class AnomalyService:
    def __init__(self, config: AnomalyConfig | None = None) -> None:
        self.config = config or get_settings().anomaly

    # ----------------------------------------------------------------- public
    def detect(
        self,
        history: list[SensorReading],
        current: dict[str, float | None],
        *,
        exclude_current_from_baseline: bool = True,
    ) -> list[dict[str, Any]]:
        """Return anomalies for the current reading against the historical baseline."""
        window = history[-self.config.window_points :]
        anomalies: list[dict[str, Any]] = []
        for metric in MONITORED_METRICS:
            values = [float(getattr(row, metric)) for row in window if getattr(row, metric) is not None]
            if exclude_current_from_baseline and values:
                values = values[:-1]
            current_value = current.get(metric)
            if current_value is None:
                continue
            if len(values) < self.config.min_samples:
                continue
            anomaly = self._check_metric(metric, values, float(current_value))
            if anomaly:
                anomalies.append(anomaly)
        stuck = self._check_stuck(window)
        for item in stuck:
            if not any(a["sensor"] == item["sensor"] and a["kind"] == item["kind"] for a in anomalies):
                anomalies.append(item)
        if anomalies:
            logger.info(
                "anomalies_detected",
                count=len(anomalies),
                sensors=[a["sensor"] for a in anomalies],
                severities=[a["severity"] for a in anomalies],
            )
        return anomalies

    def baseline_readiness(self, history: list[SensorReading]) -> dict[str, int]:
        window = history[-self.config.window_points :]
        out: dict[str, int] = {}
        for metric in MONITORED_METRICS:
            out[metric] = sum(1 for row in window if getattr(row, metric) is not None)
        return out

    def baseline_stats(self, history: list[SensorReading]) -> dict[str, dict[str, float | None]]:
        """Baseline summary used by the UI and the chatbot."""
        window = history[-self.config.window_points :]
        out: dict[str, dict[str, float | None]] = {}
        for metric in MONITORED_METRICS:
            values = [float(getattr(row, metric)) for row in window if getattr(row, metric) is not None]
            if not values:
                out[metric] = {"mean": None, "median": None, "sigma": None, "samples": 0}
                continue
            out[metric] = {
                "mean": round(mean(values), 3),
                "median": round(median(values), 3),
                "sigma": round(robust_sigma(values), 3),
                "samples": len(values),
            }
        return out

    # ---------------------------------------------------------------- private
    def _check_metric(
        self, metric: str, values: list[float], current_value: float
    ) -> dict[str, Any] | None:
        spec = REGISTRY.get(metric)
        if spec is None:
            return None
        baseline_mean = mean(values)
        sigma = robust_sigma(values)
        floor = self.config.min_absolute_floor.get(metric, 0.0)
        delta = current_value - baseline_mean
        z_score = (delta / sigma) if sigma > 1e-9 else None

        severity: str | None = None
        kind = "spike" if delta > 0 else "drop"

        if z_score is not None and abs(z_score) >= self.config.z_high and abs(delta) >= floor:
            severity = "high"
        elif z_score is not None and abs(z_score) >= self.config.z_medium and abs(delta) >= floor:
            severity = "medium"
        elif z_score is None and abs(delta) >= max(floor * 3, floor):
            # Baseline is perfectly flat: any real movement is notable.
            severity = "medium"

        # sudden change test on first differences (catches a step change even
        # when the rolling sigma is inflated by the step itself)
        diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
        diffs.append(current_value - values[-1])
        min_delta = self.config.sudden_min_delta.get(metric, 0.0)
        if diffs:
            diff_sigma = stdev(diffs)
            last_diff = diffs[-1]
            threshold = diff_sigma * self.config.sudden_sigma
            if (
                abs(last_diff) >= min_delta
                and (threshold <= 1e-9 or abs(last_diff) >= threshold)
                and severity in (None, "low")
            ):
                severity = "medium" if abs(last_diff) >= min_delta * 2 else "low"
                kind = "sudden_change"

        if severity is None:
            return None

        expected_low = round(baseline_mean - 2 * sigma, 3)
        expected_high = round(baseline_mean + 2 * sigma, 3)
        direction = "above" if delta > 0 else "below"
        message = self._message(spec.label, current_value, baseline_mean, spec.unit, direction, kind)
        explanation = (
            f"Rolling baseline over the last {len(values)} samples: mean {baseline_mean:.2f}"
            f" {spec.unit}, robust sigma {sigma:.2f}. Current value {current_value:.2f} {spec.unit} "
            f"is {abs(delta):.2f} {spec.unit} {direction} the baseline"
            + (f" (z-score {z_score:.2f})" if z_score is not None else " (baseline sigma near zero)")
            + f". Detection method: rolling mean/MAD z-score with a {self.config.sudden_sigma:.1f}-sigma "
            "first-difference step test."
        )
        return {
            "sensor": metric,
            "label": spec.label,
            "unit": spec.unit,
            "severity": severity,
            "kind": kind,
            "current_value": round(current_value, 3),
            "expected_value": round(baseline_mean, 3),
            "expected_low": expected_low,
            "expected_high": expected_high,
            "deviation": round(delta, 3),
            "z_score": round(z_score, 3) if z_score is not None else None,
            "baseline_samples": len(values),
            "message": message,
            "explanation": explanation,
            "detected_at": utcnow().isoformat(),
            "direction": direction,
            "contribution_to_risk": {"low": 0.08, "medium": 0.2, "high": 0.35}[severity],
        }

    def _check_stuck(self, window: list[SensorReading]) -> list[dict[str, Any]]:
        """Detect sensors frozen at a constant value (common wiring/ADC failure)."""
        results: list[dict[str, Any]] = []
        min_repeats = max(self.config.min_samples, 8)
        for metric in MONITORED_METRICS:
            values = [getattr(row, metric) for row in window]
            values = [float(v) for v in values if v is not None]
            if len(values) < min_repeats:
                continue
            tail = values[-min_repeats:]
            if len(set(tail)) == 1 and float(REGISTRY[metric].maximum or 1) != 0:
                # perfectly flat tail; check it is not the floor/ceiling of a binary sensor
                spec = REGISTRY[metric]
                if spec.minimum is not None and tail[0] <= spec.minimum + 1e-6:
                    continue
                if spec.maximum is not None and tail[0] >= spec.maximum - 1e-6:
                    continue
                results.append(
                    {
                        "sensor": metric,
                        "label": spec.label,
                        "unit": spec.unit,
                        "severity": "medium",
                        "kind": "stuck",
                        "current_value": round(tail[-1], 3),
                        "expected_value": None,
                        "expected_low": None,
                        "expected_high": None,
                        "deviation": 0.0,
                        "z_score": None,
                        "baseline_samples": len(tail),
                        "message": (
                            f"{spec.label} has been constant at {tail[-1]:.2f} {spec.unit} "
                            f"for the last {len(tail)} samples."
                        ),
                        "explanation": (
                            "A perfectly constant value over consecutive samples usually means a "
                            "failed, disconnected or unpowered sensor rather than a real steady "
                            "environment. Verify the wiring and the sensor supply."
                        ),
                        "detected_at": utcnow().isoformat(),
                        "direction": "above",
                        "contribution_to_risk": 0.2,
                    }
                )
        return results

    def _message(
        self,
        label: str,
        current_value: float,
        baseline_mean: float,
        unit: str,
        direction: str,
        kind: str,
    ) -> str:
        if kind == "sudden_change":
            return (
                f"{label} changed abruptly to {current_value:.1f} {unit} "
                f"(recent baseline {baseline_mean:.1f} {unit})."
            )
        prefix = "above" if direction == "above" else "below"
        return (
            f"{label} reading of {current_value:.1f} {unit} is significantly {prefix} "
            f"the recent baseline of {baseline_mean:.1f} {unit}."
        )

    def severity_counts(self, anomalies: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {"low": 0, "medium": 0, "high": 0}
        for anomaly in anomalies:
            severity = str(anomaly.get("severity", "low"))
            counts[severity] = counts.get(severity, 0) + 1
        return counts


def anomalies_from_reading(row: SensorReading | None) -> list[dict[str, Any]]:
    """Anomalies stored alongside a historical reading."""
    if row is None or not row.anomalies:
        return []
    return [dict(item) for item in row.anomalies]


def newest_anomaly_timestamp(anomalies: list[dict[str, Any]]) -> str | None:
    if not anomalies:
        return None
    return str(anomalies[0].get("detected_at") or utcnow().isoformat())


def age_of(timestamp: str) -> float:
    parsed = ensure_utc(datetime.fromisoformat(timestamp))
    if parsed is None:
        return 0.0
    return (utcnow() - parsed).total_seconds()
