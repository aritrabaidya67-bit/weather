"""Shared response schemas (health, errors, system status)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    environment: str
    uptime_seconds: float
    server_time: str
    database: dict[str, Any] = Field(default_factory=dict)
    device: dict[str, Any] = Field(default_factory=dict)
    ollama: dict[str, Any] = Field(default_factory=dict)
    checks: dict[str, str] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: str | None = None
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: str | None = None


class SystemStatusResponse(BaseModel):
    """Aggregate status used by the dashboard header."""

    server_time: str
    backend: str = "online"
    database: str = "online"
    arduino: str = "offline"
    device_online: bool = False
    device_last_seen_at: str | None = None
    device_seconds_since_payload: float | None = None
    reading_stale: bool = False
    realtime_subscribers: int = 0
    data_source: str = "unknown"
    ollama: dict[str, Any] = Field(default_factory=dict)
    active_alerts: int = 0
    chat_rate_limit_per_minute: int = 20
    notes: list[str] = Field(default_factory=list)
