"""Persistence for chatbot transcripts."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import ChatMessage


class ChatRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, message: ChatMessage) -> ChatMessage:
        self.session.add(message)
        self.session.flush()
        return message

    def history(self, session_id: str, limit: int = 50) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        rows = list(self.session.execute(stmt).scalars().all())
        rows.reverse()
        return rows

    def recent(self, limit: int = 100) -> list[ChatMessage]:
        stmt = select(ChatMessage).order_by(ChatMessage.created_at.desc()).limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    def clear_session(self, session_id: str) -> int:
        result = self.session.execute(
            delete(ChatMessage).where(ChatMessage.session_id == session_id)
        )
        return int(result.rowcount or 0)

    def count(self, session_id: str | None = None) -> int:
        stmt = select(func.count(ChatMessage.id))
        if session_id:
            stmt = stmt.where(ChatMessage.session_id == session_id)
        return int(self.session.execute(stmt).scalar_one() or 0)
