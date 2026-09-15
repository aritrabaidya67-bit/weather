"""Sensor ingestion, history, aggregation and anomaly endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from ...core.logging import get_logger
from ...core.security import client_identity, get_ingest_limiter
from ...core.sensors import CHANNELS, CHANNEL_ORDER, registry_public
from ...schemas import (
    AnomalyListResponse,
    HeartbeatResponse,
    HistoryResponse,
    IngestionResponse,
    SensorPayload,
    SensorReadingOut,
    SummaryResponse,
)
from ...utils.timeutils import utcnow
from ..deps import ApiKeyDep, DeviceDep, HoursQuery, ReadAccessDep, SessionDep
from ..services import AnalyticsService, AnomalyService, IngestionRejected, SensorService

logger = get_logger("app.api.sensors")
router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.get("/catalog", summary="Sensor registry (keys, units, ranges, bands)")
def catalog(_: ReadAccessDep) -> dict[str, Any]:
    return {
        "sensors": registry_public(),
        "channels": [
            {
                "key": key,
                "label": CHANNELS[key]["label"],
                "primary": CHANNELS[key]["primary"],
                "secondary": CHANNELS[key]["secondary"],
                "sensor": CHANNELS[key]["sensor"],
                "icon": CHANNELS[key]["icon"],
            }
            for key in CHANNEL_ORDER
        ],
    }


@router.post(
    "/data",
    response_model=IngestionResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest a sensor payload from the Arduino (or the simulator)",
    description=(
        "Requires the `X-API-Key` header. Accepts both the canonical payload shape and the "
        "legacy flat shape from the original project. Values outside the physical range of a "
        "sensor are rejected individually and reported in `rejected_fields`; a payload with no "
        "usable measurement at all is rejected with HTTP 422."
    ),
)
async def ingest(
    request: Request,
    session: SessionDep,
    _: ApiKeyDep,
    payload: Annotated[SensorPayload, Body(openapi_examples={  # type: ignore[valid-type]
        "arduino": {
            "summary": "Arduino UNO R4 WiFi payload",
            "value": {
                "device_id": "arduino-r4-wifi-01",
                "timestamp": "2026-09-15T09:12:00Z",
                "sequence": 128,
                "firmware_version": "1.0.0",
                "ip_address": "192.168.1.42",
                "rssi": -61,
                "transmission_interval_ms": 15000,
                "temperature_c": 27.4,
                "humidity_pct": 64.2,
                "bmp_temperature_c": 27.1,
                "pressure_hpa": 1009.4,
                "rain_raw": 880,
                "rain_pct": 10.0,
                "ldr_raw": 640,
                "light_pct": 71.0,
                "air_quality_raw": 295,
            },
        }
    })],
) -> Any:
    limiter = get_ingest_limiter()
    allowed, retry_after = limiter.check(client_identity(request))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Ingestion rate limit exceeded.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    body = await request.json() if await _has_json(request) else None
    service = SensorService(session)
    try:
        result = service.ingest(payload, raw_body=body, client_ip=client_identity(request))
    except IngestionRejected as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "accepted": False,
                "error": exc.detail,
                "detail": "Payload rejected: no usable measurements.",
                "device_id": exc.device_id,
                "field_errors": [
                    {"field": key, "reason": reason} for key, reason in exc.rejected_fields.items()
                ],
                "rejected_fields": exc.rejected_fields,
                "warnings": exc.warnings,
                "timestamp": utcnow().isoformat(),
            },
        )
    return result


async def _has_json(request: Request) -> bool:
    content_type = request.headers.get("content-type", "")
    return "json" in content_type.lower()


@router.post("/heartbeat", response_model=HeartbeatResponse, summary="Optional device heartbeat")
def heartbeat(
    session: SessionDep,
    _: ApiKeyDep,
    device_id: Annotated[str, Query(min_length=3, max_length=64)],
    rssi: Annotated[int | None, Query(ge=-127, le=10)] = None,
    ip_address: Annotated[str | None, Query(max_length=64)] = None,
    firmware_version: Annotated[str | None, Query(max_length=32)] = None,
) -> dict[str, Any]:
    from ..services import DeviceService

    device_service = DeviceService(session)
    device = device_service.ensure(
        device_id, firmware_version=firmware_version, ip_address=ip_address
    )
    if rssi is not None:
        device.rssi = rssi
    device_service.mark_online(device_id)
    session.commit()
    return {
        "success": True,
        "device_id": device_id,
        "server_time": utcnow().isoformat(),
        "ack": "ok",
        "expected_interval_seconds": device_service.settings.expected_transmission_interval_seconds,
        "commands": [],
    }


@router.get("/latest", response_model=SensorReadingOut, summary="Latest stored reading")
def latest(session: SessionDep, _: ReadAccessDep, device_id: DeviceDep) -> Any:
    reading = AnalyticsService(session).latest(device_id)
    if not reading:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No reading stored for this device yet. "
                "Start the simulator or flash the Arduino firmware."
            ),
        )
    return reading


@router.get("/history", response_model=HistoryResponse, summary="Historical readings and series")
def history(
    session: SessionDep,
    _: ReadAccessDep,
    device_id: DeviceDep,
    hours: HoursQuery = 6.0,
    bucket: Annotated[str | None, Query(pattern="^(15m|1h|6h|24h|7d)$")] = None,
    metrics: Annotated[str | None, Query(description="Comma separated metric keys")] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 400,
) -> Any:
    selected = [item.strip() for item in metrics.split(",")] if metrics else None
    return AnalyticsService(session).history(
        device_id, hours=hours, metrics=selected, bucket=bucket, limit=limit
    )


@router.get("/aggregate", summary="Bucketed averages (downsampled history)")
def aggregate(
    session: SessionDep,
    _: ReadAccessDep,
    device_id: DeviceDep,
    hours: HoursQuery = 24.0,
    bucket: Annotated[str, Query(pattern="^(15m|1h|6h|24h|7d)$")] = "6h",
) -> dict[str, Any]:
    service = AnalyticsService(session)
    return {
        "device_id": device_id,
        "range_hours": hours,
        "bucket": bucket,
        "points": service.aggregates(device_id, hours, bucket),
    }


@router.get("/summary/{period}", response_model=SummaryResponse, summary="Daily or weekly summary")
def summary(
    period: str,
    session: SessionDep,
    _: ReadAccessDep,
    device_id: DeviceDep,
) -> Any:
    if period not in ("day", "week"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="period must be 'day' or 'week'.",
        )
    return AnalyticsService(session).summary(device_id, period)


@router.get("/correlations", summary="Pairwise correlations between metrics")
def correlations(
    session: SessionDep,
    _: ReadAccessDep,
    device_id: DeviceDep,
    hours: HoursQuery = 6.0,
) -> dict[str, Any]:
    service = AnalyticsService(session)
    return {
        "device_id": device_id,
        "hours": hours,
        "correlations": service.correlations(device_id, hours=hours, limit=8),
        "notes": [
            "Correlations need at least 8 overlapping samples and are only reported above |r| = 0.5.",
            "Correlation describes co-movement inside this window; it is not causation.",
        ],
    }


@router.get("/anomalies", response_model=AnomalyListResponse, summary="Detected anomalies in the window")
def anomalies(
    session: SessionDep,
    _: ReadAccessDep,
    device_id: DeviceDep,
    hours: HoursQuery = 6.0,
) -> Any:
    service = AnalyticsService(session)
    detector = AnomalyService()
    window = service.readings.recent(device_id, hours=hours)
    found = service.anomalies_in_window(window)
    readiness = detector.baseline_readiness(window)
    baseline_ready = any(count >= detector.config.min_samples for count in readiness.values())
    return {
        "device_id": device_id,
        "count": len(found),
        "window_hours": hours,
        "severity_counts": {
            severity: sum(1 for item in found if item.get("severity") == severity)
            for severity in ("low", "medium", "high")
        },
        "sensor_counts": {
            metric: count for metric, count in detector.baseline_readiness(window).items()
        },
        "anomalies": found,
        "baseline_ready": baseline_ready,
        "notes": (
            ["Anomaly detection needs at least "
             f"{detector.config.min_samples} samples per sensor before it can report anything."]
            if not baseline_ready
            else ["Anomaly baseline is active; detections use a rolling mean/MAD z-score."]
        ),
    }


@router.get("/baseline", summary="Rolling baseline statistics per monitored metric")
def baseline(session: SessionDep, _: ReadAccessDep, device_id: DeviceDep) -> dict[str, Any]:
    service = AnalyticsService(session)
    detector = AnomalyService()
    window = service.readings.recent(device_id, limit=detector.config.window_points)
    return {
        "device_id": device_id,
        "window_points": detector.config.window_points,
        "min_samples": detector.config.min_samples,
        "metrics": detector.baseline_stats(window),
        "readiness": detector.baseline_readiness(window),
    }


@router.get("/health", summary="Per-sensor health (reporting rate, staleness, stuck detection)")
def sensor_health(session: SessionDep, _: ReadAccessDep, device_id: DeviceDep) -> dict[str, Any]:
    service = AnalyticsService(session)
    health = service.sensor_health(device_id)
    return {
        "device_id": device_id,
        "overall_health_score": service.health_score(device_id),
        "sensors": health,
    }
