"""Shared FastAPI dependencies and the centralized authorization policy.

Every route declares its access level through exactly one of these annotated
dependencies, so the policy lives in one auditable place rather than being
re-derived per endpoint:

* ``SessionDep``     - database session (no authorization)
* ``ReadAccessDep``  - public reads; optionally key-protected by REQUIRE_AUTH_FOR_READS
* ``ApiKeyDep``      - DEVICE scope: ingestion + the firmware risk-state poll
* ``AdminKeyDep``    - ADMIN scope: destructive/maintenance operations
* ``ChatOwnerDep``   - caller presented a valid device or admin key (chat data)

The device and admin credentials are disjoint: a device key can never reach an
admin endpoint and vice versa.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.database import session_dependency
from ..core.security import (
    ApiKeyError,
    optional_api_key,
    require_admin_key,
    require_api_key,
    validate_chat_owner,
)
from . import services as service_registry


def get_session() -> Iterator[Session]:
    """One database session per request."""
    yield from session_dependency()


SessionDep = Annotated[Session, Depends(get_session)]
#: DEVICE scope - writing sensor data, the firmware's LED/buzzer poll.
ApiKeyDep = Annotated[str, Depends(require_api_key)]
#: ADMIN scope - destructive and maintenance operations.
AdminKeyDep = Annotated[str, Depends(require_admin_key)]
#: Public dashboard reads; key-gated when REQUIRE_AUTH_FOR_READS=true.
ReadAccessDep = Annotated[bool, Depends(optional_api_key)]


def require_chat_ownership(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> bool:
    """Chat-data and mutation access policy (self-verifying).

    Covers every endpoint that reads or writes operator data without being a
    device write: chat history, chat context, alert acknowledge/resolve.

    * ``REQUIRE_AUTH_FOR_READS=false`` (LAN demo default): open, so the
      single-operator dashboard keeps working.
    * ``REQUIRE_AUTH_FOR_READS=true``: a valid device or admin key is required;
      knowing a session UUID alone is NOT authorization.

    This dependency verifies the key itself (it never relies on another
    dependency having run first) and fails closed with 401.
    """
    settings = get_settings()
    if not settings.require_auth_for_reads:
        return True
    if not validate_chat_owner(x_api_key, settings):
        raise ApiKeyError("This operation requires a valid API key.")
    return True


ChatOwnerDep = Annotated[bool, Depends(require_chat_ownership)]
HoursQuery = Annotated[
    float,
    Query(ge=0.05, le=24 * 31, description="Look-back window in hours (default 6)"),
]


def resolve_device_id(session: Session, device_id: str | None) -> str:
    """Fall back to the configured/primary device when none is given."""
    if device_id:
        return device_id
    return service_registry.DeviceService(session).primary_device_id()


# NOTE: FastAPI forbids defaults inside ``Annotated[...]``, so the default lives on
# the function signature instead.
DeviceIdQuery = Annotated[
    str | None,
    Query(description="Device identifier; defaults to the primary/configured device", max_length=64),
]


def device_dependency(session: SessionDep, device_id: DeviceIdQuery = None) -> str:
    return resolve_device_id(session, device_id)


DeviceDep = Annotated[str, Depends(device_dependency)]


def ensure_known_metric(metric: str) -> str:
    from ..core.sensors import REGISTRY

    if metric not in REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unknown metric '{metric}'. Valid metrics: {', '.join(sorted(REGISTRY))}"
            ),
        )
    return metric


def ensure_horizon(horizon: int) -> int:
    if horizon <= 0 or horizon > 240:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="horizon_minutes must be between 1 and 240.",
        )
    return horizon


def settings_summary() -> dict[str, object]:
    settings = get_settings()
    return {
        "environment": settings.environment,
        "device_id": settings.device_id,
        "expected_interval_seconds": settings.expected_transmission_interval_seconds,
        "ollama_enabled": settings.ollama_enabled,
        "ollama_model": settings.ollama_model or None,
    }
