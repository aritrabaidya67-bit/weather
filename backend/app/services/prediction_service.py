"""Forecasting.

Method selection is data-driven rather than fashion-driven:

* **< min samples** -> no forecast at all. The response says so explicitly
  ("insufficient historical data for reliable prediction") instead of emitting a
  guess dressed up as a prediction.
* **linear + Holt blend** (default) - an ordinary least-squares line and Holt's
  linear exponential smoothing are computed independently and blended by fit
  quality. With 15-second sampling, 30 minutes of history already gives >100
  points, so this is well inside a statistical method's comfort zone with far
  less variance than a fitted ML model would have.
* **diurnal model** for illumination, where a daily sine is objectively the right
  prior and a straight line is nonsense.
* **heuristic probability** for rain, because "will it rain" is a classification
  problem driven by pressure/humidity dynamics, not a linear extrapolation.

Confidence (documented, deterministic)::

    sample_score = min(1, n / (2 * min_samples))
    fit_score    = R^2                      (linear)  |  1 - sigma_res/sigma_y  (Holt)
    base         = 0.55 * fit_score + 0.45 * sample_score
    confidence   = clamp(base * exp(-horizon / max(30, window_minutes)), 0.02, max_confidence)

Every response carries method, sample count, R², the features used and a
disclaimer, and snapshots are persisted so forecasts can later be scored against
what actually happened.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Sequence

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.logging import get_logger
from ..core.sensors import REGISTRY
from ..models import PredictionRecord, SensorReading
from ..repositories import PredictionRepository, ReadingRepository
from ..utils import environment
from ..utils.stats import clamp, holt_linear_forecast, linear_fit, mean, stdev
from ..utils.timeutils import ensure_utc, utcnow
from .analytics_service import AnalyticsService
from .risk_service import RiskService

logger = get_logger("app.prediction")

PREDICTION_METRICS = (
    "temperature_c",
    "humidity_pct",
    "pressure_hpa",
    "air_quality_index",
    "light_pct",
    "rain_pct",
)

RISK_FORECAST_METRICS = PREDICTION_METRICS

INSUFFICIENT_NOTE = (
    "Insufficient historical data for reliable prediction. "
    "At least {needed} samples are required; {have} available."
)


class PredictionService:
    def __init__(self, session: Session, risk_service: RiskService | None = None) -> None:
        self.session = session
        self.settings = get_settings()
        self.readings = ReadingRepository(session)
        self.predictions = PredictionRepository(session)
        self.analytics = AnalyticsService(session)
        self.risk = risk_service or RiskService()

    # --------------------------------------------------------------- public API
    def forecast(
        self,
        device_id: str,
        *,
        horizons: list[int] | None = None,
        persist: bool = False,
    ) -> dict[str, Any]:
        horizons = horizons or list(self.settings.prediction.horizons_minutes)
        horizons = sorted({int(h) for h in horizons if 0 < int(h) <= 240}) or [30]
        rows = self.readings.recent(device_id, limit=self.settings.prediction.max_samples)
        now = utcnow()
        metrics: dict[str, dict[str, Any]] = {}
        per_horizon: dict[str, dict[str, dict[str, Any]]] = {str(h): {} for h in horizons}
        notes: list[str] = []
        samples = 0

        series = {metric: self._extract_series(rows, metric) for metric in PREDICTION_METRICS}
        samples = max((len(points) for points in series.values()), default=0)
        window_minutes = self._window_minutes(rows)

        if samples < self.settings.prediction.min_samples_linear:
            notes.append(
                INSUFFICIENT_NOTE.format(
                    needed=self.settings.prediction.min_samples_linear, have=samples
                )
            )

        for horizon in horizons:
            for metric in PREDICTION_METRICS:
                prediction = self._predict_metric(
                    metric, series[metric], horizon, rows, window_minutes
                )
                per_horizon[str(horizon)][metric] = prediction
                if horizon == self.settings.prediction.primary_horizon_minutes:
                    metrics[metric] = prediction
            per_horizon[str(horizon)]["risk_score"] = self._risk_forecast(
                device_id, per_horizon[str(horizon)], horizon
            )

        primary_key = str(self.settings.prediction.primary_horizon_minutes)
        if primary_key not in per_horizon:
            primary_key = str(horizons[0])
        for metric in PREDICTION_METRICS:
            metrics.setdefault(metric, per_horizon[primary_key][metric])

        risk_forecast = per_horizon[primary_key].get("risk_score")
        rain = self._rain_probability(rows, self.settings.prediction.primary_horizon_minutes)
        summary = self._summary_lines(metrics, risk_forecast, samples, rows)

        if samples == 0:
            notes.append("No readings stored yet, so no forecast can be produced.")

        if persist and samples >= self.settings.prediction.min_samples_linear:
            self._persist(device_id, per_horizon, rows, now)

        return {
            "device_id": device_id,
            "generated_at": now.isoformat(),
            "primary_horizon_minutes": int(primary_key),
            "horizons_minutes": horizons,
            "data_sufficient": samples >= self.settings.prediction.min_samples_linear,
            "samples_used": samples,
            "observation_window_minutes": round(window_minutes, 1),
            "metrics": {k: v for k, v in metrics.items() if v},
            "all_horizons": per_horizon,
            "risk": risk_forecast,
            "rain": rain,
            "summary": summary,
            "notes": notes,
            "disclaimer": (
                "Forecasts are statistical estimates derived from recent sensor history. "
                "They are not guaranteed outcomes."
            ),
        }

    def accuracy(self, device_id: str) -> dict[str, Any]:
        summary = self.predictions.accuracy_summary(device_id)
        evaluated = self.predictions.count(device_id)
        return {
            "device_id": device_id,
            "evaluated_count": int(evaluated),
            "horizons": summary,
            "notes": [
                "Forecast snapshots are stored and scored against the reading that actually arrived at the target time.",
                "Absolute error (MAE) is reported per metric and horizon; higher horizons naturally score worse.",
            ]
            + ([] if evaluated else ["No forecasts have been scored yet - this needs data over time."]),
        }

    def history(self, device_id: str, limit: int = 50) -> dict[str, Any]:
        records = self.predictions.list(device_id, limit=limit)
        return {
            "device_id": device_id,
            "count": len(records),
            "records": [record.as_dict() for record in records],
        }

    def evaluate_pending(self, limit: int = 300) -> int:
        """Score forecasts whose horizon has elapsed (honest self-assessment)."""
        pending = self.predictions.pending_evaluation(limit=limit)
        evaluated = 0
        for record in pending:
            target = ensure_utc(record.target_at) or utcnow()
            row = self._reading_nearest(record.device_id, target)
            if row is None:
                continue
            actual = getattr(row, record.metric, None)
            self.predictions.evaluate(record, float(actual) if actual is not None else None)
            evaluated += 1
        if evaluated:
            logger.info("predictions_evaluated", count=evaluated)
        return evaluated

    # ---------------------------------------------------------------- internals
    def _extract_series(
        self, rows: Sequence[SensorReading], metric: str
    ) -> list[tuple[float, float, datetime]]:
        """Return (minutes_relative, value, timestamp) with the last sample at 0.

        An empty series means "this metric has no stored value at all". A series
        with a single point is returned as-is: it cannot support a fit, but it is
        a real observation, and reporting it lets callers distinguish "one
        reading exists" from "no readings exist" and state the current value.
        Collapsing both to an empty list would make `samples_used` read 0 when a
        reading is plainly there, which is exactly the kind of misleading number
        this service is supposed to avoid.
        """
        raw: list[tuple[float, float, datetime]] = []
        for row in rows:
            value = getattr(row, metric, None)
            if value is None:
                continue
            received = ensure_utc(row.received_at)
            if received is None:
                continue
            raw.append((received.timestamp(), float(value), received))
        if not raw:
            return []
        last_timestamp = raw[-1][0]
        return [((ts - last_timestamp) / 60.0, value, stamp) for ts, value, stamp in raw]

    def _window_minutes(self, rows: Sequence[SensorReading]) -> float:
        timestamps = [ensure_utc(r.received_at) for r in rows if r.received_at is not None]
        timestamps = [t for t in timestamps if t is not None]
        if len(timestamps) < 2:
            return 0.0
        return (timestamps[-1] - timestamps[0]).total_seconds() / 60.0

    def _sampling_interval_minutes(self, series: list[tuple[float, float, datetime]]) -> float:
        if len(series) < 2:
            return 1.0
        diffs = [
            abs(series[index][0] - series[index - 1][0]) for index in range(1, len(series))
        ]
        positives = [d for d in diffs if d > 0]
        if not positives:
            return 1.0
        return max(1e-3, mean(positives))

    def _predict_metric(
        self,
        metric: str,
        series: list[tuple[float, float, datetime]],
        horizon_minutes: int,
        rows: Sequence[SensorReading],
        window_minutes: float,
    ) -> dict[str, Any]:
        spec = REGISTRY[metric]
        base: dict[str, Any] = {
            "metric": metric,
            "label": spec.label,
            "unit": spec.unit,
            "horizon_minutes": horizon_minutes,
            "current_value": series[-1][1] if series else None,
            "current_status": (
                spec.interpret(series[-1][1])[0] if series else None
            ),
        }
        # The minimum-history rule is enforced BEFORE any method is tried, so no
        # method can bypass it. The diurnal prior used to run first and would
        # happily emit a confident-looking illumination forecast from a single
        # reading - a fabricated prediction, which is exactly what must not
        # happen. A method may only add information, never a prerequisite.
        if len(series) < self.settings.prediction.min_samples_linear:
            return {
                **base,
                "predicted_value": None,
                "lower_bound": None,
                "upper_bound": None,
                "delta": None,
                "direction": "unknown",
                "confidence": 0.0,
                "confidence_label": "low",
                "method": "insufficient_data",
                "samples_used": len(series),
                "r_squared": None,
                "expected_status": None,
                "reasoning": INSUFFICIENT_NOTE.format(
                    needed=self.settings.prediction.min_samples_linear, have=len(series)
                ),
                "features": ["recent sensor history"],
                "warnings": ["Not enough history for a statistical forecast."],
            }

        if metric == "light_pct":
            diurnal = self._diurnal_prediction(spec, series, horizon_minutes, window_minutes)
            if diurnal is not None:
                return {**base, **diurnal}

        xs = [point[0] for point in series]
        ys = [point[1] for point in series]
        interval = self._sampling_interval_minutes(series)
        fit = linear_fit(xs, ys)
        holt = None
        if len(series) >= self.settings.prediction.min_samples_holt:
            holt = holt_linear_forecast(ys, intervals_per_step=interval)

        linear_prediction = fit.predict(float(horizon_minutes)) if fit else None
        holt_prediction = (
            holt.forecast(horizon_minutes / interval if interval else horizon_minutes)
            if holt
            else None
        )

        y_sigma = stdev(ys)
        method = "linear_trend"
        residual_sigma = fit.residual_sigma if fit else y_sigma
        fit_score = fit.r_squared if fit else 0.0

        if linear_prediction is not None and holt_prediction is not None:
            holt_fit_score = (
                clamp(1 - (holt.residual_sigma / y_sigma), 0.0, 1.0) if y_sigma > 0 else 0.5
            )
            weight_linear = fit_score + 0.05
            weight_holt = holt_fit_score + 0.05
            predicted = (
                linear_prediction * weight_linear + holt_prediction * weight_holt
            ) / (weight_linear + weight_holt)
            fit_score = clamp(
                (fit_score * weight_linear + holt_fit_score * weight_holt)
                / (weight_linear + weight_holt),
                0.0,
                1.0,
            )
            residual_sigma = (fit.residual_sigma + holt.residual_sigma) / 2
            method = "blend"
        elif holt_prediction is not None:
            predicted = holt_prediction
            residual_sigma = holt.residual_sigma
            method = "holt_linear"
        else:
            predicted = linear_prediction
            method = "linear_trend"

        if predicted is None:
            return {
                **base,
                "predicted_value": None,
                "direction": "unknown",
                "confidence": 0.0,
                "confidence_label": "low",
                "method": "insufficient_data",
                "samples_used": len(series),
                "reasoning": "The fit could not produce a value (degenerate series).",
                "features": [],
                "warnings": ["Timestamps of the available samples are identical."],
                "lower_bound": None,
                "upper_bound": None,
                "delta": None,
                "r_squared": None,
                "expected_status": None,
            }

        predicted = spec.clamp(float(predicted))
        margin = max(residual_sigma, 0.02 * abs(predicted) + 1e-6) * math.sqrt(
            1 + horizon_minutes / max(1.0, window_minutes)
        )
        confidence = self._confidence(fit_score, len(series), horizon_minutes, window_minutes)
        current = ys[-1]
        delta = predicted - current
        direction = self._direction(delta, spec)
        expected_status, _ = spec.interpret(predicted)

        features = [
            "last {} samples over {:.0f} minutes".format(len(series), window_minutes),
            f"sampling interval ~{interval:.2f} min",
            "ordinary least squares slope" if method in ("linear_trend", "blend") else "",
            "Holt linear exponential smoothing" if method in ("holt_linear", "blend") else "",
        ]
        warnings: list[str] = []
        if confidence < 0.45:
            warnings.append("Low confidence: treat this forecast as indicative only.")
        if horizon_minutes > max(15.0, window_minutes):
            warnings.append(
                "The horizon exceeds the observed window, so this is an extrapolation."
            )
        r2 = fit.r_squared if fit else None
        reasoning = (
            f"{method.replace('_', ' ')} over {len(series)} samples ({window_minutes:.0f} min of history); "
            f"fit quality R²={r2:.2f}. " if r2 is not None else
            f"{method.replace('_', ' ')} over {len(series)} samples. "
        )
        reasoning += (
            f"Predicted {predicted:.2f} {spec.unit} at +{horizon_minutes} min versus "
            f"{current:.2f} {spec.unit} now (delta {delta:+.2f})."
        )

        return {
            **base,
            "predicted_value": round(predicted, spec.decimals + 1),
            "lower_bound": round(max(spec.minimum or -1e9, predicted - margin), spec.decimals + 1),
            "upper_bound": round(min(spec.maximum or 1e9, predicted + margin), spec.decimals + 1),
            "delta": round(delta, spec.decimals + 1),
            "direction": direction,
            "confidence": confidence,
            "confidence_label": _confidence_label(confidence),
            "method": method,
            "samples_used": len(series),
            "r_squared": round(r2, 3) if r2 is not None else None,
            "expected_status": expected_status,
            "reasoning": reasoning,
            "features": [f for f in features if f],
            "warnings": warnings,
        }

    def _confidence(
        self, fit_score: float, samples: int, horizon_minutes: float, window_minutes: float
    ) -> float:
        cfg = self.settings.prediction
        sample_score = min(1.0, samples / max(1, 2 * cfg.min_samples_linear))
        base = 0.55 * clamp(fit_score, 0.0, 1.0) + 0.45 * sample_score
        decay = math.exp(-horizon_minutes / max(30.0, window_minutes or 30.0))
        return round(clamp(base * decay, 0.02, cfg.max_confidence), 3)

    def _direction(self, delta: float, spec: Any) -> str:
        threshold = max(1e-9, (spec.plausible_delta_per_min or 1.0) * 0.5)
        if delta > threshold:
            return "rising"
        if delta < -threshold:
            return "falling"
        return "stable"

    def _diurnal_prediction(
        self,
        spec: Any,
        series: list[tuple[float, float, datetime]],
        horizon_minutes: int,
        window_minutes: float,
    ) -> dict[str, Any] | None:
        """Illumination follows a daily cycle; fitting a line to it is meaningless."""
        if not series:
            return None
        target_time = series[-1][2] + timedelta(minutes=horizon_minutes)
        amplitude = max((value for _, value, _ in series), default=0.0)
        if amplitude < 5:
            return None
        expected = self._solar_expectation(target_time, amplitude)
        current = series[-1][1]
        delta = expected - current
        # Observations must span enough of the day for a diurnal claim to be safe.
        span = window_minutes
        confidence = round(
            clamp(0.25 + min(0.35, len(series) / 400) + min(0.3, span / 720) * 0.35, 0.05, 0.7), 3
        )
        direction = "rising" if delta > 3 else ("falling" if delta < -3 else "stable")
        return {
            "predicted_value": round(expected, 2),
            "lower_bound": round(max(0.0, expected - 15), 2),
            "upper_bound": round(min(100.0, expected + 15), 2),
            "delta": round(delta, 2),
            "direction": direction,
            "confidence": confidence,
            "confidence_label": _confidence_label(confidence),
            "method": "diurnal_model",
            "samples_used": len(series),
            "r_squared": None,
            "expected_status": spec.interpret(expected)[0],
            "reasoning": (
                "Illumination is modelled with a solar-cycle expectation (06:00-19:00 local peak scaled "
                f"to the observed maximum of {amplitude:.0f} %) rather than a linear extrapolation, "
                "because a straight line cannot describe a day/night cycle."
            ),
            "features": ["local clock time", "observed daily maximum illumination"],
            "warnings": (
                ["The diurnal model is a rough prior; an LDR is uncalibrated."]
            ),
        }

    def _solar_expectation(self, target: datetime, amplitude: float) -> float:
        local = target.astimezone()
        hour = local.hour + local.minute / 60.0
        if hour < 6.0 or hour > 19.0:
            return 1.0
        return round(clamp(amplitude * math.sin(math.pi * (hour - 6.0) / 13.0), 0.0, 100.0), 2)

    def _risk_forecast(
        self, device_id: str, horizon_metrics: dict[str, dict[str, Any]], horizon: int
    ) -> dict[str, Any]:
        latest = self.readings.latest(device_id)
        current_metrics = self.analytics._metrics_from_row(latest)  # noqa: SLF001 (shared helper)
        current_assessment = self.risk.assess(
            self.analytics._risk_inputs(  # noqa: SLF001
                latest, current_metrics, list(latest.anomalies or []) if latest else [], {}
            )
        )
        predicted_metrics = dict(current_metrics)
        for metric, prediction in horizon_metrics.items():
            if prediction.get("predicted_value") is not None:
                predicted_metrics[metric] = prediction["predicted_value"]
        if predicted_metrics.get("temperature_c") is not None:
            predicted_metrics["heat_index_c"] = environment.heat_index_c(
                predicted_metrics.get("temperature_c"), predicted_metrics.get("humidity_pct")
            )
        predicted_assessment = self.risk.assess(
            self.analytics._risk_inputs(  # noqa: SLF001
                latest, predicted_metrics, [], {}
            )
        )

        current_points = {c["key"]: c["points"] for c in current_assessment["contributions"]}
        predicted_points = {c["key"]: c["points"] for c in predicted_assessment["contributions"]}
        drivers: list[str] = []
        for key, points in sorted(
            predicted_points.items(), key=lambda item: abs(item[1] - current_points.get(item[0], 0)), reverse=True
        ):
            delta = points - current_points.get(key, 0)
            if abs(delta) < 1.0:
                continue
            direction = "up" if delta > 0 else "down"
            label = key.replace("_", " ")
            drivers.append(f"{label} {direction} {abs(delta):.1f} points")
            if len(drivers) >= 3:
                break

        predicted_score = float(predicted_assessment["score"])
        current_score = float(current_assessment["score"])
        delta = predicted_score - current_score
        direction = "rising" if delta > 2 else ("falling" if delta < -2 else "stable")
        confidences = [
            prediction["confidence"]
            for prediction in horizon_metrics.values()
            if isinstance(prediction, dict) and prediction.get("confidence")
        ]
        confidence = round(
            clamp(mean(confidences) * 0.9 if confidences else 0.0, 0.0, 0.9), 3
        )
        return {
            "horizon_minutes": horizon,
            "current_score": current_score,
            "predicted_score": predicted_score,
            "current_level": int(current_assessment["level"]),
            "predicted_level": int(predicted_assessment["level"]),
            "predicted_label": str(predicted_assessment["label"]),
            "direction": direction,
            "confidence": confidence,
            "drivers": drivers,
        }

    def _rain_probability(self, rows: Sequence[SensorReading], horizon: int) -> dict[str, Any]:
        values = [
            (
                ensure_utc(row.received_at),
                row.humidity_pct,
                row.pressure_hpa,
                row.rain_pct,
            )
            for row in rows
        ]
        values = [item for item in values if item[0] is not None]
        if len(values) < 5:
            return {
                "horizon_minutes": horizon,
                "probability": 0.0,
                "confidence": 0.0,
                "method": "heuristic_probability",
                "reasoning": "Not enough readings to assess rain probability.",
                "currently_raining": False,
            }
        humidity = [v[1] for v in values if v[1] is not None]
        pressure = [v[2] for v in values if v[2] is not None]
        wetness = [v[3] for v in values if v[3] is not None]
        current_wetness = wetness[-1] if wetness else 0.0
        currently_raining = current_wetness >= 10

        weights = self.settings.prediction.rain_probability_weights
        terms: dict[str, float] = {}
        if humidity:
            terms["humidity"] = clamp((humidity[-1] - 60.0) / 40.0, 0.0, 1.0)
            if len(humidity) >= 4:
                rise = humidity[-1] - humidity[0]
                terms["humidity_rise"] = clamp(rise / 15.0, 0.0, 1.0)
        if pressure and len(pressure) >= 3:
            drop = pressure[0] - pressure[-1]
            terms["pressure_drop"] = clamp(drop / 6.0, 0.0, 1.0)
        terms["current_wetness"] = clamp(current_wetness / 100.0, 0.0, 1.0)

        weighted = sum(terms.get(key, 0.0) * weights.get(key, 0.0) for key in weights)
        total_weight = sum(weights.values()) or 1.0
        z = (weighted / total_weight) * 5.0 - 1.5
        probability = 1.0 / (1.0 + math.exp(-z))
        if currently_raining:
            probability = max(probability, 0.75)
        probability = clamp(probability, 0.02, 0.95)
        confidence = round(clamp(0.3 + min(0.3, len(values) / 300) * 0.3, 0.2, 0.6), 3)
        return {
            "horizon_minutes": horizon,
            "probability": round(probability, 3),
            "confidence": confidence,
            "method": "heuristic_probability",
            "reasoning": (
                "Heuristic logistic model using absolute humidity level, humidity trend, "
                "recent pressure change and current wetness (weights are configurable). "
                "This is a probabilistic indicator, not a meteorological forecast."
            ),
            "currently_raining": currently_raining,
            "inputs": {key: round(value, 3) for key, value in terms.items()},
        }

    def _summary_lines(
        self,
        metrics: dict[str, dict[str, Any]],
        risk_forecast: dict[str, Any] | None,
        samples: int,
        rows: Sequence[SensorReading],
    ) -> list[str]:
        lines: list[str] = []
        horizon = next(iter(metrics.values()))["horizon_minutes"] if metrics else 30
        if samples < self.settings.prediction.min_samples_linear:
            return [
                INSUFFICIENT_NOTE.format(
                    needed=self.settings.prediction.min_samples_linear, have=samples
                )
            ]
        for metric in ("temperature_c", "humidity_pct", "air_quality_index", "pressure_hpa", "light_pct", "rain_pct"):
            prediction = metrics.get(metric)
            if not prediction or prediction.get("predicted_value") is None:
                continue
            spec = REGISTRY[metric]
            current = prediction.get("current_value")
            predicted = prediction.get("predicted_value")
            percent = int(round(float(prediction.get("confidence", 0)) * 100))
            status_change = ""
            if (
                prediction.get("current_status")
                and prediction.get("expected_status")
                and prediction["current_status"] != prediction["expected_status"]
            ):
                status_change = (
                    f" (status {prediction['current_status']} -> {prediction['expected_status']})"
                )
            lines.append(
                f"{spec.label}: {current:.1f} -> {predicted:.1f} {spec.unit} in the next "
                f"{horizon} minutes{status_change}. Confidence {percent}% "
                f"({prediction.get('method', 'unknown').replace('_', ' ')})."
            )
        if risk_forecast and risk_forecast.get("predicted_score") is not None:
            lines.append(
                f"Environmental risk is forecast to go from {risk_forecast['current_score']:.0f} "
                f"to {risk_forecast['predicted_score']:.0f} "
                f"({risk_forecast['direction']}); level {risk_forecast['current_level']} -> "
                f"{risk_forecast['predicted_level']}. Drivers: "
                f"{', '.join(risk_forecast.get('drivers') or ['no dominant driver'])}."
            )
        _ = rows
        return lines

    def _reading_nearest(self, device_id: str, target: datetime) -> SensorReading | None:
        window = self.readings.between(
            device_id, target - timedelta(minutes=5), target + timedelta(minutes=5)
        )
        if not window:
            return None
        return min(
            window,
            key=lambda row: abs(
                ((ensure_utc(row.received_at) or target) - target).total_seconds()
            ),
        )

    def _persist(
        self,
        device_id: str,
        per_horizon: dict[str, dict[str, dict[str, Any]]],
        rows: Sequence[SensorReading],
        now: datetime,
    ) -> None:
        records: list[PredictionRecord] = []
        for horizon_key, metrics in per_horizon.items():
            horizon = int(horizon_key)
            for metric, prediction in metrics.items():
                if metric == "risk_score":
                    continue
                if prediction.get("predicted_value") is None:
                    continue
                records.append(
                    PredictionRecord(
                        device_id=device_id,
                        created_at=now,
                        target_at=now + timedelta(minutes=horizon),
                        horizon_minutes=horizon,
                        metric=metric,
                        current_value=prediction.get("current_value"),
                        predicted_value=prediction.get("predicted_value"),
                        lower_bound=prediction.get("lower_bound"),
                        upper_bound=prediction.get("upper_bound"),
                        confidence=prediction.get("confidence"),
                        method=prediction.get("method"),
                        reasoning={
                            "reasoning": prediction.get("reasoning"),
                            "features": prediction.get("features", []),
                            "r_squared": prediction.get("r_squared"),
                        },
                    )
                )
        count = self.predictions.add_many(records)
        if count:
            logger.info("prediction_snapshot_stored", count=count)


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.7:
        return "high"
    if confidence >= 0.45:
        return "medium"
    return "low"


__all__ = ["PredictionService", "PREDICTION_METRICS"]
