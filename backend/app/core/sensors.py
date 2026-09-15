"""Central sensor registry.

Every sensor known to the platform is described here exactly once. Validation
ranges, units, chart metadata, interpretation bands, anomaly sensitivities and
legacy payload aliases all derive from this registry, so the Arduino firmware,
the simulator, the analytics engine and the frontend metadata endpoint cannot
drift apart.

Sources for the physical ranges below (kept deliberately conservative and
documented so no fabricated precision is introduced):

* DHT12 / AM2302 (temperature): -40..80 C, accuracy ~ +-0.5 C, resolution 0.1 C
* DHT12 / AM2302 (humidity):     0..100 %RH, accuracy ~ +-2..5 %RH
* BMP280 (pressure):             300..1100 hPa, accuracy ~ +-1 hPa
* Rain sensor (analog):          10-bit ADC -> 0..1023 raw counts
                                  (dry ~ 900-1023, wet ~ 300-700, soaked < 300)
* LDR (analog):                  10-bit ADC -> 0..1023 raw counts
* MQ-135 (analog):               10-bit ADC -> 0..1023 raw counts. The absolute
                                  concentration needs calibration (R0 in clean
                                  air); without calibration we only expose a
                                  normalised *relative* index, never ppm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SensorKind = Literal["numeric", "status"]


@dataclass(frozen=True)
class InterpretationBand:
    """A human readable interpretation for a numeric slice of a sensor."""

    until: float
    label: str
    severity: Literal["good", "info", "watch", "warning", "critical"]


@dataclass(frozen=True)
class SensorSpec:
    key: str
    label: str
    unit: str
    kind: SensorKind
    minimum: float | None
    maximum: float | None
    decimals: int
    color: str
    description: str
    plausible_delta_per_min: float
    bands: tuple[InterpretationBand, ...] = field(default_factory=tuple)
    aliases: tuple[str, ...] = field(default_factory=tuple)
    calibration_notes: str = ""

    def clamp(self, value: float) -> float:
        if self.minimum is not None and value < self.minimum:
            return self.minimum
        if self.maximum is not None and value > self.maximum:
            return self.maximum
        return value

    def interpret(self, value: float) -> tuple[str, str]:
        """Return (label, severity) for a numeric value."""
        for band in self.bands:
            if value <= band.until:
                return band.label, band.severity
        if self.bands:
            last = self.bands[-1]
            return last.label, last.severity
        return "unknown", "info"


RAIN_STATUS_BANDS = (
    InterpretationBand(5.0, "dry", "good"),
    InterpretationBand(40.0, "light rain", "info"),
    InterpretationBand(75.0, "rain", "watch"),
    InterpretationBand(100.0, "heavy rain", "warning"),
)

LIGHT_STATUS_BANDS = (
    InterpretationBand(5.0, "dark", "info"),
    InterpretationBand(35.0, "dim", "info"),
    InterpretationBand(70.0, "moderate", "good"),
    InterpretationBand(100.0, "bright", "good"),
)

AIR_QUALITY_BANDS = (
    InterpretationBand(25.0, "good", "good"),
    InterpretationBand(50.0, "moderate", "info"),
    InterpretationBand(75.0, "poor", "warning"),
    InterpretationBand(100.0, "hazardous", "critical"),
)


REGISTRY: dict[str, SensorSpec] = {
    "temperature_c": SensorSpec(
        key="temperature_c",
        label="Temperature",
        unit="degC",
        kind="numeric",
        minimum=-40.0,
        maximum=85.0,
        decimals=1,
        color="#f97316",
        description="Ambient air temperature measured by the DHT12 / AM2302 sensor.",
        plausible_delta_per_min=2.5,
        bands=(
            InterpretationBand(0.0, "freezing", "warning"),
            InterpretationBand(10.0, "cold", "info"),
            InterpretationBand(18.0, "cool", "good"),
            InterpretationBand(26.0, "comfortable", "good"),
            InterpretationBand(32.0, "warm", "watch"),
            InterpretationBand(38.0, "hot", "warning"),
            InterpretationBand(100.0, "extreme heat", "critical"),
        ),
        aliases=("temperature_dht", "temperature", "temp", "temp_c", "dht_temperature_c"),
        calibration_notes="DHT12/AM2302 digital output; typical accuracy +-0.5 degC.",
    ),
    "humidity_pct": SensorSpec(
        key="humidity_pct",
        label="Relative Humidity",
        unit="%RH",
        kind="numeric",
        minimum=0.0,
        maximum=100.0,
        decimals=1,
        color="#38bdf8",
        description="Relative humidity measured by the DHT12 / AM2302 sensor.",
        plausible_delta_per_min=5.0,
        bands=(
            InterpretationBand(20.0, "very dry", "watch"),
            InterpretationBand(30.0, "dry", "info"),
            InterpretationBand(60.0, "comfortable", "good"),
            InterpretationBand(75.0, "humid", "watch"),
            InterpretationBand(90.0, "very humid", "warning"),
            InterpretationBand(100.0, "saturated", "critical"),
        ),
        aliases=("humidity", "rh", "relative_humidity", "humidity_percent"),
        calibration_notes="DHT12/AM2302 digital output; typical accuracy +-2..5 %RH.",
    ),
    "bmp_temperature_c": SensorSpec(
        key="bmp_temperature_c",
        label="BMP280 Temperature",
        unit="degC",
        kind="numeric",
        minimum=-40.0,
        maximum=85.0,
        decimals=1,
        color="#fb923c",
        description="Second temperature channel from the BMP280 (used for cross-checks).",
        plausible_delta_per_min=2.5,
        aliases=("temperature_bmp", "bmp_temp", "bmp280_temperature_c"),
    ),
    "pressure_hpa": SensorSpec(
        key="pressure_hpa",
        label="Barometric Pressure",
        unit="hPa",
        kind="numeric",
        minimum=300.0,
        maximum=1100.0,
        decimals=1,
        color="#a78bfa",
        description="Barometric pressure from the BMP280. Fast drops indicate incoming weather.",
        plausible_delta_per_min=3.0,
        bands=(
            InterpretationBand(980.0, "very low - stormy", "warning"),
            InterpretationBand(1000.0, "low", "info"),
            InterpretationBand(1020.0, "normal", "good"),
            InterpretationBand(1035.0, "high", "info"),
            InterpretationBand(1100.0, "very high", "info"),
        ),
        aliases=("pressure", "pressure_pa", "barometric_pressure_hpa"),
        calibration_notes="BMP280: 300..1100 hPa, relative accuracy ~ +-0.12 hPa.",
    ),
    "rain_raw": SensorSpec(
        key="rain_raw",
        label="Rain Raw",
        unit="ADC",
        kind="numeric",
        minimum=0.0,
        maximum=1023.0,
        decimals=0,
        color="#60a5fa",
        description="Raw 10-bit ADC value of the rain sensor board (higher = drier).",
        plausible_delta_per_min=400.0,
        aliases=("rain", "rain_adc", "rain_value"),
        calibration_notes="Analog rain board: dry ~900-1023, wet ~300-700, soaked <300 counts.",
    ),
    "rain_pct": SensorSpec(
        key="rain_pct",
        label="Rainfall Intensity",
        unit="%",
        kind="numeric",
        minimum=0.0,
        maximum=100.0,
        decimals=1,
        color="#3b82f6",
        description="Wetness index derived from the rain sensor ADC (0 = dry, 100 = fully wet).",
        plausible_delta_per_min=60.0,
        bands=RAIN_STATUS_BANDS,
        aliases=("rain_level", "wetness_pct"),
    ),
    "ldr_raw": SensorSpec(
        key="ldr_raw",
        label="Light Raw",
        unit="ADC",
        kind="numeric",
        minimum=0.0,
        maximum=1023.0,
        decimals=0,
        color="#facc15",
        description="Raw 10-bit ADC value of the LDR voltage divider (higher = brighter).",
        plausible_delta_per_min=500.0,
        aliases=("light_raw", "ldr", "light_adc"),
    ),
    "light_pct": SensorSpec(
        key="light_pct",
        label="Light Intensity",
        unit="%",
        kind="numeric",
        minimum=0.0,
        maximum=100.0,
        decimals=1,
        color="#eab308",
        description="Normalised illumination index derived from the LDR (uncalibrated, relative).",
        plausible_delta_per_min=60.0,
        bands=LIGHT_STATUS_BANDS,
        aliases=("light_level_pct",),
        calibration_notes=(
            "An LDR is not a calibrated lux meter. Values are a relative illumination "
            "index; a lux figure would require a calibrated sensor."
        ),
    ),
    "air_quality_raw": SensorSpec(
        key="air_quality_raw",
        label="Air Quality Raw",
        unit="ADC",
        kind="numeric",
        minimum=0.0,
        maximum=1023.0,
        decimals=0,
        color="#34d399",
        description="Raw 10-bit ADC value of the MQ-135 gas sensor (higher = more pollutants).",
        plausible_delta_per_min=250.0,
        aliases=("mq135_raw", "gas_raw", "air_raw", "air_quality_adc"),
        calibration_notes=(
            "MQ-135 output depends on heater warm-up (>=24 h for best stability) and "
            "requires R0 calibration in clean air before absolute ppm claims are valid."
        ),
    ),
    "air_quality_index": SensorSpec(
        key="air_quality_index",
        label="Air Quality Index",
        unit="idx",
        kind="numeric",
        minimum=0.0,
        maximum=100.0,
        decimals=0,
        color="#22c55e",
        description="Normalised relative air-quality index (0 = cleanest observed, 100 = worst).",
        plausible_delta_per_min=40.0,
        bands=AIR_QUALITY_BANDS,
        aliases=("air_quality", "aqi", "gas_index"),
        calibration_notes=(
            "Relative index, not an official AQI and not a ppm concentration. It is "
            "derived from the MQ-135 ADC against a configurable clean-air baseline."
        ),
    ),
}

#: The six physical measurement channels the dashboard, simulator and firmware
#: all speak about. Each channel maps to one primary metric plus extra fields.
CHANNELS: dict[str, dict[str, object]] = {
    "temperature": {
        "key": "temperature",
        "label": "Temperature",
        "primary": "temperature_c",
        "secondary": ["bmp_temperature_c"],
        "sensor": "DHT12 / AM2302 + BMP280",
        "icon": "thermometer",
    },
    "humidity": {
        "key": "humidity",
        "label": "Humidity",
        "primary": "humidity_pct",
        "secondary": [],
        "sensor": "DHT12 / AM2302",
        "icon": "droplets",
    },
    "pressure": {
        "key": "pressure",
        "label": "Pressure",
        "primary": "pressure_hpa",
        "secondary": [],
        "sensor": "BMP280",
        "icon": "gauge",
    },
    "air_quality": {
        "key": "air_quality",
        "label": "Air Quality",
        "primary": "air_quality_index",
        "secondary": ["air_quality_raw"],
        "sensor": "MQ-135",
        "icon": "wind",
    },
    "light": {
        "key": "light",
        "label": "Light",
        "primary": "light_pct",
        "secondary": ["ldr_raw"],
        "sensor": "LDR",
        "icon": "sun",
    },
    "rain": {
        "key": "rain",
        "label": "Rain",
        "primary": "rain_pct",
        "secondary": ["rain_raw"],
        "sensor": "Rain sensor board",
        "icon": "cloud-rain",
    },
}

#: Order used by the UI for metric grids.
CHANNEL_ORDER = ("temperature", "humidity", "pressure", "air_quality", "light", "rain")

#: Fields physically present in the hardware payload.
HARDWARE_FIELDS = (
    "temperature_c",
    "humidity_pct",
    "bmp_temperature_c",
    "pressure_hpa",
    "rain_raw",
    "ldr_raw",
    "air_quality_raw",
)

#: Extra fields derived by the backend normalisation step.
DERIVED_FIELDS = ("rain_pct", "light_pct", "air_quality_index")


def channel_for_sensor(key: str) -> str | None:
    for channel_key, channel in CHANNELS.items():
        if channel["primary"] == key or key in channel["secondary"]:  # type: ignore[operator]
            return channel_key
    return None


def resolve_alias(name: str) -> str | None:
    """Map a legacy / alternate field name onto a canonical registry key."""
    if name in REGISTRY:
        return name
    lowered = name.strip().lower()
    for spec in REGISTRY.values():
        if lowered in spec.aliases:
            return spec.key
    return None


def registry_public() -> list[dict[str, object]]:
    """Serialisable registry for the /meta endpoint and the frontend."""
    out: list[dict[str, object]] = []
    for spec in REGISTRY.values():
        out.append(
            {
                "key": spec.key,
                "label": spec.label,
                "unit": spec.unit,
                "kind": spec.kind,
                "minimum": spec.minimum,
                "maximum": spec.maximum,
                "decimals": spec.decimals,
                "color": spec.color,
                "description": spec.description,
                "channel": channel_for_sensor(spec.key),
                "calibration_notes": spec.calibration_notes,
                "bands": [
                    {"until": b.until, "label": b.label, "severity": b.severity} for b in spec.bands
                ],
            }
        )
    return out
