"""Time parsing / formatting helpers (everything internally is UTC aware)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

UNIX_EPOCH_2020 = 1_577_836_800  # anything below this is treated as a broken clock


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_timestamp(raw: object) -> datetime | None:
    """Parse ISO-8601 strings, epoch seconds/milliseconds, or datetime objects."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return ensure_utc(raw)
    if isinstance(raw, (int, float)):
        value = float(raw)
        if value <= 0:
            return None
        if value > 1e11:  # milliseconds
            value /= 1000.0
        if value < UNIX_EPOCH_2020:
            return None
        return datetime.fromtimestamp(value, tz=UTC)
    text = str(raw).strip()
    if not text:
        return None
    if text.replace(".", "", 1).isdigit():
        return parse_timestamp(float(text))
    normalized = text.replace("Z", "+00:00")
    try:
        return ensure_utc(datetime.fromisoformat(normalized))
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                return ensure_utc(datetime.strptime(text, fmt))
            except ValueError:
                continue
    return None


def to_iso(value: datetime | None) -> str | None:
    value = ensure_utc(value)
    return value.isoformat() if value else None


def seconds_between(later: datetime, earlier: datetime) -> float:
    later, earlier = ensure_utc(later), ensure_utc(earlier)
    assert later and earlier
    return (later - earlier).total_seconds()


def minutes_between(later: datetime, earlier: datetime) -> float:
    return seconds_between(later, earlier) / 60.0


def humanize_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "never"
    seconds = abs(seconds)
    if seconds < 60:
        return f"{seconds:.0f} s"
    if seconds < 3600:
        return f"{seconds / 60:.1f} min"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} d"


def floor_to_minute(value: datetime) -> datetime:
    value = ensure_utc(value) or utcnow()
    return value.replace(second=0, microsecond=0)


def window_start(hours: float, now: datetime | None = None) -> datetime:
    now = ensure_utc(now) or utcnow()
    return now - timedelta(hours=hours)


def is_daytime(value: datetime, latitude: float = 22.57) -> bool:
    """Very rough local-day test used only for light-anomaly explanations."""
    local = (ensure_utc(value) or utcnow()).astimezone()
    return 6 <= local.hour < 19
