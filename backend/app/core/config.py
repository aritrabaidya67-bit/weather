"""Application configuration.

Every environment-specific value lives here and can be overridden through the
``backend/.env`` file or real environment variables. No secret is ever baked
into source control: ``.env.example`` ships placeholders only.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
#: Config files referenced relatively (RISK_CONFIG_FILE) resolve against backend/.
PROJECT_DIR = BACKEND_DIR


# --------------------------------------------------------------------------
# Risk model configuration
# --------------------------------------------------------------------------
class RiskLevelSpec(BaseModel):
    level: int
    code: str
    label: str
    min_score: float
    description: str
    color: str


class RiskBand(BaseModel):
    """A scoring band for a single factor.

    ``until`` is the inclusive upper bound of the band and ``points`` the
    fraction (0..1) of the factor weight earned inside that band. Bands are
    evaluated in order, so they must be declared worst-first for factors where
    lower values are worse (air quality) or best-first otherwise.
    """

    until: float
    points: float
    reason: str | None = None


class CombinationRule(BaseModel):
    """Cross-sensor rule: poor conditions that are only risky when combined.

    Each condition is ``{metric: {"min": x, "max": y}}``; every condition must
    hold for the rule to fire. Rules exist because single-sensor thresholds miss
    things like heat stress (temperature *and* humidity) by construction.
    """

    id: str
    label: str
    reason: str
    action: str
    points: float
    conditions: dict[str, dict[str, float]]


class RiskFactorConfig(BaseModel):
    key: str
    label: str
    weight: float
    inversion: Literal["low_is_good", "high_is_good"] = "low_is_good"
    bands: list[RiskBand]
    supported: bool = True
    note: str | None = None


class RiskConfig(BaseModel):
    """Fully explainable, configurable risk model.

    The default numbers are engineering heuristics anchored on published
    comfort/health guidance (ASHRAE 55 comfort envelope for temperature and
    humidity, WHO air-quality guidance for the relative air index, and standard
    meteorological pressure-trend rules). They are *not* presented as regulatory
    thresholds; they can be replaced atomically through ``RISK_CONFIG_FILE``.
    """

    version: str = "1.0.0"
    description: str = "Configurable multi-factor environmental risk model (0-100)."
    factors: list[RiskFactorConfig] = Field(
        default_factory=lambda: [
            RiskFactorConfig(
                key="air_quality",
                label="Air quality",
                weight=30.0,
                bands=[
                    RiskBand(until=25.0, points=0.0, reason="Air quality is in the good range"),
                    RiskBand(until=50.0, points=0.35, reason="Air quality moderately degraded"),
                    RiskBand(until=75.0, points=0.75, reason="Air quality significantly degraded"),
                    RiskBand(
                        until=100.0,
                        points=1.0,
                        reason="Air quality is in the hazardous range",
                    ),
                ],
            ),
            RiskFactorConfig(
                key="temperature",
                label="Temperature",
                weight=20.0,
                bands=[
                    RiskBand(until=0.0, points=0.85, reason="Sub-zero ambient temperature"),
                    RiskBand(until=10.0, points=0.5, reason="Cold ambient temperature"),
                    RiskBand(until=18.0, points=0.2, reason="Below the comfortable range"),
                    RiskBand(until=26.0, points=0.0, reason="Temperature inside the comfort envelope"),
                    RiskBand(until=32.0, points=0.3, reason="Above the comfortable range"),
                    RiskBand(until=38.0, points=0.7, reason="Hot conditions, heat stress likely"),
                    RiskBand(until=100.0, points=1.0, reason="Extreme heat, dangerous conditions"),
                ],
            ),
            RiskFactorConfig(
                key="humidity",
                label="Humidity",
                weight=15.0,
                bands=[
                    RiskBand(until=20.0, points=0.6, reason="Very dry air, respiratory irritation risk"),
                    RiskBand(until=30.0, points=0.3, reason="Air is drier than the comfort range"),
                    RiskBand(until=65.0, points=0.0, reason="Humidity inside the comfort range"),
                    RiskBand(until=78.0, points=0.3, reason="Humidity above the comfort range"),
                    RiskBand(until=90.0, points=0.65, reason="Very humid, mould and heat-stress risk"),
                    RiskBand(until=100.0, points=1.0, reason="Air is saturated with moisture"),
                ],
            ),
            RiskFactorConfig(
                key="pressure",
                label="Pressure",
                weight=10.0,
                bands=[
                    RiskBand(until=975.0, points=0.8, reason="Very low pressure, storm conditions"),
                    RiskBand(until=1000.0, points=0.4, reason="Low pressure, unsettled weather"),
                    RiskBand(until=1035.0, points=0.0, reason="Pressure in the normal range"),
                    RiskBand(until=1100.0, points=0.15, reason="Unusually high pressure"),
                ],
            ),
            RiskFactorConfig(
                key="rain",
                label="Rain / wetness",
                weight=10.0,
                bands=[
                    RiskBand(until=5.0, points=0.0, reason="No rain detected"),
                    RiskBand(until=40.0, points=0.3, reason="Light rain detected"),
                    RiskBand(until=75.0, points=0.6, reason="Continuous rain detected"),
                    RiskBand(until=100.0, points=0.85, reason="Heavy rain detected"),
                ],
            ),
            RiskFactorConfig(
                key="light",
                label="Light level",
                weight=5.0,
                supported=True,
                note=(
                    "Light is intentionally a low-weight factor: a dark reading is rarely "
                    "hazardous on its own and an LDR is not a calibrated reference."
                ),
                bands=[
                    RiskBand(until=5.0, points=0.4, reason="Very dark ambient light"),
                    RiskBand(until=35.0, points=0.15, reason="Low ambient light"),
                    RiskBand(until=100.0, points=0.0, reason="Adequate ambient light"),
                ],
            ),
            RiskFactorConfig(
                key="composite",
                label="Anomalies & sensor health",
                weight=10.0,
                supported=False,
                note="Derived from anomaly severity and fraction of healthy sensors.",
                bands=[],
            ),
        ]
    )
    levels: list[RiskLevelSpec] = Field(
        default_factory=lambda: [
            RiskLevelSpec(
                level=1,
                code="VERY_LOW",
                label="Very Low",
                min_score=0.0,
                description="Environment is well inside safe operating conditions.",
                color="#22c55e",
            ),
            RiskLevelSpec(
                level=2,
                code="LOW",
                label="Low",
                min_score=20.0,
                description="Minor deviations from ideal conditions.",
                color="#84cc16",
            ),
            RiskLevelSpec(
                level=3,
                code="MODERATE",
                label="Moderate",
                min_score=40.0,
                description="Noticeable degradation; keep monitoring.",
                color="#eab308",
            ),
            RiskLevelSpec(
                level=4,
                code="HIGH",
                label="High",
                min_score=60.0,
                description="Significant environmental stress; corrective action advised.",
                color="#f97316",
            ),
            RiskLevelSpec(
                level=5,
                code="CRITICAL",
                label="Critical",
                min_score=80.0,
                description="Dangerous conditions; act immediately.",
                color="#ef4444",
            ),
        ]
    )
    #: Cross-sensor stress rules (temperature x humidity, stagnant humid air, ...).
    combination_rules: list[CombinationRule] = Field(
        default_factory=lambda: [
            CombinationRule(
                id="heat_stress",
                label="Heat stress combination",
                reason="High temperature combined with high humidity (heat index {heat_index_c:.1f} degC)",
                action="Reduce heat load (ventilation, shading, cooling) and hydrate regularly",
                points=6.0,
                conditions={
                    "temperature_c": {"min": 30.0},
                    "humidity_pct": {"min": 60.0},
                },
            ),
            CombinationRule(
                id="stagnant_humid_air",
                label="Pollutants trapped in humid air",
                reason="Degraded air quality combined with high humidity (poor ventilation)",
                action="Ventilate the space and reduce pollutant sources",
                points=4.0,
                conditions={
                    "air_quality_index": {"min": 50.0},
                    "humidity_pct": {"min": 75.0},
                },
            ),
            CombinationRule(
                id="storm_tendency",
                label="Storm-prone combination",
                reason="Saturated air together with low pressure (storm-prone conditions)",
                action="Secure the outdoor sensor node and watch for rapid weather changes",
                points=3.0,
                conditions={
                    "humidity_pct": {"min": 80.0},
                    "pressure_hpa": {"max": 1002.0},
                },
            ),
        ]
    )
    #: Trend based escalation thresholds (documented in docs/architecture.md).
    pressure_drop_escalation: list[dict[str, float]] = Field(
        default_factory=lambda: [
            {"drop_hpa": 4.0, "points": 0.75},
            {"drop_hpa": 8.0, "points": 0.95},
        ]
    )
    air_quality_worsening_escalation: list[dict[str, float]] = Field(
        default_factory=lambda: [
            {"slope_per_minute": 0.25, "points": 0.55},
            {"slope_per_minute": 0.6, "points": 0.85},
        ]
    )
    min_anomaly_contribution: float = 0.0
    stale_data_penalty: float = 0.5
    sensor_failure_penalty_per_sensor: float = 0.15
    anomaly_penalty_per_high: float = 0.35
    anomaly_penalty_per_medium: float = 0.2
    anomaly_penalty_per_low: float = 0.08


# --------------------------------------------------------------------------
# Anomaly detection configuration
# --------------------------------------------------------------------------
class AnomalyConfig(BaseModel):
    window_points: int = 60
    min_samples: int = 12
    z_medium: float = 2.5
    z_high: float = 3.5
    sudden_sigma: float = 4.0
    sudden_min_delta: dict[str, float] = Field(
        default_factory=lambda: {
            "temperature_c": 2.0,
            "humidity_pct": 6.0,
            "pressure_hpa": 2.0,
            "air_quality_index": 15.0,
            "light_pct": 25.0,
            "rain_pct": 25.0,
        }
    )
    min_absolute_floor: dict[str, float] = Field(
        default_factory=lambda: {
            "temperature_c": 0.6,
            "humidity_pct": 1.5,
            "pressure_hpa": 0.3,
            "air_quality_index": 4.0,
            "light_pct": 3.0,
            "rain_pct": 3.0,
        }
    )


# --------------------------------------------------------------------------
# Prediction configuration
# --------------------------------------------------------------------------
class PredictionConfig(BaseModel):
    horizons_minutes: list[int] = Field(default_factory=lambda: [15, 30, 60])
    primary_horizon_minutes: int = 30
    min_samples_linear: int = 8
    min_samples_holt: int = 10
    max_samples: int = 240
    max_confidence: float = 0.92
    #: Confidence decay per hour of extrapolation beyond the observation window.
    horizon_decay_per_hour: float = 0.18
    rain_probability_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "humidity": 0.45,
            "pressure_drop": 0.35,
            "current_wetness": 0.5,
            "humidity_rise": 0.25,
        }
    )


# --------------------------------------------------------------------------
# Alert configuration
# --------------------------------------------------------------------------
class AlertRuleConfig(BaseModel):
    cooldown_minutes: int = 15
    device_offline_grace_seconds: int = 30
    worsening_streak_minutes: int = 45


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- application ------------------------------------------------------
    app_name: str = "Environmental Intelligence Platform"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = False

    # --- networking -------------------------------------------------------
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    #: Comma separated list of allowed browser origins.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    #: Extra origin regexes (useful for LAN IPs during a demo).
    cors_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?$"

    # --- security ---------------------------------------------------------
    api_key: str = "change-me-device-key"
    api_key_header: str = "X-API-Key"
    #: Optional key for administrative endpoints; falls back to API_KEY.
    admin_api_key: str | None = None
    require_auth_for_reads: bool = False
    chat_rate_limit_per_minute: int = 20
    ingest_rate_limit_per_minute: int = 600

    # --- storage ----------------------------------------------------------
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'environmental.db').as_posix()}"
    retention_days: int = 365

    # --- device -----------------------------------------------------------
    device_id: str = "arduino-r4-wifi-01"
    device_display_name: str = "Arduino UNO R4 WiFi - Environmental Node"
    expected_transmission_interval_seconds: int = 15
    device_offline_after_seconds: int = 60
    #: Reject payloads whose timestamp drifts more than this from server time.
    max_timestamp_skew_seconds: int = 900
    #: Ignore identical duplicate payloads inside this window.
    duplicate_window_seconds: int = 3
    stale_reading_seconds: int = 90

    # --- calibration / derived metrics -----------------------------------
    #: MQ-135 clean-air ADC baseline used to normalise the relative index.
    air_quality_clean_baseline: float = 180.0
    #: MQ-135 ADC value treated as the maximum of the relative index scale.
    air_quality_max_reference: float = 850.0
    #: Rain sensor ADC values mapping to 0 % and 100 % wetness.
    rain_dry_adc: float = 950.0
    rain_wet_adc: float = 250.0
    #: LDR ADC values mapped to 0 % and 100 % illumination index.
    light_dark_adc: float = 40.0
    light_bright_adc: float = 900.0

    # --- simulation -------------------------------------------------------
    simulation_mode: bool = False
    simulation_interval_seconds: float = 5.0
    simulation_scenario: str = "mixed_weather"
    simulation_seed: int | None = 20260915
    #: The built-in demo simulator feeds the same device as real hardware by
    #: default so the dashboard is live out of the box; readings are still
    #: tagged ``source="simulation"`` and shown as simulated in the UI.
    simulation_device_id: str = "arduino-r4-wifi-01"
    simulation_speed: float = 1.0

    # --- ollama -----------------------------------------------------------
    ollama_enabled: bool = True
    ollama_host: str = "http://localhost:11434"
    #: Leave empty to auto-detect from the models installed locally.
    ollama_model: str = ""
    #: Preference order used when ``OLLAMA_MODEL`` is not set. Non-thinking models
    #: come first because they answer a grounded data question in seconds, while a
    #: thinking model may spend its whole token budget reasoning before it speaks.
    ollama_fallback_models: str = "gemma3:4b,qwen3:4b,qwen3:8b,llama3.2:3b,mistral:7b"
    #: Some builds of "thinking" models (Qwen3 and friends) leak their chain of
    #: thought into the answer when thinking is switched off, so the direct-answer
    #: flag stays opt-in. Ollama >= 0.9 already reports reasoning separately, and
    #: the client retries without the flag if a model rejects it.
    ollama_disable_thinking: bool = False
    #: Safety valve against runaway generation. Reasoning tokens count towards
    #: this budget, so it must stay comfortably above what a thinking model
    #: needs - otherwise the model spends the whole budget thinking and returns
    #: an empty answer.
    ollama_num_predict: int = 2048
    ollama_timeout_seconds: float = 180.0
    ollama_temperature: float = 0.2
    ollama_num_ctx: int = 8192
    ollama_keep_alive: str = "10m"
    ollama_health_cache_seconds: int = 30
    chat_max_history_messages: int = 8
    chat_max_context_chars: int = 14000

    # --- analytics --------------------------------------------------------
    analytics_default_hours: int = 6
    prediction_snapshot_interval_minutes: int = 5
    background_workers_enabled: bool = True

    # --- nested model config ---------------------------------------------
    anomaly: AnomalyConfig = Field(default_factory=AnomalyConfig)
    prediction: PredictionConfig = Field(default_factory=PredictionConfig)
    alerts: AlertRuleConfig = Field(default_factory=AlertRuleConfig)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def ollama_fallback_list(self) -> list[str]:
        return [m.strip() for m in self.ollama_fallback_models.split(",") if m.strip()]

    @property
    def device_online_threshold_seconds(self) -> int:
        """A device is offline once it misses several consecutive intervals."""
        configured = self.device_offline_after_seconds
        interval_based = int(self.expected_transmission_interval_seconds * 3)
        return max(configured, interval_based)

    def resolve_database_url(self) -> str:
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _risk_config_path() -> Path | None:
    import os

    raw = os.getenv("RISK_CONFIG_FILE", "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_DIR / raw
    if path.exists():
        return path
    return (PROJECT_ROOT / raw) if (PROJECT_ROOT / raw).exists() else None


@lru_cache
def get_risk_config() -> RiskConfig:
    """Return the active risk model, optionally replaced by a JSON file."""
    path = _risk_config_path()
    if path is not None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return RiskConfig.model_validate(payload)
        except Exception:  # pragma: no cover - misconfiguration must not kill the app
            from .logging import get_logger

            get_logger(__name__).error(
                "risk_config_invalid", extra={"path": str(path)}
            )
    return RiskConfig()


def reload_settings() -> None:
    """Clear cached configuration (used by tests and the dev scripts)."""
    get_settings.cache_clear()
    get_risk_config.cache_clear()
