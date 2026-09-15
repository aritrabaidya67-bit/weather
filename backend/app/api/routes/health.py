"""Health, system status and platform metadata endpoints."""

from __future__ import annotations

import socket
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from ...core.config import get_settings
from ...core.logging import get_logger
from ...core.realtime import bus
from ...core.sensors import CHANNELS, CHANNEL_ORDER, registry_public
from ...schemas import HealthResponse, MetaResponse, SystemStatusResponse
from ...utils.timeutils import seconds_between, utcnow
from ..deps import SessionDep, resolve_device_id
from ..services import ALERT_RULES, AlertService, DeviceService, RiskService, get_ollama_client, scheduler

logger = get_logger("app.api.health")
router = APIRouter(tags=["system"])
STARTED_AT = utcnow()
#: Keep in one place so the root payload, /health and /meta never disagree.
APP_VERSION = "1.0.0"


def local_addresses() -> list[str]:
    """Best-effort list of LAN addresses so the user knows what to put in the firmware."""
    addresses: set[str] = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            addr = info[4][0]
            if "." in addr and not addr.startswith("127."):
                addresses.add(addr)
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            addresses.add(sock.getsockname()[0])
    except OSError:
        pass
    return sorted(addresses)


@router.get("/health", response_model=HealthResponse, summary="Liveness/readiness probe")
def health(session: SessionDep) -> dict[str, Any]:
    settings = get_settings()
    database_status = "ok"
    database_detail: dict[str, Any] = {}
    try:
        session.execute(text("SELECT 1"))
        from ...repositories import ReadingRepository

        repository = ReadingRepository(session)
        database_detail = {
            "dialect": session.bind.dialect.name if session.bind else "unknown",
            "readings": repository.count(),
        }
    except Exception as exc:  # noqa: BLE001 - health must always answer
        # The exception text can contain connection strings/paths; the client
        # only needs the fact and the class. Details stay in the server log.
        logger.warning("health_database_check_failed", error_type=type(exc).__name__)
        logger.debug("health_database_check_detail", exc_info=True)
        database_status = "error"
        database_detail = {"error": f"{type(exc).__name__} (see server logs)"}

    device = DeviceService(session).status(resolve_device_id(session, None), include_sensor_health=False)
    ollama_status = _ollama_status_sync()

    checks = {
        "database": database_status,
        "device": "online" if device["online"] else "offline",
        "realtime": "ok",
        "ollama": "ok" if ollama_status.get("available") else "degraded",
    }
    overall = "ok" if database_status == "ok" else "degraded"
    return {
        "status": overall,
        "version": APP_VERSION,
        "environment": settings.environment,
        "uptime_seconds": round(seconds_between(utcnow(), STARTED_AT), 1),
        "server_time": utcnow().isoformat(),
        "database": database_detail,
        "device": {
            "device_id": device["device_id"],
            "online": device["online"],
            "last_payload_at": device["last_payload_at"],
            "seconds_since_last_payload": device["seconds_since_last_payload"],
        },
        "ollama": ollama_status,
        "checks": checks,
    }


@router.get("/status", response_model=SystemStatusResponse, summary="Aggregate status for the dashboard header")
def status(session: SessionDep) -> dict[str, Any]:
    settings = get_settings()
    device_service = DeviceService(session)
    device_id = resolve_device_id(session, None)
    device = device_service.status(device_id, include_sensor_health=False)
    alerts = AlertService(session)
    ollama_status = _ollama_status_sync()
    notes: list[str] = list(device.get("notes") or [])
    reading_stale = bool(
        device["seconds_since_last_payload"] is None
        or device["seconds_since_last_payload"] > settings.stale_reading_seconds
    )
    source = device.get("source") or "unknown"
    return {
        "server_time": utcnow().isoformat(),
        "backend": "online",
        "database": "online",
        "arduino": device["status"],
        "device_online": bool(device["online"]),
        "device_last_seen_at": device["last_payload_at"],
        "device_seconds_since_payload": device["seconds_since_last_payload"],
        "reading_stale": reading_stale,
        "realtime_subscribers": bus.subscriber_count,
        "data_source": source,
        "ollama": ollama_status,
        "active_alerts": alerts.repository.count(device_id, active_only=True),
        "chat_rate_limit_per_minute": settings.chat_rate_limit_per_minute,
        "notes": notes,
    }


@router.get("/meta", response_model=MetaResponse, summary="Sensor registry, risk model, alert rules and features")
def meta(session: SessionDep) -> dict[str, Any]:
    settings = get_settings()
    risk = RiskService()
    addresses = local_addresses()
    recommended = None
    if addresses:
        recommended = f"http://{addresses[-1]}:{settings.backend_port}"
    return {
        "app_name": settings.app_name,
        "version": APP_VERSION,
        "environment": settings.environment,
        "server_time": utcnow().isoformat(),
        "api_version": "v1",
        "risk_model": risk.model_description(),
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
        "alert_rules": AlertService(session).catalogue(),
        "features": {
            "realtime_websocket": True,
            "realtime_sse": True,
            "anomaly_detection": True,
            "prediction": True,
            "chatbot": settings.ollama_enabled,
            "history_retention_days": settings.retention_days,
        },
        "local_addresses": addresses,
        "recommended_backend_url": recommended,
    }


@router.get("/system/workers", summary="Background worker status")
def workers() -> dict[str, Any]:
    return {
        "background": scheduler.status(),
        "realtime_subscribers": bus.subscriber_count,
        "rules_loaded": len(ALERT_RULES),
    }


def _ollama_status_sync() -> dict[str, Any]:
    """Non-blocking snapshot of the last Ollama probe (cached)."""
    client = get_ollama_client()
    cached = client._status  # noqa: SLF001 - deliberate read of the cached probe
    if cached is None:
        return {
            "available": False,
            "model": None,
            "models_available": [],
            "running": False,
            "installed": False,
            "host": get_settings().ollama_host,
            "detail": "Ollama status has not been probed yet. Open the AI chat page to trigger a probe.",
        }
    payload = cached.as_dict()
    payload["available"] = bool(cached.running and cached.selected_model)
    return payload
