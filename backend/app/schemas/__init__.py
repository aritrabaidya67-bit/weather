"""Pydantic schemas (the wire contract for Arduino, simulator and frontend)."""

from .alert import AlertListResponse, AlertOut, AlertRuleOut
from .anomaly import Anomaly, AnomalyListResponse
from .chat import (
    ChatHistoryResponse,
    ChatRequest,
    ChatResponse,
    ChatStatusResponse,
    ChatStreamChunk,
    ChatTurn,
    SuggestedQuestionsResponse,
)
from .common import ErrorResponse, HealthResponse, SystemStatusResponse
from .device import (
    DeviceListResponse,
    DeviceOut,
    HeartbeatResponse,
    MetaResponse,
    RiskStateResponse,
    SensorHealthOut,
)
from .prediction import (
    MetricPrediction,
    PredictionAccuracyResponse,
    PredictionHistoryResponse,
    PredictionResponse,
    RainForecast,
    RiskForecast,
)
from .risk import (
    RiskAnalysisResponse,
    RiskAssessment,
    RiskContribution,
    RiskLevelInfo,
    RiskModelResponse,
    RiskTrendPoint,
)
from .sensor import (
    AggregatePoint,
    HistoryResponse,
    IngestionResponse,
    MetricSeries,
    SensorPayload,
    SensorReadingOut,
    SeriesPoint,
    SummaryResponse,
)

__all__ = [
    "AggregatePoint",
    "AlertListResponse",
    "AlertOut",
    "AlertRuleOut",
    "Anomaly",
    "AnomalyListResponse",
    "ChatHistoryResponse",
    "ChatRequest",
    "ChatResponse",
    "ChatStatusResponse",
    "ChatStreamChunk",
    "ChatTurn",
    "DeviceListResponse",
    "DeviceOut",
    "ErrorResponse",
    "HeartbeatResponse",
    "HealthResponse",
    "HistoryResponse",
    "IngestionResponse",
    "MetaResponse",
    "MetricPrediction",
    "MetricSeries",
    "PredictionAccuracyResponse",
    "PredictionHistoryResponse",
    "PredictionResponse",
    "RainForecast",
    "RiskAnalysisResponse",
    "RiskAssessment",
    "RiskContribution",
    "RiskForecast",
    "RiskLevelInfo",
    "RiskModelResponse",
    "RiskStateResponse",
    "RiskTrendPoint",
    "SensorHealthOut",
    "SensorPayload",
    "SensorReadingOut",
    "SeriesPoint",
    "SummaryResponse",
    "SystemStatusResponse",
]
