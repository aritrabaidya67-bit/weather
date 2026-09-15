"""API-key authentication, rate limiting and secret hygiene."""

from __future__ import annotations

import secrets
import time
from collections import deque
from threading import Lock
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from .config import Settings, get_settings
from .logging import get_logger, register_secret

logger = get_logger("app.security")


class ApiKeyError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "X-API-Key"},
        )


def _expected_keys(settings: Settings) -> list[str]:
    keys = [settings.api_key]
    if settings.admin_api_key:
        keys.append(settings.admin_api_key)
    return [key for key in keys if key]


def keys_are_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    register_secret(settings.api_key)
    register_secret(settings.admin_api_key)
    return bool(settings.api_key) and settings.api_key != "change-me-device-key"


def validate_api_key(candidate: str | None, settings: Settings | None = None) -> bool:
    """Constant-time comparison against every accepted key."""
    settings = settings or get_settings()
    if not candidate:
        return False
    return any(secrets.compare_digest(candidate, key) for key in _expected_keys(settings))


async def require_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    """Dependency protecting device-facing and mutating endpoints."""
    settings = get_settings()
    if not keys_are_configured(settings):
        logger.warning(
            "api_key_not_configured",
            hint="set API_KEY in backend/.env before connecting real hardware",
            path=request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server API key is not configured. Set API_KEY in backend/.env.",
        )
    if not validate_api_key(x_api_key, settings):
        logger.warning(
            "api_key_rejected",
            path=request.url.path,
            client=request.client.host if request.client else None,
            key_supplied=bool(x_api_key),
        )
        raise ApiKeyError("Invalid or missing API key.")
    return x_api_key or ""


async def optional_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> bool:
    """For read endpoints that can optionally be locked down."""
    settings = get_settings()
    if not settings.require_auth_for_reads:
        return True
    if not validate_api_key(x_api_key, settings):
        raise ApiKeyError("Read access requires a valid API key.")
    return True


class RateLimiter:
    """Small in-process sliding-window limiter.

    Deliberately dependency free: one process, one API, LAN scale traffic. It is
    not a security boundary for the ingestion endpoint, it only protects the
    cheap-but-not-free chatbot and ingestion paths from runaway clients.
    """

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, key: str) -> tuple[bool, float]:
        """Return ``(allowed, retry_after_seconds)``."""
        now = time.monotonic()
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            cutoff = now - self.window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                retry_after = max(0.0, self.window_seconds - (now - bucket[0]))
                return False, round(retry_after, 2)
            bucket.append(now)
            return True, 0.0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_identity(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


_chat_limiter: RateLimiter | None = None
_ingest_limiter: RateLimiter | None = None


def get_chat_limiter() -> RateLimiter:
    global _chat_limiter
    if _chat_limiter is None:
        _chat_limiter = RateLimiter(get_settings().chat_rate_limit_per_minute)
    return _chat_limiter


def get_ingest_limiter() -> RateLimiter:
    global _ingest_limiter
    if _ingest_limiter is None:
        _ingest_limiter = RateLimiter(get_settings().ingest_rate_limit_per_minute)
    return _ingest_limiter
