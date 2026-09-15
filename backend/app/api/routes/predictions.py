"""Forecasting endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, status

from ...core.security import client_identity, get_ingest_limiter
from ...schemas import PredictionAccuracyResponse, PredictionHistoryResponse, PredictionResponse
from ..deps import DeviceDep, ReadAccessDep, SessionDep
from ..services import PredictionService

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get(
    "",
    response_model=PredictionResponse,
    summary="Statistical forecast including risk and rain probability",
    description=(
        "Uses a linear + Holt blend for continuous metrics, a solar-cycle model for illumination "
        "and a heuristic probability model for rain. Every metric reports the method, the sample "
        "count, the fit quality, the confidence and the features used. When history is too short "
        "the response says so instead of inventing a forecast."
    ),
)
def forecast(
    request: Request,
    session: SessionDep,
    _: ReadAccessDep,
    device_id: DeviceDep,
    horizons: Annotated[str | None, Query(description="Comma separated minutes, e.g. 15,30,60")] = None,
    persist: Annotated[bool, Query(description="Store a snapshot for later accuracy scoring")] = False,
) -> Any:
    parsed: list[int] | None = None
    if horizons:
        try:
            parsed = [int(item.strip()) for item in horizons.split(",") if item.strip()]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="horizons must be a comma separated list of minutes (1-240).",
            ) from None
    if persist:
        # Persisting a snapshot writes a row; a loop against this flag must not
        # be able to fill the database unauthenticated, so it borrows the
        # ingestion rate-limit budget (which is far above any dashboard's needs).
        limiter = get_ingest_limiter()
        allowed, retry_after = limiter.check(f"forecast-persist:{client_identity(request)}")
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many forecast snapshot requests. Please wait a moment.",
                headers={"Retry-After": str(int(retry_after) + 1)},
            )
    result = PredictionService(session).forecast(device_id, horizons=parsed, persist=persist)
    if persist:
        # Forecast snapshots are only written when explicitly requested; commit
        # them here because read endpoints do not commit implicitly.
        session.commit()
    return result


@router.get("/accuracy", response_model=PredictionAccuracyResponse, summary="How good past forecasts actually were")
def accuracy(session: SessionDep, _: ReadAccessDep, device_id: DeviceDep) -> Any:
    return PredictionService(session).accuracy(device_id)


@router.get("/history", response_model=PredictionHistoryResponse, summary="Stored forecast snapshots")
def history(
    session: SessionDep,
    _: ReadAccessDep,
    device_id: DeviceDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> Any:
    return PredictionService(session).history(device_id, limit=limit)
