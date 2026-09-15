"""Persistence queries for the sensor time series."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..core.sensors import REGISTRY
from ..models import SensorReading
from ..utils.timeutils import ensure_utc, utcnow


class ReadingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------ writes
    def add(self, reading: SensorReading) -> SensorReading:
        self.session.add(reading)
        self.session.flush()
        return reading

    def delete_older_than(self, cutoff: datetime) -> int:
        result = self.session.execute(
            delete(SensorReading).where(SensorReading.received_at < cutoff)
        )
        return int(result.rowcount or 0)

    # ------------------------------------------------------------------- reads
    def latest(self, device_id: str | None = None) -> SensorReading | None:
        stmt = select(SensorReading).order_by(SensorReading.received_at.desc()).limit(1)
        if device_id:
            stmt = stmt.where(SensorReading.device_id == device_id)
        return self.session.execute(stmt).scalars().first()

    def latest_any_device(self) -> SensorReading | None:
        return self.latest(None)

    def recent(
        self,
        device_id: str | None = None,
        *,
        minutes: float | None = None,
        hours: float | None = None,
        limit: int | None = None,
        ascending: bool = True,
        newest_first_limit: bool = True,
    ) -> list[SensorReading]:
        """Return readings inside a rolling window, oldest first.

        ``limit`` always keeps the *newest* N readings inside the window, which is
        what analytics and prediction actually need.
        """
        stmt = select(SensorReading)
        if device_id:
            stmt = stmt.where(SensorReading.device_id == device_id)
        if minutes is not None:
            stmt = stmt.where(SensorReading.received_at >= utcnow() - timedelta(minutes=minutes))
        elif hours is not None:
            stmt = stmt.where(SensorReading.received_at >= utcnow() - timedelta(hours=hours))
        if limit is not None:
            stmt = stmt.order_by(SensorReading.received_at.desc()).limit(limit)
            rows = list(self.session.execute(stmt).scalars().all())
            rows.reverse()
            return rows
        stmt = stmt.order_by(SensorReading.received_at.asc())
        return list(self.session.execute(stmt).scalars().all())

    def between(
        self,
        device_id: str | None,
        start: datetime | None,
        end: datetime | None,
        limit: int | None = None,
    ) -> list[SensorReading]:
        stmt = select(SensorReading)
        if device_id:
            stmt = stmt.where(SensorReading.device_id == device_id)
        if start:
            stmt = stmt.where(SensorReading.received_at >= ensure_utc(start))
        if end:
            stmt = stmt.where(SensorReading.received_at <= ensure_utc(end))
        if limit:
            stmt = stmt.order_by(SensorReading.received_at.desc()).limit(limit)
            rows = list(self.session.execute(stmt).scalars().all())
            rows.reverse()
            return rows
        stmt = stmt.order_by(SensorReading.received_at.asc())
        return list(self.session.execute(stmt).scalars().all())

    def count(self, device_id: str | None = None, since: datetime | None = None) -> int:
        stmt = select(func.count(SensorReading.id))
        if device_id:
            stmt = stmt.where(SensorReading.device_id == device_id)
        if since:
            stmt = stmt.where(SensorReading.received_at >= ensure_utc(since))
        return int(self.session.execute(stmt).scalar_one() or 0)

    def device_ids(self) -> list[str]:
        rows = self.session.execute(
            select(SensorReading.device_id).distinct().order_by(SensorReading.device_id)
        ).all()
        return [row[0] for row in rows]

    def duplicate_exists(
        self, device_id: str, sequence: int | None, window_seconds: int
    ) -> SensorReading | None:
        if sequence is None:
            return None
        cutoff = utcnow() - timedelta(seconds=window_seconds)
        stmt = (
            select(SensorReading)
            .where(
                SensorReading.device_id == device_id,
                SensorReading.sequence == sequence,
                SensorReading.received_at >= cutoff,
            )
            .limit(1)
        )
        return self.session.execute(stmt).scalars().first()

    def last_risk_scores(self, device_id: str, limit: int = 60) -> list[tuple[datetime, float, int]]:
        stmt = (
            select(SensorReading.received_at, SensorReading.risk_score, SensorReading.risk_level)
            .where(
                SensorReading.device_id == device_id,
                SensorReading.risk_score.is_not(None),
            )
            .order_by(SensorReading.received_at.desc())
            .limit(limit)
        )
        rows = list(self.session.execute(stmt).all())
        rows.reverse()
        out: list[tuple[datetime, float, int]] = []
        for received_at, score, level in rows:
            if score is None:
                continue
            out.append((ensure_utc(received_at) or utcnow(), float(score), int(level or 1)))
        return out

    # -------------------------------------------------------------- aggregation
    def aggregate(
        self,
        device_id: str,
        start: datetime,
        end: datetime,
        bucket_seconds: int,
    ) -> list[dict[str, Any]]:
        """Average every metric inside fixed time buckets.

        Bucketing happens in Python so the same code path works on SQLite and
        PostgreSQL without dialect specific SQL (a PostgreSQL deployment would
        swap this for ``time_bucket``).
        """
        rows = self.between(device_id, start, end)
        if not rows:
            return []
        metric_keys = [key for key in REGISTRY if key != "rain_status"]
        buckets: dict[int, dict[str, Any]] = {}
        for row in rows:
            received_at = ensure_utc(row.received_at) or utcnow()
            epoch = received_at.timestamp()
            index = int(epoch // bucket_seconds)
            bucket = buckets.setdefault(
                index, {"count": 0, "timestamp": datetime.fromtimestamp(index * bucket_seconds, tz=received_at.tzinfo)}
            )
            bucket["count"] += 1
            for key in metric_keys:
                value = getattr(row, key, None)
                if value is None:
                    continue
                acc = bucket.setdefault(key, [0.0, 0])
                acc[0] += float(value)
                acc[1] += 1
            if row.risk_score is not None:
                acc = bucket.setdefault("risk_score", [0.0, 0])
                acc[0] += float(row.risk_score)
                acc[1] += 1
            if row.risk_level is not None:
                acc = bucket.setdefault("risk_level", [0.0, 0])
                acc[0] += float(row.risk_level)
                acc[1] += 1
        out: list[dict[str, Any]] = []
        for index in sorted(buckets):
            bucket = buckets[index]
            point: dict[str, Any] = {
                "bucket_start": bucket["timestamp"].isoformat(),
                "count": bucket["count"],
            }
            for key, value in bucket.items():
                if key in ("count", "timestamp"):
                    continue
                total, hits = value  # type: ignore[misc]
                point[key] = round(total / hits, 3) if hits else None
            out.append(point)
        return out

    def all_columns(self) -> Sequence[str]:
        return list(SensorReading.__table__.columns.keys())
