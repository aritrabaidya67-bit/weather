"""Risk analysis endpoints: current assessment, explainability, model description."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from ...schemas import RiskAnalysisResponse, RiskAssessment, RiskModelResponse
from ..deps import DeviceDep, HoursQuery, ReadAccessDep, SessionDep
from ..services import AlertService, AnalyticsService, RiskService

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/model", response_model=RiskModelResponse, summary="Risk model, weights and level definitions")
def model(_: ReadAccessDep) -> dict[str, Any]:
    return RiskService().model_description()


@router.get("/current", response_model=RiskAssessment, summary="Current explainable risk assessment")
def current(session: SessionDep, _: ReadAccessDep, device_id: DeviceDep) -> Any:
    service = AnalyticsService(session)
    latest = service.readings.latest(device_id)
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No sensor data yet, so no risk can be calculated. "
                "The risk engine scores the first payload the Arduino node sends."
            ),
        )
    metrics = service._metrics_from_row(latest)  # noqa: SLF001
    return RiskService().assess(
        service._risk_inputs(  # noqa: SLF001
            latest,
            metrics,
            list(latest.anomalies or []),
            service.trend_context(device_id, hours=3.0),
        )
    )


@router.get("/analysis", response_model=RiskAnalysisResponse, summary="Risk with trend, factors, anomalies and alerts")
def analysis(
    session: SessionDep,
    _: ReadAccessDep,
    device_id: DeviceDep,
    hours: HoursQuery = 6.0,
) -> Any:
    service = AnalyticsService(session)
    overview = service.overview(device_id, hours=hours)
    risk_trend_rows = service.readings.last_risk_scores(device_id, limit=120)
    trend = [
        {"timestamp": timestamp.isoformat(), "score": score, "level": level}
        for timestamp, score, level in risk_trend_rows
    ]
    direction = "unknown"
    change = None
    if len(trend) >= 4:
        quarter = max(1, len(trend) // 4)
        first = sum(point["score"] for point in trend[:quarter]) / quarter
        last = sum(point["score"] for point in trend[-quarter:]) / quarter
        change = round(last - first, 2)
        direction = "rising" if change > 3 else ("falling" if change < -3 else "stable")
    assessment = overview["risk"]
    return {
        "device_id": device_id,
        "assessment": assessment,
        "trend": trend,
        "trend_direction": direction,
        "trend_change": change,
        "top_contributors": assessment["contributions"][:4],
        "anomalies": overview["anomalies"],
        "alerts": overview["alerts"],
        "history_hours": hours,
        "notes": (
            overview["notes"]
            + [
                "Contributions are additive: each factor's points come from the configured weights, "
                "so their sum equals the risk score (before combination-rule penalties)."
            ]
        ),
    }


@router.get("/alerts", summary="Active alerts relevant to the risk assessment")
def risk_alerts(session: SessionDep, _: ReadAccessDep, device_id: DeviceDep) -> dict[str, Any]:
    alerts = AlertService(session).list(device_id, active_only=True, limit=50)
    return {
        "device_id": device_id,
        "assessments_affected_by": alerts["category_counts"],
        "alerts": alerts["alerts"],
    }
