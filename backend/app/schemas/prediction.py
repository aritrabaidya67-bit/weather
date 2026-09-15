"""Forecasting schemas.

Predictions are always returned with their method, confidence and reasoning so
the UI (and the chatbot) can present them as estimates rather than facts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Direction = Literal["rising", "falling", "stable", "unknown"]
Method = Literal[
    "linear_trend",
    "holt_linear",
    "blend",
    "diurnal_model",
    "heuristic_probability",
    "persistence",
    "insufficient_data",
]


class MetricPrediction(BaseModel):
    metric: str
    label: str
    unit: str
    current_value: float | None = None
    predicted_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    delta: float | None = None
    direction: Direction = "unknown"
    horizon_minutes: int
    confidence: float = 0.0
    confidence_label: Literal["low", "medium", "high"] = "low"
    method: Method = "insufficient_data"
    samples_used: int = 0
    r_squared: float | None = None
    expected_status: str | None = None
    current_status: str | None = None
    reasoning: str = ""
    features: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RiskForecast(BaseModel):
    horizon_minutes: int
    current_score: float | None = None
    predicted_score: float | None = None
    current_level: int | None = None
    predicted_level: int | None = None
    predicted_label: str | None = None
    direction: Direction = "unknown"
    confidence: float = 0.0
    drivers: list[str] = Field(default_factory=list)


class RainForecast(BaseModel):
    horizon_minutes: int
    probability: float = 0.0
    confidence: float = 0.0
    method: Method = "heuristic_probability"
    reasoning: str = ""
    currently_raining: bool = False


class PredictionResponse(BaseModel):
    device_id: str
    generated_at: str
    primary_horizon_minutes: int
    horizons_minutes: list[int] = Field(default_factory=list)
    data_sufficient: bool = True
    samples_used: int = 0
    observation_window_minutes: float = 0.0
    metrics: dict[str, MetricPrediction] = Field(default_factory=dict)
    #: horizon (minutes as string) -> metric key -> prediction. The ``risk_score``
    #: entry holds a :class:`RiskForecast` rather than a metric prediction, hence Any.
    all_horizons: dict[str, dict[str, Any]] = Field(default_factory=dict)
    risk: RiskForecast | None = None
    rain: RainForecast | None = None
    summary: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "Forecasts are statistical estimates derived from recent sensor history. "
        "They are not guaranteed outcomes."
    )


class PredictionAccuracyResponse(BaseModel):
    device_id: str
    evaluated_count: int = 0
    horizons: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class PredictionHistoryResponse(BaseModel):
    device_id: str
    count: int = 0
    records: list[dict[str, Any]] = Field(default_factory=list)
