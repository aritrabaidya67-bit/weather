"""Environmental derivations and unit conversions.

Every formula here is a published approximation, quoted so the platform never
claims more precision than the sensor chain can deliver.
"""

from __future__ import annotations

import math

from .stats import clamp

# --------------------------------------------------------------------- derived
# Heat index: NWS/Rothfusz regression (valid for T >= 26.7 C and RH >= 40 %).
# Below the validity domain we return None instead of a fabricated number, and
# the UI shows "not applicable" - which is the truthful answer.
def heat_index_c(temperature_c: float | None, humidity_pct: float | None) -> float | None:
    if temperature_c is None or humidity_pct is None:
        return None
    t = temperature_c
    rh = humidity_pct
    if t < 26.7:
        return None
    t_f = t * 9 / 5 + 32
    hi_f = (
        -42.379
        + 2.04901523 * t_f
        + 10.14333127 * rh
        - 0.22475541 * t_f * rh
        - 6.83783e-3 * t_f**2
        - 5.481717e-2 * rh**2
        + 1.22874e-3 * t_f**2 * rh
        + 8.5282e-4 * t_f * rh**2
        - 1.99e-6 * t_f**2 * rh**2
    )
    if rh < 13 and 80 <= t_f <= 112:
        hi_f -= ((13 - rh) / 4) * math.sqrt((17 - abs(t_f - 95)) / 17) if abs(t_f - 95) <= 17 else 0
    elif rh > 85 and 80 <= t_f <= 87:
        hi_f += ((rh - 85) / 10) * ((87 - t_f) / 5)
    return round((hi_f - 32) * 5 / 9, 1)


# Dew point: Magnus/Tetens approximation (accuracy ~ +-0.4 C over 0..60 C).
def dew_point_c(temperature_c: float | None, humidity_pct: float | None) -> float | None:
    if temperature_c is None or humidity_pct is None or humidity_pct <= 0:
        return None
    a, b = 17.62, 243.12
    gamma = (a * temperature_c) / (b + temperature_c) + math.log(humidity_pct / 100.0)
    return round((b * gamma) / (a - gamma), 1)


# Absolute humidity in g/m3 (ideal gas approximation) - informative only.
def absolute_humidity_g_m3(temperature_c: float | None, humidity_pct: float | None) -> float | None:
    if temperature_c is None or humidity_pct is None:
        return None
    saturation = 6.112 * math.exp((17.67 * temperature_c) / (temperature_c + 243.5))
    vapour_pressure = saturation * humidity_pct / 100.0
    return round(216.7 * vapour_pressure / (temperature_c + 273.15), 2)


# ------------------------------------------------------------------- normalising
def rain_pct_from_raw(raw: float | None, dry_adc: float, wet_adc: float) -> float | None:
    """Wetness index 0..100 from the rain board's 10-bit ADC reading."""
    if raw is None:
        return None
    span = dry_adc - wet_adc
    if abs(span) < 1e-6:
        return None
    return round(clamp((dry_adc - raw) / span * 100.0, 0.0, 100.0), 1)


def light_pct_from_raw(raw: float | None, dark_adc: float, bright_adc: float) -> float | None:
    """Relative illumination index 0..100 from the LDR divider.

    Note: an LDR's resistance vs illuminance curve is strongly non-linear and the
    divider is uncalibrated, so this is a *relative* index, not lux.
    """
    if raw is None:
        return None
    span = bright_adc - dark_adc
    if abs(span) < 1e-6:
        return None
    return round(clamp((raw - dark_adc) / span * 100.0, 0.0, 100.0), 1)


def air_quality_index_from_raw(
    raw: float | None, clean_baseline: float, max_reference: float
) -> float | None:
    """Relative air-quality index 0..100 (higher = more pollutants).

    Derived from an MQ-135 ADC reading against a configurable clean-air baseline.
    This is intentionally *not* a ppm conversion: the datasheet curve needs an R0
    calibration in clean air plus heater burn-in, so publishing ppm here would be
    manufactured precision.
    """
    if raw is None:
        return None
    span = max_reference - clean_baseline
    if abs(span) < 1e-6:
        return None
    return round(clamp((raw - clean_baseline) / span * 100.0, 0.0, 100.0), 1)


# ---------------------------------------------------------------------- status
# Status bands mirror app/core/sensors.py so the Arduino, backend and UI agree.
RAIN_BANDS = ((5.0, "dry"), (40.0, "light rain"), (75.0, "rain"), (100.0, "heavy rain"))
LIGHT_BANDS = ((5.0, "dark"), (35.0, "dim"), (70.0, "moderate"), (100.0, "bright"))
AIR_BANDS = ((25.0, "good"), (50.0, "moderate"), (75.0, "poor"), (100.0, "hazardous"))


def _band_label(value: float | None, bands: tuple[tuple[float, str], ...]) -> str | None:
    if value is None:
        return None
    for until, label in bands:
        if value <= until:
            return label
    return bands[-1][1]


def rain_status(rain_pct: float | None) -> str | None:
    return _band_label(rain_pct, RAIN_BANDS)


def light_status(light_pct: float | None) -> str | None:
    return _band_label(light_pct, LIGHT_BANDS)


def air_quality_status(index: float | None) -> str | None:
    return _band_label(index, AIR_BANDS)


def barometric_tendency(change_hpa_3h: float | None) -> str:
    """Standard meteorological pressure-tendency wording."""
    if change_hpa_3h is None:
        return "unknown"
    if change_hpa_3h <= -4:
        return "rapidly falling"
    if change_hpa_3h <= -1:
        return "falling"
    if change_hpa_3h >= 4:
        return "rapidly rising"
    if change_hpa_3h >= 1:
        return "rising"
    return "steady"
