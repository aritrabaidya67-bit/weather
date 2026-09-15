"""Alert table with de-duplication fingerprints and resolution state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base, UTCDateTime
from .reading import utcnow


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(120), index=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    sensor: Mapped[str | None] = mapped_column(String(40), nullable=True)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    triggered_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fingerprint": self.fingerprint,
            "device_id": self.device_id,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "sensor": self.sensor,
            "metric_value": self.metric_value,
            "risk_level": self.risk_level,
            "recommended_action": self.recommended_action,
            "context": self.context,
            "is_active": self.is_active,
            "occurrence_count": self.occurrence_count,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "acknowledged_at": (
                self.acknowledged_at.isoformat() if self.acknowledged_at else None
            ),
        }
