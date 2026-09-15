"""Small statistics helpers.

Implemented in pure Python on purpose: the analytics pipeline only ever works
on a few hundred points, so a NumPy dependency would add install risk (for
example on brand-new CPython releases) without buying measurable speed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def variance(values: list[float], sample: bool = True) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    avg = mean(values)
    total = sum((v - avg) ** 2 for v in values)
    divisor = (n - 1) if sample else n
    return total / divisor if divisor else 0.0


def stdev(values: list[float], sample: bool = True) -> float:
    return math.sqrt(max(variance(values, sample), 0.0))


def robust_sigma(values: list[float]) -> float:
    """MAD-based sigma estimate, resistant to outliers.

    ``1.4826 * MAD`` is the normal-consistent scaling factor for the median
    absolute deviation. Falls back to the classical sample sigma for very small
    samples where MAD collapses to zero.
    """
    if len(values) < 4:
        return stdev(values)
    med = median(values)
    deviations = [abs(v - med) for v in values]
    mad = median(deviations)
    if mad <= 0:
        return stdev(values)
    return 1.4826 * mad


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[int(rank)]
    fraction = rank - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def moving_average(values: list[float], window: int) -> list[float]:
    if window <= 1:
        return list(values)
    out: list[float] = []
    buffer: list[float] = []
    for value in values:
        buffer.append(value)
        if len(buffer) > window:
            buffer.pop(0)
        out.append(mean(buffer))
    return out


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation; ``None`` when it is not statistically meaningful."""
    n = min(len(xs), len(ys))
    if n < 8:
        return None
    xs, ys = xs[:n], ys[:n]
    mx, my = mean(xs), mean(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    denominator = math.sqrt(
        sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)
    )
    if denominator == 0:
        return None
    return numerator / denominator


def slope_per_minute(values: list[float], timestamps: list[float]) -> float | None:
    """Ordinary least squares slope of ``values`` against ``timestamps`` (minutes)."""
    n = min(len(values), len(timestamps))
    if n < 3:
        return None
    xs = timestamps[-n:]
    ys = values[-n:]
    mx, my = mean(xs), mean(ys)
    denominator = sum((x - mx) ** 2 for x in xs)
    if denominator == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / denominator


@dataclass(slots=True)
class LinearFit:
    slope: float
    intercept: float
    r_squared: float
    n: int
    residual_sigma: float

    def predict(self, x: float) -> float:
        return self.intercept + self.slope * x


def linear_fit(xs: list[float], ys: list[float], weights: list[float] | None = None) -> LinearFit | None:
    """Weighted least-squares line fit with fit-quality diagnostics."""
    n = min(len(xs), len(ys))
    if n < 2:
        return None
    xs, ys = xs[:n], ys[:n]
    ws = weights[:n] if weights else [1.0] * n
    total_w = sum(ws)
    if total_w <= 0:
        return None
    mx = sum(x * w for x, w in zip(xs, ws, strict=True)) / total_w
    my = sum(y * w for y, w in zip(ys, ws, strict=True)) / total_w
    sxx = sum(w * (x - mx) ** 2 for x, w in zip(xs, ws, strict=True))
    sxy = sum(w * (x - mx) * (y - my) for x, y, w in zip(xs, ys, ws, strict=True))
    if sxx == 0:
        return None
    slope = sxy / sxx
    intercept = my - slope * mx
    predictions = [intercept + slope * x for x in xs]
    residuals = [y - p for y, p in zip(ys, predictions, strict=True)]
    ss_res = sum(r**2 for r in residuals)
    ss_tot = sum((y - my) ** 2 for y in ys)
    r_squared = 0.0 if ss_tot == 0 else max(0.0, min(1.0, 1 - ss_res / ss_tot))
    resid_sigma = math.sqrt(ss_res / max(1, n - 2))
    return LinearFit(slope, intercept, r_squared, n, resid_sigma)


@dataclass(slots=True)
class HoltLinear:
    """Holt's linear (double exponential smoothing) state."""

    level: float
    trend: float
    residual_sigma: float
    n: int

    def forecast(self, steps: float) -> float:
        return self.level + self.trend * steps


def holt_linear_forecast(
    values: list[float],
    intervals_per_step: float = 1.0,
    alpha: float = 0.35,
    beta: float = 0.12,
) -> HoltLinear | None:
    """Double exponential smoothing.

    ``intervals_per_step`` converts the requested horizon (in sampling intervals)
    into forecast steps. Smoothing constants are deliberately conservative so a
    single noisy sample cannot swing the forecast.
    """
    if len(values) < 4:
        return None
    level = values[0]
    trend = (values[-1] - values[0]) / max(1, len(values) - 1)
    residuals: list[float] = []
    for value in values[1:]:
        forecast = level + trend
        residuals.append(value - forecast)
        last_level = level
        level = alpha * value + (1 - alpha) * (level + trend)
        trend = beta * (level - last_level) + (1 - beta) * trend
    resid_sigma = stdev(residuals) if len(residuals) > 2 else 0.0
    return HoltLinear(level=level, trend=trend * intervals_per_step, residual_sigma=resid_sigma, n=len(values))


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
