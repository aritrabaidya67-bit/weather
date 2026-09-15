"""Persisted chatbot transcript with a snapshot of the data context used."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base, UTCDateTime
from .reading import utcnow


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    grounding: Mapped[str | None] = mapped_column(String(24), nullable=True)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "model": self.model,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "grounding": self.grounding,
        }
