"""Alert centre endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from ...schemas import AlertListResponse, AlertRuleOut
from ..deps import DeviceIdQuery, HoursQuery, ReadAccessDep, SessionDep
from ..services import ALERT_RULES, AlertService

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/rules", response_model=list[AlertRuleOut], summary="Alert rule catalogue")
def rules(_: ReadAccessDep) -> Any:
    return [
        {
            "id": rule.id,
            "category": rule.category,
            "severity": rule.severity,
            "title": rule.title,
            "description": rule.description,
            "condition": rule.condition,
            "default_action": rule.default_action,
            "enabled": True,
        }
        for rule in ALERT_RULES
    ]


@router.get("", response_model=AlertListResponse, summary="List alerts")
def list_alerts(
    session: SessionDep,
    _: ReadAccessDep,
    device_id: DeviceIdQuery = None,
    active_only: bool = False,
    severity: Annotated[str | None, Query(pattern="^(info|warning|critical)$")] = None,
    category: str | None = None,
    hours: HoursQuery | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Any:
    return AlertService(session).list(
        device_id,
        active_only=active_only,
        severity=severity,
        category=category,
        hours=hours,
        limit=limit,
        offset=offset,
    )


@router.post("/{alert_id}/acknowledge", summary="Acknowledge an alert")
def acknowledge(alert_id: int, session: SessionDep, _: ReadAccessDep) -> dict[str, Any]:
    service = AlertService(session)
    result = service.acknowledge(alert_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found.")
    session.commit()
    return {"success": True, "alert": result}


@router.post("/{alert_id}/resolve", summary="Manually resolve an alert")
def resolve(alert_id: int, session: SessionDep, _: ReadAccessDep) -> dict[str, Any]:
    from ...utils.timeutils import utcnow

    service = AlertService(session)
    alert = service.repository.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found.")
    alert.is_active = False
    alert.resolved_at = utcnow()
    session.commit()
    return {"success": True, "alert": alert.as_dict()}
