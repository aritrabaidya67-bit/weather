"""Explainable risk-model schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RiskContribution(BaseModel):
    """One factor's share of the total risk score.

    ``points`` is what the factor actually added to the 0-100 score, so the
    contributions always sum (up to rounding) to ``risk_score``. That is what
    makes the score auditable instead of arbitrary.
    """

    key: str
    label: str
    points: float
    max_points: float
    weight: float
    normalised: float = Field(description="0..1 position of the reading inside the factor scale")
    reading: float | None = None
    unit: str | None = None
    severity: Literal["good", "info", "watch", "warning", "critical", "unknown"] = "unknown"
    reason: str | None = None
    direction: Literal["increasing", "reducing", "neutral"] = "neutral"


class RiskAssessment(BaseModel):
    score: float
    level: int
    label: str
    code: str
    color: str
    description: str
    confidence: float = Field(default=1.0, description="0..1 confidence given data coverage")
    reasons: list[str] = Field(default_factory=list)
    reducing_factors: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    contributions: list[RiskContribution] = Field(default_factory=list)
    data_coverage: float = 1.0
    missing_metrics: list[str] = Field(default_factory=list)
    model_version: str = "1.0.0"
    evaluated_at: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class RiskTrendPoint(BaseModel):
    timestamp: str
    score: float
    level: int


class RiskAnalysisResponse(BaseModel):
    device_id: str
    assessment: RiskAssessment
    trend: list[RiskTrendPoint] = Field(default_factory=list)
    trend_direction: str = "unknown"
    trend_change: float | None = None
    top_contributors: list[RiskContribution] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    history_hours: float = 6.0
    notes: list[str] = Field(default_factory=list)


class RiskLevelInfo(BaseModel):
    level: int
    code: str
    label: str
    min_score: float
    max_score: float
    description: str
    color: str
    led_index: int
    buzzer_pattern: str


class RiskModelResponse(BaseModel):
    version: str
    description: str
    levels: list[RiskLevelInfo]
    factors: list[dict[str, Any]]
    weights: dict[str, float]
    notes: list[str] = Field(default_factory=list)
