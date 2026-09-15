"""FastAPI application entrypoint.

Run locally with::

    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Binding to 0.0.0.0 matters: the Arduino must reach this machine over the local
Wi-Fi network using the laptop's LAN/hotspot IP, never localhost.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import ROUTERS
from .core.config import get_settings
from .core.database import describe_database, init_db
from .core.logging import configure_logging, get_logger
from .core.realtime import bus
from .core.security import keys_are_configured, register_secret
from .services import IngestionRejected, runner, scheduler
from .utils.timeutils import utcnow

settings = get_settings()
configure_logging(settings.log_level, settings.log_json)
logger = get_logger("app.main")

API_PREFIX = "/api/v1"

DESCRIPTION = """
**Environmental Intelligence Platform** - FastAPI backend.

Edge device: **Arduino UNO R4 WiFi** (DHT12/AM2302, BMP280, rain, LDR, MQ-135,
5 risk LEDs and a buzzer) posting JSON over Wi-Fi.

The backend validates and normalises every payload, stores the history, computes
an explainable risk score, detects anomalies, forecasts the near future, raises
alerts, streams everything to the dashboard over a WebSocket and answers
questions through an Ollama-backed chatbot that only ever sees the platform's own
data.

* Device endpoints require the `X-API-Key` header (set `API_KEY` in `backend/.env`).
* Read endpoints are open by default for the dashboard; set
  `REQUIRE_AUTH_FOR_READS=true` to lock them down too.
* No secret is ever exposed to the browser: the frontend only talks to this API.
"""


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "api_starting",
        app=settings.app_name,
        environment=settings.environment,
        host=settings.backend_host,
        port=settings.backend_port,
        simulation_mode=settings.simulation_mode,
    )
    register_secret(settings.api_key)
    register_secret(settings.admin_api_key)
    if not keys_are_configured(settings):
        logger.warning(
            "api_key_not_configured",
            hint="Set API_KEY in backend/.env; device endpoints return HTTP 503 until then.",
        )
    init_db()
    logger.info("database_ready", database=describe_database())
    await scheduler.start()
    if settings.simulation_mode:
        await runner.start()
    bus.publish("system", {"message": "backend started", "simulation_mode": settings.simulation_mode})
    try:
        yield
    finally:
        await runner.stop()
        await scheduler.stop()
        logger.info("api_stopped")


app = FastAPI(
    title=settings.app_name,
    description=DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*", settings.api_key_header, "X-Requested-With"],
    expose_headers=["X-Process-Time", "Retry-After"],
)


@app.middleware("http")
async def timing_middleware(request: Request, call_next: Any) -> Any:
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Process-Time"] = str(duration_ms)
    if request.url.path.startswith(API_PREFIX) and duration_ms > 750:
        logger.warning(
            "slow_request",
            path=request.url.path,
            method=request.method,
            duration_ms=duration_ms,
        )
    return response


@app.exception_handler(IngestionRejected)
async def ingestion_rejected_handler(_: Request, exc: IngestionRejected) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "accepted": False,
            "error": exc.detail,
            "device_id": exc.device_id,
            "field_errors": [
                {"field": key, "reason": reason} for key, reason in exc.rejected_fields.items()
            ],
            "warnings": exc.warnings,
            "timestamp": utcnow().isoformat(),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", [])]
        errors.append(
            {
                "field": ".".join(location) or "body",
                "reason": error.get("msg", "invalid value"),
                "type": error.get("type"),
            }
        )
    logger.warning("request_validation_failed", errors=len(errors), first=errors[:2])
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": "Request validation failed",
            "detail": "The payload did not match the expected schema.",
            "field_errors": errors,
            "timestamp": utcnow().isoformat(),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception", path=request.url.path, error=type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "Internal server error",
            "detail": "The request could not be completed. Check the backend logs for details.",
            "timestamp": utcnow().isoformat(),
        },
    )


@app.get("/", include_in_schema=False)
def root() -> dict[str, Any]:
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "api": API_PREFIX,
        "docs": "/docs",
        "health": f"{API_PREFIX}/health",
        "simulation_mode": settings.simulation_mode,
    }


for router in ROUTERS:
    app.include_router(router, prefix=API_PREFIX)

__all__ = ["app"]
