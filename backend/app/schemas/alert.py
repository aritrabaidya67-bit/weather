"""Alert schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AlertSeverity = Literal["info", "warning", "critical"]


class AlertOut(BaseModel):
    id: int | None = None
    fingerprint: str | None = None
    device_id: str | None = None
    category: str
    severity: AlertSeverity | str
    title: str
    message: str
    sensor: str | None = None
    metric_value: float | None = None
    risk_level: int | None = None
    recommended_action: str | None = None
    context: dict[str, Any] | None = None
    is_active: bool = True
    occurrence_count: int = 1
    triggered_at: str | None = None
    last_seen_at: str | None = None
    resolved_at: str | None = None
    acknowledged_at: str | None = None


class AlertListResponse(BaseModel):
    device_id: str
    active_count: int = 0
    total_count: int = 0
    severity_counts: dict[str, int] = Field(default_factory=dict)
    category_counts: dict[str, int] = Field(default_factory=dict)
    alerts: list[AlertOut] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AlertRuleOut(BaseModel):
    id: str
    category: str
    severity: str
    title: str
    description: str
    condition: str
    default_action: str
    enabled: bool = True
