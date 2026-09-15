"""Stored prediction snapshots.

Snapshots are kept so the platform can honestly report how good its own
forecasts were: ``actual_value`` is filled in once the forecast horizon has
elapsed, which turns "prediction" into something measurable instead of a
decorative number.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base, UTCDateTime
from .reading import utcnow


class PredictionRecord(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    target_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    horizon_minutes: Mapped[int] = mapped_column(Integer)
    metric: Mapped[str] = mapped_column(String(40), index=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    lower_bound: Mapped[float | None] = mapped_column(Float, nullable=True)
    upper_bound: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reasoning: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    actual_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    absolute_error: Mapped[float | None] = mapped_column(Float, nullable=True)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "target_at": self.target_at.isoformat() if self.target_at else None,
            "horizon_minutes": self.horizon_minutes,
            "metric": self.metric,
            "current_value": self.current_value,
            "predicted_value": self.predicted_value,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "confidence": self.confidence,
            "method": self.method,
            "reasoning": self.reasoning,
            "actual_value": self.actual_value,
            "evaluated": self.evaluated,
            "absolute_error": self.absolute_error,
        }
