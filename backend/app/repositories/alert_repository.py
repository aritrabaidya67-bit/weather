"""Persistence queries for alerts."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Alert
from ..utils.timeutils import ensure_utc, utcnow


class AlertRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, alert: Alert) -> Alert:
        self.session.add(alert)
        self.session.flush()
        return alert

    def get(self, alert_id: int) -> Alert | None:
        return self.session.get(Alert, alert_id)

    def find_recent_by_fingerprint(
        self, fingerprint: str, within_seconds: int
    ) -> Alert | None:
        cutoff = utcnow() - timedelta(seconds=within_seconds)
        stmt = (
            select(Alert)
            .where(Alert.fingerprint == fingerprint, Alert.last_seen_at >= cutoff)
            .order_by(Alert.last_seen_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalars().first()

    def list(
        self,
        device_id: str | None = None,
        *,
        active_only: bool = False,
        severity: str | None = None,
        category: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Alert]:
        stmt = select(Alert)
        if device_id:
            stmt = stmt.where(Alert.device_id == device_id)
        if active_only:
            stmt = stmt.where(Alert.is_active.is_(True))
        if severity:
            stmt = stmt.where(Alert.severity == severity)
        if category:
            stmt = stmt.where(Alert.category == category)
        if since:
            stmt = stmt.where(Alert.last_seen_at >= ensure_utc(since))
        stmt = stmt.order_by(Alert.is_active.desc(), Alert.last_seen_at.desc()).limit(limit).offset(offset)
        return list(self.session.execute(stmt).scalars().all())

    def count(
        self,
        device_id: str | None = None,
        *,
        active_only: bool = False,
        since: datetime | None = None,
    ) -> int:
        stmt = select(func.count(Alert.id))
        if device_id:
            stmt = stmt.where(Alert.device_id == device_id)
        if active_only:
            stmt = stmt.where(Alert.is_active.is_(True))
        if since:
            stmt = stmt.where(Alert.last_seen_at >= ensure_utc(since))
        return int(self.session.execute(stmt).scalar_one() or 0)

    def severity_counts(self, device_id: str | None = None, active_only: bool = False) -> dict[str, int]:
        stmt = select(Alert.severity, func.count(Alert.id)).group_by(Alert.severity)
        if device_id:
            stmt = stmt.where(Alert.device_id == device_id)
        if active_only:
            stmt = stmt.where(Alert.is_active.is_(True))
        return {row[0]: int(row[1]) for row in self.session.execute(stmt).all()}

    def category_counts(self, device_id: str | None = None) -> dict[str, int]:
        stmt = select(Alert.category, func.count(Alert.id)).group_by(Alert.category)
        if device_id:
            stmt = stmt.where(Alert.device_id == device_id)
        return {row[0]: int(row[1]) for row in self.session.execute(stmt).all()}

    def active_by_category(self, device_id: str, category: str) -> list[Alert]:
        stmt = select(Alert).where(
            Alert.device_id == device_id,
            Alert.category == category,
            Alert.is_active.is_(True),
        )
        return list(self.session.execute(stmt).scalars().all())

    def resolve_missing(self, device_id: str, seen_categories: set[str]) -> int:
        """Resolve active alerts whose condition no longer holds."""
        stmt = select(Alert).where(Alert.device_id == device_id, Alert.is_active.is_(True))
        rows = list(self.session.execute(stmt).scalars().all())
        now = utcnow()
        resolved = 0
        for alert in rows:
            if alert.category in seen_categories:
                continue
            alert.is_active = False
            alert.resolved_at = now
            resolved += 1
        if resolved:
            self.session.flush()
        return resolved
