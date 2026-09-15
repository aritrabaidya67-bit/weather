"""Analytics: statistics, trends, aggregation and evidence-based observations.

This service never invents narrative. Every observation it produces carries the
numbers that support it (trend slope, R², sample count, baseline comparison), and
observations are withheld when the data is too thin to justify them.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, Sequence

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.logging import get_logger
from ..core.sensors import CHANNELS, CHANNEL_ORDER, REGISTRY
from ..models import SensorReading
from ..repositories import AlertRepository, DeviceRepository, ReadingRepository
from ..utils import environment
from ..utils.stats import (
    linear_fit,
    mean,
    median,
    moving_average,
    pearson,
    percentile,
    robust_sigma,
    slope_per_minute,
    stdev,
)
from ..utils.timeutils import ensure_utc, utcnow
from .anomaly_service import MONITORED_METRICS
from .risk_service import RiskService

logger = get_logger("app.analytics")

#: A trend is only reported as rising/falling when the fitted slope exceeds this
#: share of the sensor's plausible per-minute movement. This keeps sensor noise
#: from being reported as a trend.
TREND_SIGNIFICANCE_RATIO = 0.05

BUCKETS_SECONDS = {
    "15m": 30,
    "1h": 60,
    "6h": 300,
    "24h": 900,
    "7d": 3600,
}


class AnalyticsService:
    def __init__(self, session: Session, risk_service: RiskService | None = None) -> None:
        self.session = session
        self.settings = get_settings()
        self.readings = ReadingRepository(session)
        self.alerts = AlertRepository(session)
        self.devices = DeviceRepository(session)
        self.risk = risk_service or RiskService()

    # ------------------------------------------------------------------ series
    def metric_series(
        self,
        rows: Sequence[SensorReading],
        metric: str,
        *,
        bucket_seconds: int | None = None,
        include_points: bool = True,
    ) -> dict[str, Any]:
        spec = REGISTRY.get(metric)
        label = spec.label if spec else metric
        unit = spec.unit if spec else ""
        timestamps: list[float] = []
        values: list[float] = []
        points: list[dict[str, Any]] = []
        fallback_points: list[dict[str, Any]] = []

        bucket: dict[int, list[float]] = {}
        bucket_index: dict[int, datetime] = {}
        for row in rows:
            value = getattr(row, metric, None)
            if value is None:
                continue
            received_at = ensure_utc(row.received_at) or utcnow()
            value = float(value)
            timestamps.append(received_at.timestamp() / 60.0)
            values.append(value)
            fallback_points.append({"timestamp": received_at.isoformat(), "value": round(value, 3)})
            if bucket_seconds:
                index = int(received_at.timestamp() // bucket_seconds)
                bucket.setdefault(index, []).append(value)
                bucket_index[index] = received_at

        if bucket_seconds and bucket:
            points = [
                {
                    "timestamp": bucket_index[index].isoformat(),
                    "value": round(mean(bucket[index]), 3),
                }
                for index in sorted(bucket)
            ]
        elif include_points:
            points = fallback_points[-400:]

        series: dict[str, Any] = {
            "metric": metric,
            "label": label,
            "unit": unit,
            "points": points if include_points else [],
            "sample_count": len(values),
        }
        if not values:
            series.update(
                {
                    "minimum": None,
                    "maximum": None,
                    "mean": None,
                    "median": None,
                    "p95": None,
                    "stdev": None,
                    "latest": None,
                    "change": None,
                    "change_pct": None,
                    "slope_per_minute": None,
                    "trend": "unknown",
                    "r_squared": None,
                }
            )
            return series

        fit = linear_fit(timestamps, values)
        slope = fit.slope if fit else None
        trend_threshold = (spec.plausible_delta_per_min if spec else 1.0) * TREND_SIGNIFICANCE_RATIO
        trend = "stable"
        if slope is not None:
            if slope > trend_threshold:
                trend = "rising"
            elif slope < -trend_threshold:
                trend = "falling"
        change = values[-1] - values[0]
        series.update(
            {
                "minimum": round(min(values), 3),
                "maximum": round(max(values), 3),
                "mean": round(mean(values), 3),
                "median": round(median(values), 3),
                "p95": round(percentile(values, 95), 3),
                "stdev": round(stdev(values), 3),
                "latest": round(values[-1], 3),
                "change": round(change, 3),
                "change_pct": round(change / values[0] * 100, 2) if values[0] else None,
                "slope_per_minute": round(slope, 4) if slope is not None else None,
                "trend": trend,
                "r_squared": round(fit.r_squared, 3) if fit else None,
            }
        )
        return series

    def rate_of_change_per_hour(self, rows: Sequence[SensorReading], metric: str) -> float | None:
        timestamps: list[float] = []
        values: list[float] = []
        for row in rows:
            value = getattr(row, metric, None)
            if value is None:
                continue
            timestamps.append((ensure_utc(row.received_at) or utcnow()).timestamp() / 60.0)
            values.append(float(value))
        slope = slope_per_minute(values, timestamps)
        return round(slope * 60, 4) if slope is not None else None

    # ------------------------------------------------------------ trend helper
    def trend_context(self, device_id: str, hours: float = 3.0) -> dict[str, float | None]:
        """Trend figures the risk engine uses for escalation rules."""
        rows = self.readings.recent(device_id, hours=hours)
        if len(rows) < 3:
            return {}
        pressure_values = [r.pressure_hpa for r in rows if r.pressure_hpa is not None]
        context: dict[str, float | None] = {
            "pressure_change_hpa_3h": (
                round(pressure_values[-1] - pressure_values[0], 3) if len(pressure_values) >= 2 else None
            ),
            "air_quality_slope_per_minute": self._slope(rows, "air_quality_index"),
            "temperature_slope_per_minute": self._slope(rows, "temperature_c"),
            "humidity_slope_per_minute": self._slope(rows, "humidity_pct"),
        }
        return context

    def _slope(self, rows: Sequence[SensorReading], metric: str) -> float | None:
        timestamps: list[float] = []
        values: list[float] = []
        for row in rows:
            value = getattr(row, metric, None)
            if value is None:
                continue
            timestamps.append((ensure_utc(row.received_at) or utcnow()).timestamp() / 60.0)
            values.append(float(value))
        slope = slope_per_minute(values, timestamps)
        return round(slope, 4) if slope is not None else None

    # ----------------------------------------------------------------- readings
    def reading_to_dict(self, row: SensorReading | None, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or utcnow()
        if row is None:
            return {}
        received_at = ensure_utc(row.received_at) or now
        age = (now - received_at).total_seconds()
        missing = [
            key
            for key in CHANNELS
            if getattr(row, CHANNELS[key]["primary"], None) is None
        ]
        payload = row.as_series_point()
        payload.update(
            {
                "device_id": row.device_id,
                "rain_status": row.rain_status,
                "light_status": row.light_status,
                "air_quality_status": row.air_quality_status,
                "risk_reasons": row.risk_reasons,
                "recommended_actions": row.recommended_actions,
                "risk_factors": row.risk_factors,
                "anomalies": row.anomalies or [],
                "health_score": row.health_score,
                "is_stale": age > self.settings.stale_reading_seconds,
                "age_seconds": round(age, 1),
                "missing_metrics": missing,
            }
        )
        return payload

    def latest(self, device_id: str) -> dict[str, Any]:
        return self.reading_to_dict(self.readings.latest(device_id))

    # ---------------------------------------------------------------- overview
    def channel_cards(self, device_id: str, hours: float = 6.0) -> list[dict[str, Any]]:
        """One card per physical channel: value, status, trend, sparkline."""
        settings = self.settings
        rows = self.readings.recent(device_id, minutes=120)
        window = self.readings.recent(device_id, hours=hours)
        cards: list[dict[str, Any]] = []
        for channel_key in CHANNEL_ORDER:
            channel = CHANNELS[channel_key]
            primary = str(channel["primary"])
            series = self.metric_series(window, primary, bucket_seconds=120)
            spec = REGISTRY[primary]
            current = float(series["latest"]) if series["latest"] is not None else None
            status_label, severity = (
                spec.interpret(current) if current is not None else ("no data", "info")
            )
            recent_series = self.metric_series(rows, primary, bucket_seconds=60)
            secondary = {}
            for key in channel["secondary"]:  # type: ignore[union-attr]
                secondary_series = self.metric_series(window, str(key), include_points=False)
                if secondary_series.get("latest") is not None:
                    secondary[str(key)] = {
                        "label": REGISTRY[str(key)].label,
                        "unit": REGISTRY[str(key)].unit,
                        "latest": secondary_series["latest"],
                        "mean": secondary_series["mean"],
                    }
            cards.append(
                {
                    "channel": channel_key,
                    "label": channel["label"],
                    "sensor": channel["sensor"],
                    "icon": channel["icon"],
                    "metric": primary,
                    "unit": spec.unit,
                    "color": spec.color,
                    "decimals": spec.decimals,
                    "value": current,
                    "status": status_label,
                    "severity": severity,
                    "trend": series["trend"],
                    "change": series["change"],
                    "change_pct": series["change_pct"],
                    "sufficient_data": series["sample_count"] >= 3,
                    "sample_count": series["sample_count"],
                    "sparkline": recent_series["points"],
                    "stats": {
                        "min": series["minimum"],
                        "max": series["maximum"],
                        "mean": series["mean"],
                        "median": series["median"],
                        "stdev": series["stdev"],
                        "p95": series["p95"],
                        "slope_per_minute": series["slope_per_minute"],
                        "r_squared": series["r_squared"],
                    },
                    "secondary": secondary,
                    "rate_of_change_per_hour": self.rate_of_change_per_hour(window, primary),
                    "stale": bool(
                        rows
                        and rows[-1].received_at
                        and (
                            utcnow() - (ensure_utc(rows[-1].received_at) or utcnow())
                        ).total_seconds()
                        > settings.stale_reading_seconds
                    ),
                }
            )
        return cards

    def classification(self, metrics: dict[str, float | None]) -> dict[str, Any]:
        """Plain-language classification of the current environment."""
        parts: list[str] = []
        temp = metrics.get("temperature_c")
        humidity = metrics.get("humidity_pct")
        air = metrics.get("air_quality_index")
        rain = metrics.get("rain_pct")
        pressure = metrics.get("pressure_hpa")

        if temp is not None:
            if temp >= 38:
                parts.append("extremely hot")
            elif temp >= 32:
                parts.append("hot")
            elif temp >= 26:
                parts.append("warm")
            elif temp >= 18:
                parts.append("mild")
            elif temp >= 10:
                parts.append("cool")
            else:
                parts.append("cold")
        humidity_label = None
        if humidity is not None:
            if humidity >= 90:
                humidity_label = "saturated air"
            elif humidity >= 75:
                humidity_label = "very humid"
            elif humidity >= 60:
                humidity_label = "humid"
            elif humidity >= 30:
                humidity_label = "comfortable humidity"
            elif humidity >= 20:
                humidity_label = "dry air"
            else:
                humidity_label = "very dry air"
            parts.append(humidity_label)
        if air is not None:
            parts.append(f"{environment.air_quality_status(air) or 'unknown'} air quality")
        if rain is not None:
            parts.append("precipitation present" if rain >= 5 else "no precipitation")
        if pressure is not None:
            tendency = environment.barometric_tendency(
                None  # tendency is a trend property, reported separately
            )
            if pressure < 1000:
                parts.append("low pressure")
            elif pressure > 1030:
                parts.append("high pressure")
            _ = tendency

        return {
            "label": ", ".join(parts) if parts else "insufficient data",
            "components": {
                "temperature": temp,
                "humidity": humidity,
                "air_quality_index": air,
                "rain_pct": rain,
                "pressure_hpa": pressure,
            },
            "heat_stress": (
                "heat stress likely"
                if (metrics.get("heat_index_c") or 0) >= 32
                else ("no significant heat stress" if temp is not None else "unknown")
            ),
        }

    # ------------------------------------------------------------ observations
    def observations(self, device_id: str, hours: float = 6.0) -> list[dict[str, Any]]:
        window = self.readings.recent(device_id, hours=hours)
        if len(window) < 3:
            return []
        out: list[dict[str, Any]] = []
        now = utcnow()

        def add(kind: str, importance: str, text: str, evidence: dict[str, Any]) -> None:
            out.append(
                {
                    "id": f"{kind}-{len(out)}",
                    "kind": kind,
                    "importance": importance,
                    "text": text,
                    "evidence": evidence,
                    "generated_from": "computed",
                }
            )

        for metric, label in (
            ("temperature_c", "Temperature"),
            ("humidity_pct", "Humidity"),
            ("pressure_hpa", "Pressure"),
            ("air_quality_index", "Air quality"),
        ):
            series = self.metric_series(window, metric, include_points=False)
            if series["sample_count"] < 5 or series["slope_per_minute"] is None:
                continue
            change = series["change"]
            r2 = series["r_squared"] or 0.0
            span_minutes = max(1.0, self._window_minutes(window))
            if series["trend"] in ("rising", "falling") and abs(change) > 0 and r2 >= 0.25:
                direction = "increased" if change > 0 else "decreased"
                spec = REGISTRY[metric]
                importance = "info"
                if metric == "air_quality_index" and change > 0:
                    importance = "warning"
                add(
                    "trend",
                    importance,
                    f"{label} has {direction} by {abs(change):.1f} {spec.unit} over the "
                    f"previous {span_minutes / 60:.1f} hours (trend R² = {r2:.2f}, "
                    f"{series['sample_count']} samples).",
                    {
                        "metric": metric,
                        "change": change,
                        "slope_per_minute": series["slope_per_minute"],
                        "r_squared": r2,
                        "samples": series["sample_count"],
                    },
                )

        # air-quality deterioration streak (consecutive non-improving samples)
        streak = self._deterioration_streak(window, "air_quality_index")
        if streak and streak["minutes"] >= 20 and streak["net_change"] >= 8:
            add(
                "deterioration",
                "warning",
                f"Air quality has been deteriorating for roughly "
                f"{streak['minutes']:.0f} minutes (index +{streak['net_change']:.0f}).",
                streak,
            )

        # baseline comparison for humidity and temperature
        for metric, label, threshold in (
            ("humidity_pct", "Humidity", 6.0),
            ("temperature_c", "Temperature", 1.5),
        ):
            comparison = self._baseline_comparison(window, metric, threshold)
            if comparison:
                add(
                    "baseline",
                    "notice",
                    f"{label} is {comparison['delta']:+.2f} {comparison['unit']} versus the "
                    f"recent baseline of {comparison['baseline']:.2f} {comparison['unit']}.",
                    comparison,
                )

        # pressure tendency
        pressure_values = [(ensure_utc(r.received_at), r.pressure_hpa) for r in window if r.pressure_hpa is not None]
        if len(pressure_values) >= 4:
            first_ts, first_value = pressure_values[0]
            last_ts, last_value = pressure_values[-1]
            hours_span = max(0.01, ((last_ts or now) - (first_ts or now)).total_seconds() / 3600)
            change = float(last_value) - float(first_value)
            tendency = environment.barometric_tendency(change if hours_span >= 2 else None)
            if abs(change) >= 1.5:
                add(
                    "pressure",
                    "info",
                    f"Barometric pressure is {tendency} ({change:+.1f} hPa over {hours_span:.1f} hours).",
                    {"change_hpa": round(change, 2), "hours": round(hours_span, 2)},
                )

        # rain onset
        rain_rows = [(ensure_utc(r.received_at), r.rain_pct) for r in window if r.rain_pct is not None]
        wet = [(ts, value) for ts, value in rain_rows if value >= 10]
        if wet and rain_rows:
            first_wet = wet[0][0]
            if first_wet and (len(rain_rows) - len(wet)) > 0 and (now - first_wet).total_seconds() < hours * 3600:
                add(
                    "rain",
                    "info",
                    f"Rain was first detected at {first_wet.astimezone().strftime('%H:%M')} "
                    f"and wetness is currently {rain_rows[-1][1]:.0f} %.",
                    {"first_wet_at": first_wet.isoformat(), "current_wetness": rain_rows[-1][1]},
                )

        correlations = self.correlations(device_id, hours=hours, limit=2)
        for pair in correlations:
            add(
                "correlation",
                "notice",
                pair["message"],
                pair,
            )

        anomalies = self.anomalies_in_window(window)
        if anomalies:
            add(
                "anomaly",
                "warning",
                f"{len(anomalies)} sensor anomal"
                f"{'y' if len(anomalies) == 1 else 'ies'} detected recently "
                f"({', '.join(REGISTRY[a['sensor']].label for a in anomalies[:3] if a.get('sensor') in REGISTRY)}).",
                {"anomalies": anomalies[:5]},
            )

        order = {"critical": 0, "warning": 1, "notice": 2, "info": 3}
        out.sort(key=lambda item: order.get(str(item["importance"]), 4))
        return out[:8]

    def anomalies_in_window(self, rows: Sequence[SensorReading]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in rows:
            for anomaly in row.anomalies or []:
                out.append(dict(anomaly))
        # newest first, cap for payload size
        out.reverse()
        return out[:20]

    def _window_minutes(self, rows: Sequence[SensorReading]) -> float:
        first = ensure_utc(rows[0].received_at)
        last = ensure_utc(rows[-1].received_at)
        if not first or not last:
            return 0.0
        return (last - first).total_seconds() / 60.0

    def _deterioration_streak(
        self, rows: Sequence[SensorReading], metric: str
    ) -> dict[str, Any] | None:
        series = [
            (ensure_utc(r.received_at), float(getattr(r, metric)))
            for r in rows
            if getattr(r, metric) is not None
        ]
        if len(series) < 4:
            return None
        tolerance = 0.5
        streak_start = len(series) - 1
        for index in range(len(series) - 1, 0, -1):
            if series[index][1] >= series[index - 1][1] - tolerance:
                streak_start = index - 1
            else:
                break
        if streak_start >= len(series) - 1:
            return None
        start_ts, start_value = series[streak_start]
        end_ts, end_value = series[-1]
        if not start_ts or not end_ts:
            return None
        return {
            "metric": metric,
            "minutes": round((end_ts - start_ts).total_seconds() / 60, 1),
            "net_change": round(end_value - start_value, 2),
            "from_value": start_value,
            "to_value": end_value,
            "from_timestamp": start_ts.isoformat(),
            "samples": len(series) - streak_start,
        }

    def _baseline_comparison(
        self, rows: Sequence[SensorReading], metric: str, threshold: float
    ) -> dict[str, Any] | None:
        values = [float(getattr(r, metric)) for r in rows if getattr(r, metric) is not None]
        if len(values) < 10:
            return None
        recent = values[-5:]
        baseline = values[:-5]
        baseline_mean = mean(baseline)
        sigma = robust_sigma(baseline)
        delta = mean(recent) - baseline_mean
        if abs(delta) < threshold and (sigma <= 0 or abs(delta) < 1.5 * sigma):
            return None
        spec = REGISTRY.get(metric)
        return {
            "metric": metric,
            "delta": round(delta, 2),
            "baseline": round(baseline_mean, 2),
            "recent_mean": round(mean(recent), 2),
            "sigma": round(sigma, 2),
            "unit": spec.unit if spec else "",
            "baseline_samples": len(baseline),
        }

    # ------------------------------------------------------------ correlations
    def correlations(
        self, device_id: str, hours: float = 6.0, limit: int = 4
    ) -> list[dict[str, Any]]:
        window = self.readings.recent(device_id, hours=hours)
        if len(window) < 10:
            return []
        pairs = (
            ("temperature_c", "humidity_pct"),
            ("temperature_c", "pressure_hpa"),
            ("humidity_pct", "air_quality_index"),
            ("air_quality_index", "pressure_hpa"),
            ("light_pct", "temperature_c"),
        )
        results: list[dict[str, Any]] = []
        for left, right in pairs:
            xs = [float(getattr(r, left)) for r in window if getattr(r, left) is not None and getattr(r, right) is not None]
            ys = [float(getattr(r, right)) for r in window if getattr(r, left) is not None and getattr(r, right) is not None]
            r_value = pearson(xs, ys)
            if r_value is None or abs(r_value) < 0.5:
                continue
            strength = "strong" if abs(r_value) >= 0.75 else "moderate"
            direction = "positive" if r_value > 0 else "negative"
            results.append(
                {
                    "left": left,
                    "right": right,
                    "r": round(r_value, 3),
                    "samples": len(xs),
                    "hours": hours,
                    "message": (
                        f"{REGISTRY[left].label} and {REGISTRY[right].label} show a {strength} "
                        f"{direction} correlation over the last {hours:g} hours "
                        f"(r = {r_value:+.2f}, n = {len(xs)})."
                    ),
                }
            )
        results.sort(key=lambda item: abs(item["r"]), reverse=True)
        return results[:limit]

    # ---------------------------------------------------------------- overview
    def overview(self, device_id: str, hours: float | None = None) -> dict[str, Any]:
        hours = hours or self.settings.analytics_default_hours
        now = utcnow()
        latest_row = self.readings.latest(device_id)
        window = self.readings.recent(device_id, hours=hours)
        device = self.devices.get(device_id)
        latest = self.reading_to_dict(latest_row, now=now)

        metrics = self._metrics_from_row(latest_row)
        anomalies = list(latest_row.anomalies or []) if latest_row else []
        if not anomalies and window:
            anomalies = self.anomalies_in_window(window)[:10]
        trend = self.trend_context(device_id, hours=min(3.0, hours))
        risk_assessment = self.risk.assess(
            self._risk_inputs(latest_row, metrics, anomalies, trend)
        )
        active_alerts = self.alerts.list(device_id, active_only=True, limit=10)
        health = self.sensor_health(device_id)
        stale = bool(latest.get("is_stale")) if latest else True

        return {
            "device_id": device_id,
            "server_time": now.isoformat(),
            "range_hours": hours,
            "reading_count": len(window),
            "has_data": latest_row is not None,
            "data_source": latest_row.source if latest_row else "unknown",
            "stale": stale,
            "latest": latest,
            "metrics": metrics,
            "channels": self.channel_cards(device_id, hours=hours),
            "risk": risk_assessment,
            "anomalies": anomalies,
            "anomaly_counts": _severity_counts(anomalies),
            "alerts": [alert.as_dict() for alert in active_alerts],
            "active_alert_count": self.alerts.count(device_id, active_only=True),
            "observation_list": self.observations(device_id, hours=hours),
            "classification": self.classification(metrics),
            "correlations": self.correlations(device_id, hours=hours, limit=3),
            "sensor_health": health,
            "device": self._device_summary(device, latest_row, now),
            "heat_index_c": latest.get("heat_index_c"),
            "dew_point_c": latest.get("dew_point_c"),
            "sufficient_history": len(window) >= 10,
            "notes": self._notes(latest_row, window),
        }

    def _notes(self, latest_row: SensorReading | None, window: Sequence[SensorReading]) -> list[str]:
        notes: list[str] = []
        if latest_row is None:
            notes.append(
                "No readings stored yet for this device. Flash the Arduino firmware and check "
                "that the node can reach this backend over Wi-Fi."
            )
            return notes
        if len(window) < 10:
            notes.append(
                f"Only {len(window)} readings in the selected window: statistics and predictions need more history."
            )
        return notes

    # -------------------------------------------------------------- history API
    def history(
        self,
        device_id: str,
        *,
        hours: float = 6.0,
        metrics: Iterable[str] | None = None,
        bucket: str | None = None,
        limit: int = 400,
    ) -> dict[str, Any]:
        rows = self.readings.recent(device_id, hours=hours)
        selected = list(metrics) if metrics else [str(ch["primary"]) for ch in CHANNELS.values()]
        bucket_seconds = BUCKETS_SECONDS.get(bucket) if bucket else None
        series = {
            metric: self.metric_series(rows, metric, bucket_seconds=bucket_seconds)
            for metric in selected
            if metric in REGISTRY
        }
        series["risk_score"] = self.metric_series(rows, "risk_score", bucket_seconds=bucket_seconds)
        series["risk_level"] = self.metric_series(rows, "risk_level", bucket_seconds=bucket_seconds)
        notes: list[str] = []
        if not rows:
            notes.append("No historical data for this window.")
        elif len(rows) < 10:
            notes.append("Limited history: trends and forecasts have low confidence.")
        return {
            "device_id": device_id,
            "range_hours": hours,
            "bucket": bucket,
            "count": len(rows),
            "from_timestamp": (
                (ensure_utc(rows[0].received_at) or utcnow()).isoformat() if rows else None
            ),
            "to_timestamp": (
                (ensure_utc(rows[-1].received_at) or utcnow()).isoformat() if rows else None
            ),
            "readings": [
                self.reading_to_dict(row) for row in rows[-limit:]
            ],
            "series": series,
            "sufficient_data": len(rows) >= 10,
            "notes": notes,
        }

    def aggregates(self, device_id: str, hours: float, bucket: str) -> list[dict[str, Any]]:
        bucket_seconds = BUCKETS_SECONDS.get(bucket, 300)
        start = utcnow() - timedelta(hours=hours)
        return self.readings.aggregate(device_id, start, utcnow(), bucket_seconds)

    # -------------------------------------------------------------- summaries
    def summary(self, device_id: str, period: str = "day") -> dict[str, Any]:
        hours = 24.0 if period == "day" else 168.0
        rows = self.readings.recent(device_id, hours=hours)
        metrics: dict[str, dict[str, float | None]] = {}
        for key in list(CHANNELS[key]["primary"] for key in CHANNEL_ORDER):  # type: ignore[misc]
            series = self.metric_series(rows, str(key), include_points=False)
            if series["sample_count"]:
                metrics[str(key)] = {
                    "min": series["minimum"],
                    "max": series["maximum"],
                    "mean": series["mean"],
                    "median": series["median"],
                    "p95": series["p95"],
                    "stdev": series["stdev"],
                    "latest": series["latest"],
                    "change": series["change"],
                    "trend": series["trend"],
                }
        risk_series = self.metric_series(rows, "risk_score", include_points=False)
        level_values = [r.risk_level for r in rows if r.risk_level is not None]
        risk_stats: dict[str, Any] = {
            "min": risk_series["minimum"],
            "max": risk_series["maximum"],
            "mean": risk_series["mean"],
            "latest": risk_series["latest"],
            "trend": risk_series["trend"],
            "worst_level": max(level_values) if level_values else None,
            "level_distribution": _distribution(level_values),
            "diagnostics_available": risk_series["sample_count"] >= 10,
        }
        since = utcnow() - timedelta(hours=hours)
        alert_rows = self.alerts.list(device_id, since=since, limit=500)
        severity_counts = _severity_counts([{"severity": a.severity} for a in alert_rows])
        anomaly_counts: dict[str, int] = {}
        for row in rows:
            for anomaly in row.anomalies or []:
                key = str(anomaly.get("sensor", "unknown"))
                anomaly_counts[key] = anomaly_counts.get(key, 0) + 1
        expected = max(1, int(hours * 3600 / self.settings.expected_transmission_interval_seconds))
        highlights = [item["text"] for item in self.observations(device_id, hours=hours)[:3]]
        return {
            "device_id": device_id,
            "period": period,
            "from_timestamp": (
                (ensure_utc(rows[0].received_at) or utcnow()).isoformat() if rows else None
            ),
            "to_timestamp": (
                (ensure_utc(rows[-1].received_at) or utcnow()).isoformat() if rows else None
            ),
            "reading_count": len(rows),
            "coverage_pct": round(min(100.0, len(rows) / expected * 100), 1),
            "metrics": metrics,
            "risk": risk_stats,
            "alerts": severity_counts,
            "anomalies_by_sensor": anomaly_counts,
            "highlights": highlights,
        }

    # ----------------------------------------------------------- sensor health
    def sensor_health(self, device_id: str) -> list[dict[str, Any]]:
        window = self.readings.recent(device_id, hours=1)
        latest_row = self.readings.latest(device_id)
        now = utcnow()
        last_received = ensure_utc(latest_row.received_at) if latest_row else None
        expected_rate = 60.0 / max(1, self.settings.expected_transmission_interval_seconds)
        out: list[dict[str, Any]] = []
        for channel_key in CHANNEL_ORDER:
            channel = CHANNELS[channel_key]
            primary = str(channel["primary"])
            spec = REGISTRY[primary]
            present = [r for r in window if getattr(r, primary) is not None]
            last_with_value = None
            for row in reversed(window):
                if getattr(row, primary) is not None:
                    last_with_value = row
                    break
            age = None
            if last_with_value is not None:
                received = ensure_utc(last_with_value.received_at)
                age = (now - received).total_seconds() if received else None
            observed_rate = len(present) / max(1e-6, (self._window_minutes(window) / 60 or 1)) if window else 0.0
            coverage = (len(present) / len(window) * 100) if window else 0.0
            if not window:
                status, message = "unknown", "No readings yet - waiting for data."
            elif not present:
                status, message = "failed", f"{spec.label} has no values in the last hour."
            elif age is not None and age > self.settings.stale_reading_seconds * 3:
                status, message = (
                    "stale",
                    f"Last {spec.label} value is {age / 60:.1f} minutes old.",
                )
            elif last_with_value is not None and any(
                a.get("sensor") == primary and a.get("kind") == "stuck"
                for a in (last_with_value.anomalies or [])
            ):
                status, message = "suspect", f"{spec.label} appears stuck at a constant value."
            elif coverage < 60:
                status, message = (
                    "degraded",
                    f"{spec.label} reported in {coverage:.0f}% of the recent readings.",
                )
            else:
                status, message = "ok", f"{spec.label} reporting normally."
            out.append(
                {
                    "key": primary,
                    "label": spec.label,
                    "channel": channel_key,
                    "status": status,
                    "last_value": getattr(last_with_value, primary) if last_with_value else None,
                    "unit": spec.unit,
                    "last_seen_at": (
                        (ensure_utc(last_with_value.received_at) or now).isoformat()
                        if last_with_value
                        else None
                    ),
                    "age_seconds": round(age, 1) if age is not None else None,
                    "expected_rate_per_minute": round(expected_rate, 2),
                    "observed_rate_per_minute": round(observed_rate, 2),
                    "coverage_pct": round(coverage, 1),
                    "message": message,
                }
            )
        _ = last_received
        return out

    def health_score(self, device_id: str) -> float:
        health = self.sensor_health(device_id)
        if not health:
            return 0.0
        weights = {"ok": 1.0, "degraded": 0.6, "suspect": 0.4, "stale": 0.3, "failed": 0.0, "unknown": 0.0}
        score = sum(weights.get(str(item["status"]), 0.0) for item in health) / len(health) * 100
        return round(score, 1)

    # ----------------------------------------------------------------- helpers
    def _metrics_from_row(self, row: SensorReading | None) -> dict[str, float | None]:
        if row is None:
            return {key: None for key in REGISTRY}
        metrics: dict[str, float | None] = {}
        for key in REGISTRY:
            value = getattr(row, key, None)
            metrics[key] = float(value) if value is not None else None
        # Derived metrics are computed for the risk engine and the UI even when the
        # stored value is missing (e.g. rows written before a schema addition).
        metrics["heat_index_c"] = (
            float(row.heat_index_c)
            if row.heat_index_c is not None
            else environment.heat_index_c(metrics.get("temperature_c"), metrics.get("humidity_pct"))
        )
        metrics["dew_point_c"] = (
            float(row.dew_point_c)
            if row.dew_point_c is not None
            else environment.dew_point_c(metrics.get("temperature_c"), metrics.get("humidity_pct"))
        )
        return metrics

    def _risk_inputs(
        self,
        row: SensorReading | None,
        metrics: dict[str, float | None],
        anomalies: list[dict[str, Any]],
        trend: dict[str, float | None],
    ) -> Any:
        from .risk_service import RiskInputs

        missing = [] if row is None else [
            key for key in CHANNELS if metrics.get(CHANNELS[key]["primary"]) is None
        ]
        age = None
        if row is not None:
            received = ensure_utc(row.received_at)
            age = (utcnow() - received).total_seconds() if received else None
        return RiskInputs(
            metrics=metrics,
            anomalies=list(anomalies),
            trend=trend,
            missing_metrics=[str(m) for m in missing],
            data_age_seconds=age,
            source=row.source if row else "unknown",
            heat_index_c=metrics.get("heat_index_c"),
        )

    def _device_summary(
        self, device: Any, latest_row: SensorReading | None, now: datetime
    ) -> dict[str, Any]:
        if device is None:
            return {
                "device_id": self.settings.device_id,
                "online": False,
                "status": "offline",
                "status_message": (
                    "Waiting for the Arduino UNO R4 Wi-Fi to send sensor data. "
                    "This is expected until the firmware is flashed and the node reaches this backend."
                ),
                "last_seen_at": None,
                "seconds_since_last_payload": None,
            }
        threshold = self.settings.device_online_threshold_seconds
        last_payload = ensure_utc(device.last_payload_at) or ensure_utc(device.last_seen_at)
        age = (now - last_payload).total_seconds() if last_payload else None
        online = age is not None and age <= threshold
        return {
            "device_id": device.device_id,
            "display_name": device.display_name,
            "online": online,
            "status": "online" if online else "offline",
            "status_message": (
                "Receiving data normally."
                if online
                else device.notes
                or "No payload received recently. Check power, Wi-Fi and the backend port."
            ),
            "last_seen_at": last_payload.isoformat() if last_payload else None,
            "seconds_since_last_payload": round(age, 1) if age is not None else None,
            "firmware_version": device.firmware_version,
            "ip_address": device.ip_address,
            "source": device.source,
            "latest_reading_id": latest_row.id if latest_row else None,
        }

    def moving_averages(self, device_id: str, metric: str, window: int = 5, hours: float = 1.0) -> list[float]:
        rows = self.readings.recent(device_id, hours=hours)
        values = [float(getattr(r, metric)) for r in rows if getattr(r, metric) is not None]
        return [round(v, 3) for v in moving_average(values, window)]


def _severity_counts(anomalies: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts = {"low": 0, "medium": 0, "high": 0}
    for item in anomalies:
        severity = str(item.get("severity", "low"))
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _distribution(values: Sequence[int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        key = str(value)
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


__all__ = ["AnalyticsService", "MONITORED_METRICS", "BUCKETS_SECONDS"]
