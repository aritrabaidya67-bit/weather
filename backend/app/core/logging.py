"""Structured logging helpers.

A tiny structured logger is used instead of raw ``logging`` calls so that every
log line is ``event + key=value`` pairs. That keeps the terminal readable while
still being machine parseable, and it gives us one place to redact secrets.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

_CONFIGURED = False
_SECRETS: set[str] = set()

_LEVEL_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[35m",
}

_RESERVED = {"exc_info", "stack_info", "stacklevel", "extra"}


def register_secret(value: str | None) -> None:
    """Register a secret so it can never leak into logs."""
    if value and len(value) >= 4:
        _SECRETS.add(value)


def redact(text: str) -> str:
    for secret in _SECRETS:
        if secret in text:
            text = text.replace(secret, "***redacted***")
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, default=str))


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        level = record.levelname
        color = _LEVEL_COLORS.get(level, "")
        reset = "\033[0m" if color else ""
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        event = getattr(record, "event", record.getMessage())
        fields = getattr(record, "fields", None)
        suffix = ""
        if isinstance(fields, dict) and fields:
            rendered = " ".join(
                f"{key}={_fmt(value)}" for key, value in fields.items() if value is not None
            )
            suffix = f" {rendered}" if rendered else ""
        line = f"{ts} {color}{level:<7}{reset} {record.name:<28} {event}{suffix}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return redact(line)


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    text = str(value)
    return f'"{text}"' if " " in text else text


class StructuredLogger:
    """``logger.info("sensor_payload_received", device_id=..., bytes=...)``."""

    def __init__(self, name: str, context: dict[str, Any] | None = None) -> None:
        self._logger = logging.getLogger(name)
        self._context = dict(context or {})

    def bind(self, **context: Any) -> "StructuredLogger":
        merged = {**self._context, **context}
        return StructuredLogger(self._logger.name, merged)

    def _emit(self, log_level: int, event: str, exc_info: bool = False, **fields: Any) -> None:
        # NOTE: the parameter is called ``log_level`` on purpose - callers pass
        # domain fields such as ``level=<risk level>`` and those must not collide
        # with the logging level.
        if not self._logger.isEnabledFor(log_level):
            return
        merged = {**self._context, **fields}
        clean = {k: v for k, v in merged.items() if k not in _RESERVED}
        self._logger.log(
            log_level,
            event,
            extra={"event": event, "fields": clean},
            exc_info=exc_info,
        )

    def debug(self, event: str, **fields: Any) -> None:
        self._emit(logging.DEBUG, event, **fields)

    def info(self, event: str, **fields: Any) -> None:
        self._emit(logging.INFO, event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit(logging.WARNING, event, **fields)

    def error(self, event: str, exc_info: bool = False, **fields: Any) -> None:
        self._emit(logging.ERROR, event, exc_info=exc_info, **fields)

    def critical(self, event: str, exc_info: bool = False, **fields: Any) -> None:
        self._emit(logging.CRITICAL, event, exc_info=exc_info, **fields)

    def exception(self, event: str, **fields: Any) -> None:
        self._emit(logging.ERROR, event, exc_info=True, **fields)


def configure_logging(level: str = "INFO", as_json: bool = False) -> None:
    """Idempotent logging setup for the API process and the CLI tools."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter() if as_json else ConsoleFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Uvicorn's own handlers duplicate access logs otherwise.
    for noisy in ("uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(noisy)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    _CONFIGURED = True


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(name)
