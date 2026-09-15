"""Device / hardware endpoints.

``/device/{device_id}/risk-state`` is the compact endpoint the firmware polls to
drive its five LEDs and its buzzer, so the physical indicators always mirror the
backend's assessment (including when the Arduino cannot compute risk locally).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from ...core.config import get_settings
from ...schemas import DeviceListResponse, DeviceOut, RiskStateResponse
from ...utils.timeutils import ensure_utc, utcnow
from ..deps import ApiKeyDep, DeviceDep, ReadAccessDep, SessionDep
from ..services import AlertService, AnalyticsService, DeviceService, RiskService, runner

router = APIRouter(prefix="/device", tags=["device"])


@router.get("", response_model=DeviceOut, summary="Primary device status and sensor health")
def device(session: SessionDep, _: ReadAccessDep, device_id: DeviceDep) -> Any:
    return DeviceService(session).status(device_id)


@router.get("/list", response_model=DeviceListResponse, summary="All devices seen by the backend")
def device_list(session: SessionDep, _: ReadAccessDep) -> Any:
    return DeviceService(session).list_devices()


@router.get("/{device_id}", response_model=DeviceOut, summary="Status of one device")
def device_by_id(device_id: str, session: SessionDep, _: ReadAccessDep) -> Any:
    return DeviceService(session).status(device_id)


@router.get(
    "/{device_id}/risk-state",
    response_model=RiskStateResponse,
    summary="Compact risk state for the Arduino LEDs and buzzer",
)
def risk_state(
    device_id: str,
    session: SessionDep,
    _: ApiKeyDep,
) -> Any:
    settings = get_settings()
    service = AnalyticsService(session)
    latest = service.readings.latest(device_id)
    if latest is None:
        level = 1
        spec = RiskService().level_by_number(level)
        return {
            "device_id": device_id,
            "risk_score": 0.0,
            "risk_level": level,
            "risk_label": spec.label,
            "risk_code": spec.code,
            "color": spec.color,
            "led_index": level,
            "buzzer_pattern": "silent",
            "reasons": ["No sensor data received yet; the node reports its local fallback state."],
            "recommended_actions": [],
            "stale": True,
            "age_seconds": None,
            "data_source": "none",
            "evaluated_at": None,
            "alerts_active": 0,
            "server_time": utcnow().isoformat(),
        }
    risk_service = RiskService()
    metrics = service._metrics_from_row(latest)  # noqa: SLF001
    assessment = risk_service.assess(
        service._risk_inputs(  # noqa: SLF001
            latest, metrics, list(latest.anomalies or []), service.trend_context(device_id)
        )
    )
    received = ensure_utc(latest.received_at) or utcnow()
    age = (utcnow() - received).total_seconds()
    return risk_service.to_state_payload(
        assessment,
        device_id=device_id,
        stale=age > settings.stale_reading_seconds,
        age_seconds=round(age, 1),
        data_source=latest.source,
        alerts_active=AlertService(session).repository.count(device_id, active_only=True),
    )


@router.get("/simulation/status", summary="Built-in simulation mode status")
def simulation_status(_: ReadAccessDep) -> dict[str, Any]:
    return runner.status()


@router.post("/simulation/start", summary="Start the built-in simulator (demo mode)")
def simulation_start() -> dict[str, Any]:
    import asyncio

    if runner.running:
        return {"success": True, "message": "Simulator already running.", "status": runner.status()}
    try:
        asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover - only outside an event loop
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No running event loop available.",
        ) from None
    asyncio.create_task(runner.start())
    return {"success": True, "message": "Simulator starting.", "status": runner.status()}


@router.post("/simulation/stop", summary="Stop the built-in simulator")
def simulation_stop() -> dict[str, Any]:
    import asyncio

    if not runner.running:
        return {"success": True, "message": "Simulator is not running.", "status": runner.status()}
    asyncio.create_task(runner.stop())
    return {"success": True, "message": "Simulator stopping.", "status": runner.status()}


@router.delete("/{device_id}/readings", summary="Delete stored readings for a device (admin)")
def purge(device_id: str, session: SessionDep, _: ApiKeyDep) -> dict[str, Any]:
    from ...repositories import ReadingRepository

    repository = ReadingRepository(session)
    removed = 0
    while True:
        rows = repository.recent(device_id, limit=500)
        if not rows:
            break
        for row in rows:
            session.delete(row)
        removed += len(rows)
        session.flush()
        if len(rows) < 500:
            break
    session.commit()
    return {"success": True, "device_id": device_id, "deleted_readings": removed}
