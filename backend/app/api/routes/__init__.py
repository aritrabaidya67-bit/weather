"""API route modules."""

from . import (
    alerts,
    analytics,
    chatbot,
    device,
    health,
    predictions,
    realtime,
    risk,
    sensors,
)

#: Every router mounted by ``app.main`` under the versioned prefix.
ROUTERS = (
    health.router,
    sensors.router,
    analytics.router,
    risk.router,
    predictions.router,
    alerts.router,
    device.router,
    chatbot.router,
    realtime.router,
)

__all__ = ["ROUTERS"]
