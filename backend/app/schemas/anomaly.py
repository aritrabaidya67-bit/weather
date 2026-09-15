"""Anomaly-detection schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AnomalySeverity = Literal["low", "medium", "high"]
AnomalyKind = Literal["spike", "drop", "sudden_change", "stuck", "out_of_range"]


class Anomaly(BaseModel):
    sensor: str
    label: str
    unit: str
    severity: AnomalySeverity
    kind: AnomalyKind
    current_value: float
    expected_value: float | None = None
    expected_low: float | None = None
    expected_high: float | None = None
    deviation: float | None = None
    z_score: float | None = None
    baseline_samples: int = 0
    message: str
    explanation: str
    detected_at: str
    direction: Literal["above", "below"] = "above"
    contribution_to_risk: float = 0.0

    def as_context(self) -> dict[str, Any]:
        """Compact form embedded into the LLM context and stored on the reading."""
        return self.model_dump(mode="json", exclude_none=True)


class AnomalyListResponse(BaseModel):
    device_id: str
    count: int = 0
    window_hours: float = 6.0
    severity_counts: dict[str, int] = Field(default_factory=dict)
    sensor_counts: dict[str, int] = Field(default_factory=dict)
    anomalies: list[Anomaly] = Field(default_factory=list)
    baseline_ready: bool = True
    notes: list[str] = Field(default_factory=list)
