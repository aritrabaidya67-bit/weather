"""Analytics endpoints: dashboard overview, observations, trends, comparisons."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from ...schemas import SummaryResponse
from ..deps import DeviceDep, HoursQuery, ReadAccessDep, SessionDep
from ..services import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", summary="Everything the dashboard needs in one call")
def overview(
    session: SessionDep,
    _: ReadAccessDep,
    device_id: DeviceDep,
    hours: HoursQuery = 6.0,
) -> dict[str, Any]:
    return AnalyticsService(session).overview(device_id, hours=hours)


@router.get("/observations", summary="Evidence-based observations about the current window")
def observations(
    session: SessionDep,
    _: ReadAccessDep,
    device_id: DeviceDep,
    hours: HoursQuery = 6.0,
) -> dict[str, Any]:
    service = AnalyticsService(session)
    items = service.observations(device_id, hours=hours)
    return {
        "device_id": device_id,
        "hours": hours,
        "count": len(items),
        "observations": items,
        "notes": [
            "Every observation carries the numbers that support it; statements are withheld when the data is too thin."
        ]
        if items
        else ["No observation cleared its evidence threshold for this window."],
    }


@router.get("/trends", summary="Trend, rate of change and moving averages per channel")
def trends(
    session: SessionDep,
    _: ReadAccessDep,
    device_id: DeviceDep,
    hours: HoursQuery = 6.0,
    moving_average_window: Annotated[int, Query(ge=2, le=60)] = 5,
) -> dict[str, Any]:
    service = AnalyticsService(session)
    rows = service.readings.recent(device_id, hours=hours)
    metrics: dict[str, Any] = {}
    for metric in (
        "temperature_c",
        "humidity_pct",
        "pressure_hpa",
        "air_quality_index",
        "light_pct",
        "rain_pct",
    ):
        series = service.metric_series(rows, metric, include_points=False)
        metrics[metric] = {
            "label": series["label"],
            "unit": series["unit"],
            "trend": series["trend"],
            "slope_per_minute": series["slope_per_minute"],
            "change": series["change"],
            "change_pct": series["change_pct"],
            "latest": series["latest"],
            "mean": series["mean"],
            "min": series["minimum"],
            "max": series["maximum"],
            "samples": series["sample_count"],
            "r_squared": series["r_squared"],
            "rate_of_change_per_hour": service.rate_of_change_per_hour(rows, metric),
            "moving_average": service.moving_averages(
                device_id, metric, window=moving_average_window, hours=hours
            )[-60:],
        }
    return {
        "device_id": device_id,
        "hours": hours,
        "moving_average_window": moving_average_window,
        "trend_context": service.trend_context(device_id, hours=min(3.0, hours)),
        "metrics": metrics,
        "notes": [
            "A trend is only reported as rising/falling when the fitted slope exceeds 5% of the "
            "sensor's plausible per-minute movement (noise rejection)."
        ],
    }


@router.get("/classification", summary="Plain-language classification of the current environment")
def classification(session: SessionDep, _: ReadAccessDep, device_id: DeviceDep) -> dict[str, Any]:
    service = AnalyticsService(session)
    latest = service.readings.latest(device_id)
    metrics = service._metrics_from_row(latest)  # noqa: SLF001 - shared helper
    return {
        "device_id": device_id,
        "classification": service.classification(metrics),
        "heat_index_c": metrics.get("heat_index_c"),
        "dew_point_c": metrics.get("dew_point_c"),
        "has_data": latest is not None,
    }


@router.get("/summary/{period}", response_model=SummaryResponse, summary="Daily/weekly aggregate summary")
def summary(period: str, session: SessionDep, _: ReadAccessDep, device_id: DeviceDep) -> Any:
    if period not in ("day", "week"):
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="period must be 'day' or 'week'.",
        )
    return AnalyticsService(session).summary(device_id, period)


@router.get("/compare", summary="Compare the last N hours with the preceding N hours")
def compare(
    session: SessionDep,
    _: ReadAccessDep,
    device_id: DeviceDep,
    hours: Annotated[float, Query(ge=0.5, le=168)] = 6.0,
) -> dict[str, Any]:
    service = AnalyticsService(session)
    recent = service.readings.recent(device_id, hours=hours)
    # Pull twice the window and split it: the first half is the comparison period.
    rows = service.readings.recent(device_id, hours=hours * 2)
    split = max(0, len(rows) - len(recent))
    previous = rows[:split]
    result: dict[str, Any] = {"device_id": device_id, "hours": hours, "metrics": {}}
    for metric in (
        "temperature_c",
        "humidity_pct",
        "pressure_hpa",
        "air_quality_index",
        "light_pct",
        "rain_pct",
    ):
        current_series = service.metric_series(recent, metric, include_points=False)
        previous_series = service.metric_series(previous, metric, include_points=False)
        if not current_series["sample_count"]:
            continue
        delta = None
        if current_series["mean"] is not None and previous_series["mean"] is not None:
            delta = round(current_series["mean"] - previous_series["mean"], 3)
        result["metrics"][metric] = {
            "label": current_series["label"],
            "unit": current_series["unit"],
            "current_mean": current_series["mean"],
            "previous_mean": previous_series["mean"],
            "delta": delta,
            "current_samples": current_series["sample_count"],
            "previous_samples": previous_series["sample_count"],
            "sufficient_comparison": previous_series["sample_count"] >= 5,
            "message": (
                f"{current_series['label']} average is {delta:+.2f} {current_series['unit']} versus the previous {hours:g} hours."
                if delta is not None and previous_series["sample_count"] >= 5
                else f"Not enough earlier data to compare {current_series['label']}."
            ),
        }
    return result
