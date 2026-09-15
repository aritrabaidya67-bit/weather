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
from .core.security import key_strength_problem, register_secret
from .services import IngestionRejected, scheduler
from .utils.timeutils import utcnow

settings = get_settings()
configure_logging(settings.log_level, settings.log_json)
logger = get_logger("app.main")

API_PREFIX = "/api/v1"
APP_VERSION = "1.0.0"

DESCRIPTION = """
**Environmental Intelligence Platform** - FastAPI backend.

Edge device: **Arduino UNO R4 WiFi** (AM2302/DHT22 temperature + humidity,
BMP280, rain, LDR, MQ-135, 5 risk LEDs and a buzzer) posting JSON over Wi-Fi.

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


def _validate_startup_configuration() -> tuple[list[str], list[str]]:
    """Refuse configurations that would be silently unsafe.

    Deliberate development conveniences (open reads, DEBUG) are allowed, but a
    *production* deployment must not inherit them by accident: the process exits
    at startup rather than serving an insecure API. Returns (problems, warnings):
    problems abort the start, warnings are logged and non-fatal.
    """
    problems: list[str] = []
    warnings: list[str] = []
    is_production = settings.environment.strip().lower() in {"production", "prod"}

    if is_production:
        if settings.debug:
            problems.append("DEBUG=true is not allowed when ENVIRONMENT=production.")
        if not settings.require_auth_for_reads:
            problems.append(
                "REQUIRE_AUTH_FOR_READS=false is not allowed when ENVIRONMENT=production. "
                "Set it to true so the dashboard and every read endpoint require the API key."
            )
        if settings.backend_host.strip() in {"0.0.0.0", "", "::"} and settings.cors_allow_lan_origins:
            # Binding everywhere plus blanket private-range CORS is a
            # demo convenience; in production list exact origins instead.
            problems.append(
                "CORS_ALLOW_LAN_ORIGINS=true must not be combined with a wildcard bind in "
                "production. List the exact frontend origin in CORS_ORIGINS."
            )
        admin_problem = (
            key_strength_problem(settings.admin_api_key)
            if settings.admin_api_key
            else "ADMIN_API_KEY is not set; destructive endpoints (/device/{id}/readings) answer 503."
        )
        if settings.admin_api_key is None:
            warnings.append(admin_problem)
        elif admin_problem:
            problems.append(f"ADMIN_API_KEY is set but unusable: {admin_problem}")

    key_problem = key_strength_problem(settings.api_key)
    if key_problem:
        warnings.append(
            "Device endpoints (/sensors/data, /device/*/risk-state) return HTTP 503 until a "
            f"real key is set: {key_problem} Generate one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    if settings.admin_api_key and settings.admin_api_key == settings.api_key:
        warnings.append(
            "ADMIN_API_KEY equals API_KEY; the admin boundary is meaningless when both "
            "credentials are the same value. Generate a separate admin key."
        )
    return problems, warnings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "api_starting",
        app=settings.app_name,
        environment=settings.environment,
        host=settings.backend_host,
        port=settings.backend_port,
    )
    register_secret(settings.api_key)
    register_secret(settings.admin_api_key)

    problems, startup_warnings = _validate_startup_configuration()
    for warning in startup_warnings:
        logger.warning("configuration_warning", detail=warning)
    if problems:
        for problem in problems:
            logger.error("configuration_rejected", detail=problem)
        raise RuntimeError(
            "Refusing to start with an unsafe production configuration: "
            + " | ".join(problems)
            + " (see backend/README.md - 'Secure defaults')"
        )

    if settings.cors_wildcard_requested:
        logger.warning(
            "cors_wildcard_ignored",
            detail=(
                "CORS_ORIGINS contained '*', which is ignored: list the exact frontend origins "
                "instead. A wildcard would let any web page call this API from a browser."
            ),
        )
    logger.info(
        "cors_configured",
        origins=settings.cors_origin_list,
        lan_regex=settings.cors_allow_lan_origins,
        custom_regex=bool(settings.cors_origin_regex.strip()),
    )
    init_db()
    logger.info("database_ready", database=describe_database())
    await scheduler.start()
    bus.publish("system", {"message": "backend started"})
    try:
        yield
    finally:
        await scheduler.stop()
        logger.info("api_stopped")


app = FastAPI(
    title=settings.app_name,
    description=DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    # None (not "") means "no regex": the explicit origin list above is the only
    # policy. See docs/architecture.md for the development vs production story.
    allow_origin_regex=settings.cors_regex,
    # No cookie/session auth exists, so credentials must stay off: with
    # allow_credentials the browser would send ambient credentials to any
    # allowed origin, which is exactly what we do not want here.
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", settings.api_key_header, "X-Requested-With"],
    expose_headers=["X-Process-Time", "Retry-After"],
)


@app.middleware("http")
async def security_and_timing_middleware(request: Request, call_next: Any) -> Any:
    """Security headers + timing, applied to every response.

    The API serves JSON and browser pages (/docs), never embedded HTML from user
    input, so a conservative CSP and the standard hardening headers cost nothing
    and remove a class of browser-side mistakes.
    """
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Process-Time"] = str(duration_ms)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
    )
    # HSTS is only meaningful (and only claimed) behind TLS; the LAN demo is
    # plain HTTP, so the header is deliberately NOT set here.
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
        "version": APP_VERSION,
        "api": API_PREFIX,
        "docs": "/docs",
        "health": f"{API_PREFIX}/health",
    }


for router in ROUTERS:
    app.include_router(router, prefix=API_PREFIX)

__all__ = ["app"]
