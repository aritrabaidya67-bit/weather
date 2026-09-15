"""Thin accessor so routes import services from one place.

Keeping this indirection means route modules never import service modules
directly, which avoids import cycles between the API package and the services
package (services themselves stay importable on their own).
"""

from __future__ import annotations

from ..services import (  # noqa: F401
    ALERT_RULES,
    AlertService,
    AnalyticsService,
    AnomalyService,
    ChatbotService,
    DeviceService,
    IngestionRejected,
    OllamaUnavailable,
    PredictionService,
    RiskService,
    SensorService,
    get_ollama_client,
    runner,
    scheduler,
)

__all__ = [
    "ALERT_RULES",
    "AlertService",
    "AnalyticsService",
    "AnomalyService",
    "ChatbotService",
    "DeviceService",
    "IngestionRejected",
    "OllamaUnavailable",
    "PredictionService",
    "RiskService",
    "SensorService",
    "get_ollama_client",
    "runner",
    "scheduler",
]
