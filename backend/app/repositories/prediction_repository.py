"""Persistence queries for prediction snapshots and their later evaluation."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import PredictionRecord
from ..utils.timeutils import ensure_utc, utcnow


class PredictionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_many(self, records: list[PredictionRecord]) -> int:
        if not records:
            return 0
        self.session.add_all(records)
        self.session.flush()
        return len(records)

    def list(
        self, device_id: str | None = None, *, limit: int = 100, metric: str | None = None
    ) -> list[PredictionRecord]:
        stmt = select(PredictionRecord)
        if device_id:
            stmt = stmt.where(PredictionRecord.device_id == device_id)
        if metric:
            stmt = stmt.where(PredictionRecord.metric == metric)
        stmt = stmt.order_by(PredictionRecord.created_at.desc()).limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    def pending_evaluation(self, limit: int = 500) -> list[PredictionRecord]:
        stmt = (
            select(PredictionRecord)
            .where(
                PredictionRecord.evaluated.is_(False),
                PredictionRecord.target_at <= utcnow(),
            )
            .order_by(PredictionRecord.target_at.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def evaluate(self, record: PredictionRecord, actual_value: float | None) -> None:
        record.actual_value = actual_value
        record.evaluated = True
        if actual_value is not None and record.predicted_value is not None:
            record.absolute_error = abs(actual_value - record.predicted_value)
        self.session.flush()

    def accuracy_summary(self, device_id: str | None = None) -> dict[str, dict[str, float | None]]:
        stmt = (
            select(
                PredictionRecord.metric,
                PredictionRecord.horizon_minutes,
                func.count(PredictionRecord.id),
                func.avg(PredictionRecord.absolute_error),
            )
            .where(PredictionRecord.evaluated.is_(True))
            .group_by(PredictionRecord.metric, PredictionRecord.horizon_minutes)
        )
        if device_id:
            stmt = stmt.where(PredictionRecord.device_id == device_id)
        out: dict[str, dict[str, float | None]] = {}
        for metric, horizon, count, mean_error in self.session.execute(stmt).all():
            bucket = out.setdefault(metric, {})
            bucket[f"horizon_{horizon}m_samples"] = float(count)
            bucket[f"horizon_{horizon}m_mae"] = round(float(mean_error), 3) if mean_error is not None else None
        return out

    def count(self, device_id: str | None = None, since: datetime | None = None) -> int:
        stmt = select(func.count(PredictionRecord.id))
        if device_id:
            stmt = stmt.where(PredictionRecord.device_id == device_id)
        if since:
            stmt = stmt.where(PredictionRecord.created_at >= ensure_utc(since))
        return int(self.session.execute(stmt).scalar_one() or 0)

    def prune(self, keep: int = 5000) -> int:
        subquery = (
            select(PredictionRecord.id)
            .order_by(PredictionRecord.created_at.desc())
            .limit(keep)
            .subquery()
        )
        ids = select(subquery.c.id)
        result = self.session.execute(
            PredictionRecord.__table__.delete().where(PredictionRecord.id.not_in(ids))
        )
        return int(result.rowcount or 0)
