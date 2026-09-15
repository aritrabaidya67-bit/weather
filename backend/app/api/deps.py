"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.database import session_dependency
from ..core.security import optional_api_key, require_api_key
from . import services as service_registry


def get_session() -> Iterator[Session]:
    """One database session per request."""
    yield from session_dependency()


SessionDep = Annotated[Session, Depends(get_session)]
ApiKeyDep = Annotated[str, Depends(require_api_key)]
ReadAccessDep = Annotated[bool, Depends(optional_api_key)]
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
