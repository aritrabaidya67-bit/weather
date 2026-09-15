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


#: Values that ship in the repository as templates or were used during
#: development. None of them may ever authenticate a real device, so they are
#: rejected rather than trusted. Checked case-insensitively by substring so
#: "dev-local-key-change-me" and "PLEASE-change-me" are both caught.
WEAK_KEY_MARKERS: tuple[str, ...] = (
    "change-me",
    "changeme",
    "replace_with",
    "replace-with",
    "your_key",
    "your-key",
    "your_api_key",
    "example",
    "placeholder",
    "test-key",
    "secret123",
    "password",
    "dev-local-key",
    # Credentials that were once committed in this repository's tests/docs. They
    # are public by definition, so they must never authenticate a real device or
    # admin console even if someone copies them into `.env`.
    "test-api-key",
    "test-admin-key",
    "admin-secret-key",
    "smoke-api-key",
    "smoke-admin-key",
)

#: Shortest device key the platform will accept. Below this, offline guessing
#: against a LAN-exposed endpoint stops being a theoretical concern.
MIN_API_KEY_LENGTH = 16


def _device_keys(settings: Settings) -> list[str]:
    """Keys accepted for DEVICE operations (ingestion, risk-state)."""
    return [settings.api_key] if settings.api_key else []


def _admin_keys(settings: Settings) -> list[str]:
    """Keys accepted for ADMIN operations (destructive/maintenance endpoints).

    The admin key is its own credential: it must never be accepted as a device
    key (an admin console has no reason to POST sensor data), and the device key
    must never be accepted for admin operations (least privilege - a leaked
    node credential must not grant the right to purge the database).
    """
    if settings.admin_api_key:
        return [settings.admin_api_key]
    return []


def _expected_keys(settings: Settings) -> list[str]:
    """Union of all valid keys - only for strength checks, never for authz."""
    return [key for key in (*_device_keys(settings), *_admin_keys(settings)) if key]


def key_strength_problem(api_key: str | None) -> str | None:
    """Return a human-readable reason the device key is unacceptable, or None.

    This is a *reject* list, not a strength meter: it only rules out values that
    are published in this repository, obviously templated, or too short to be a
    real secret. Knowing exactly why a key was refused is the difference between
    a five-second fix and an afternoon of debugging.
    """
    if not api_key:
        return "API_KEY is empty."
    lowered = api_key.strip().lower()
    for marker in WEAK_KEY_MARKERS:
        if marker in lowered:
            return (
                f"API_KEY looks like the template/development value ('{marker}' appears in it). "
                "Generate a real one and put the same value in the firmware."
            )
    if len(api_key.strip()) < MIN_API_KEY_LENGTH:
        return (
            f"API_KEY is only {len(api_key.strip())} characters; at least "
            f"{MIN_API_KEY_LENGTH} are required."
        )
    if len(set(api_key.strip())) < 6:
        return "API_KEY has too little variety to be a real secret."
    return None


def keys_are_configured(settings: Settings | None = None) -> bool:
    """True only when a *usable* device key is configured.

    A template or development key counts as "not configured", so the device
    endpoints answer 503 with an explicit reason instead of accepting traffic
    that any reader of this repository could forge.
    """
    settings = settings or get_settings()
    register_secret(settings.api_key)
    register_secret(settings.admin_api_key)
    return key_strength_problem(settings.api_key) is None


def validate_api_key(
    candidate: str | None,
    settings: Settings | None = None,
    *,
    admin: bool = False,
) -> bool:
    """Constant-time comparison against the keys accepted for the given scope.

    ``admin=False`` accepts only the device key; ``admin=True`` accepts only the
    admin key. The two credential sets are deliberately disjoint so that a
    device credential can never exercise a privileged endpoint. An empty
    candidate is rejected before any comparison so a header cannot "match" an
    unset admin key.
    """
    settings = settings or get_settings()
    if not candidate:
        return False
    expected = _admin_keys(settings) if admin else _device_keys(settings)
    return any(secrets.compare_digest(candidate, key) for key in expected)


def validate_chat_owner(candidate: str | None, settings: Settings | None = None) -> bool:
    """True when the caller may read/clear chat sessions.

    Chat transcripts may contain questions about the operator's environment, so
    they are only for the holder of the *device* key (or the admin key when one
    is configured for a separate console). Unauthenticated callers get 401; a
    guessed or stolen session UUID alone grants nothing.
    """
    settings = settings or get_settings()
    if not candidate:
        return False
    candidates = [*_device_keys(settings), *_admin_keys(settings)]
    return any(secrets.compare_digest(candidate, key) for key in candidates)


def _reject_weak_device_key(request: Request, settings: Settings) -> None:
    problem = key_strength_problem(settings.api_key)
    if problem:
        logger.warning("api_key_not_configured", reason=problem, path=request.url.path)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The server's device API key is not configured for production use. "
                f"{problem} See the API key section of backend/README.md."
            ),
        )


def _log_rejection(request: Request, x_api_key: str | None, scope: str) -> None:
    logger.warning(
        "api_key_rejected",
        scope=scope,
        path=request.url.path,
        client=request.client.host if request.client else None,
        key_supplied=bool(x_api_key),
    )


async def require_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    """Device-scope authentication: ingest and the firmware risk-state poll."""
    settings = get_settings()
    _reject_weak_device_key(request, settings)
    if not validate_api_key(x_api_key, settings):
        _log_rejection(request, x_api_key, "device")
        raise ApiKeyError("Invalid or missing API key.")
    return x_api_key or ""


async def require_admin_key(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    """Admin-scope authorization for destructive/maintenance operations.

    The device key is deliberately NOT accepted here. When no admin key is
    configured the endpoint fails closed with 503 and names the remedy, so a
    missing variable can never silently downgrade an admin surface to "any
    device may purge the database".
    """
    settings = get_settings()
    if not settings.admin_api_key:
        logger.warning("admin_key_not_configured", path=request.url.path)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "This endpoint requires ADMIN_API_KEY in backend/.env, which is not "
                "configured. Destructive operations refuse to run with the device key "
                "alone. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(32))"'
            ),
        )
    if key_strength_problem(settings.admin_api_key):
        logger.warning("admin_key_not_configured", path=request.url.path, reason="weak admin key")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_KEY is set but fails the strength policy. Generate a real one.",
        )
    if not validate_api_key(x_api_key, settings, admin=True):
        _log_rejection(request, x_api_key, "admin")
        raise ApiKeyError("Administrator privileges are required for this operation.")
    return x_api_key or ""


async def optional_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> bool:
    """Read access when REQUIRE_AUTH_FOR_READS locks the dashboard down."""
    settings = get_settings()
    if not settings.require_auth_for_reads:
        return True
    if not validate_chat_owner(x_api_key, settings):
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
_chat_status_limiter: RateLimiter | None = None


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


def get_chat_status_limiter() -> RateLimiter:
    """Lighter limiter for Ollama probes and other moderately costly reads.

    ``/chat/status`` refreshes a live HTTP probe against Ollama, and
    ``/chat/context`` re-renders the whole data snapshot. Both are cheap once per
    browser but trivially abusable in a loop, so they get a bounded budget
    instead of being either unlimited or starved by the main chat limiter.
    """
    global _chat_status_limiter
    if _chat_status_limiter is None:
        _chat_status_limiter = RateLimiter(60)
    return _chat_status_limiter
