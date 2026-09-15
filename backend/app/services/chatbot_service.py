"""Environmental-analysis chatbot.

The LLM never sees a blank prompt and never supplies numbers: the backend builds a
complete structured snapshot of the platform's own data (current reading, risk
assessment, anomalies, forecasts, baselines, alerts, sensor health) and instructs
the model to *interpret* it, quoting only values present in the snapshot.

If Ollama is unavailable the same snapshot is answered by a deterministic
rule-based analyst, so the chatbot degrades instead of breaking, and it says so.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, AsyncIterator, Sequence

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.logging import get_logger
from ..core.sensors import CHANNELS, CHANNEL_ORDER, REGISTRY
from ..models import ChatMessage
from ..repositories import ChatRepository
from ..utils.timeutils import ensure_utc, humanize_seconds, utcnow
from .analytics_service import AnalyticsService
from .anomaly_service import AnomalyService
from .ollama_client import OllamaClient, OllamaUnavailable, get_ollama_client
from .prediction_service import PredictionService

logger = get_logger("app.chatbot")

GROUNDING_RULES = """You are the analysis assistant of an environmental monitoring platform.
The platform collects data from an Arduino UNO R4 Wi-Fi node with DHT12/AM2302
temperature+humidity, BMP280 pressure, rain, LDR light and MQ-135 air-quality sensors.

ABSOLUTE RULES
1. Every number you mention MUST come from the DATA SNAPSHOT below. Never invent,
   estimate or "round to something nicer" a sensor value.
2. If a value is null/missing, say the sensor has no reading and, when known, why.
3. Predictions are statistical estimates. Always state the horizon and confidence,
   and never present a forecast as a certainty.
4. The snapshot's data_source field names the source of the readings. If it reports
   that no data has been received, say so instead of describing conditions.
5. If the data is stale, say so before giving any assessment.
6. The air-quality index is a relative index derived from the MQ-135 ADC against a
   clean-air baseline, not a calibrated ppm or official AQI. Say so if you cite it.
7. If the question cannot be answered from the snapshot, say what is missing instead
   of guessing.
8. No medical, safety-critical or regulatory advice. Give practical, generic guidance.
9. Be concise: a short answer in 2-6 sentences or a compact bullet list, with units.
10. Only answer questions about this platform's environment, sensors, data, risk,
    forecasts and alerts."""

class _ModelSkipped(Exception):
    """Internal signal: the platform answers this question without the model."""


FALLBACK_WARNING = (
    "Ollama is not available, so this answer was produced by the platform's built-in "
    "rule-based analyst using the same data snapshot. Start Ollama to get "
    "model-generated explanations."
)


class ChatbotService:
    def __init__(self, session: Session, client: OllamaClient | None = None) -> None:
        self.session = session
        self.settings = get_settings()
        self.analytics = AnalyticsService(session)
        self.predictions = PredictionService(session)
        self.repository = ChatRepository(session)
        self.client = client or get_ollama_client()

    # ----------------------------------------------------------------- context
    def build_context(self, device_id: str) -> dict[str, Any]:
        latest_row = self.analytics.readings.latest(device_id)
        metrics = self.analytics._metrics_from_row(latest_row)  # noqa: SLF001
        overview = self.analytics.overview(device_id)
        anomalies = list(latest_row.anomalies or []) if latest_row else []
        prediction = self.predictions.forecast(device_id)
        trend = self.analytics.trend_context(device_id)
        history_for_baseline = self.analytics.readings.recent(
            device_id, limit=self.settings.anomaly.window_points
        )
        baselines = AnomalyService(self.settings.anomaly).baseline_stats(history_for_baseline)

        current: dict[str, Any] = {}
        for key, value in metrics.items():
            spec = REGISTRY.get(key)
            if value is None:
                current[key] = None
                continue
            current[key] = {
                "value": round(float(value), spec.decimals + 1) if spec else float(value),
                "unit": spec.unit if spec else None,
                "label": spec.label if spec else key,
                "interpretation": spec.interpret(float(value))[0] if spec else None,
            }

        stats_6h: dict[str, Any] = {}
        window = self.analytics.readings.recent(device_id, hours=6)
        for channel in CHANNEL_ORDER:
            metric = str(CHANNELS[channel]["primary"])
            series = self.analytics.metric_series(window, metric, include_points=False)
            if series["sample_count"]:
                stats_6h[metric] = {
                    "unit": series["unit"],
                    "min": series["minimum"],
                    "max": series["maximum"],
                    "mean": series["mean"],
                    "latest": series["latest"],
                    "change_6h": series["change"],
                    "slope_per_minute": series["slope_per_minute"],
                    "trend": series["trend"],
                    "samples": series["sample_count"],
                }

        alerts = self.analytics.alerts.list(device_id, active_only=True, limit=10)
        context: dict[str, Any] = {
            "as_of": utcnow().isoformat(),
            "data_source": "live hardware" if latest_row is not None else "no data",
            "data_quality": {
                "has_any_data": latest_row is not None,
                "latest_reading_age_seconds": (
                    round(
                        (
                            utcnow() - (ensure_utc(latest_row.received_at) or utcnow())
                        ).total_seconds(),
                        1,
                    )
                    if latest_row
                    else None
                ),
                "stale": bool(overview["stale"]) if latest_row else True,
                "readings_in_window": overview["reading_count"],
                "sufficient_history": overview["sufficient_history"],
                "missing_channels": [
                    channel
                    for channel in CHANNELS
                    if metrics.get(str(CHANNELS[channel]["primary"])) is None
                ],
            },
            "device": overview.get("device", {}),
            "current_reading": current,
            "environment_classification": overview["classification"],
            "risk": {
                "score": overview["risk"]["score"],
                "level": overview["risk"]["level"],
                "label": overview["risk"]["label"],
                "confidence": overview["risk"]["confidence"],
                "reasons": overview["risk"]["reasons"],
                "factors_reducing_risk": overview["risk"]["reducing_factors"],
                "recommended_actions": overview["risk"]["recommended_actions"],
                "contributions": [
                    {
                        "factor": item["label"],
                        "points_added": item["points"],
                        "max_points": item["max_points"],
                        "reading": item["reading"],
                        "unit": item["unit"],
                    }
                    for item in overview["risk"]["contributions"]
                    if item["points"] > 0.5
                ],
            },
            "anomalies": anomalies,
            "alerts_active": [
                {
                    "severity": alert.severity,
                    "title": alert.title,
                    "message": alert.message,
                    "sensor": alert.sensor,
                    "since": (ensure_utc(alert.triggered_at) or utcnow()).isoformat(),
                }
                for alert in alerts
            ],
            "statistics_last_6h": stats_6h,
            "observations": [item["text"] for item in overview["observation_list"]],
            "correlations": overview["correlations"],
            "sensor_health": [
                {
                    "sensor": item["label"],
                    "status": item["status"],
                    "message": item["message"],
                }
                for item in overview["sensor_health"]
            ],
            "prediction": {
                "horizon_minutes": prediction["primary_horizon_minutes"],
                "generated_at": prediction["generated_at"],
                "data_sufficient": prediction["data_sufficient"],
                "samples_used": prediction["samples_used"],
                "observation_window_minutes": prediction["observation_window_minutes"],
                "metrics": {
                    key: {
                        "current": value.get("current_value"),
                        "predicted": value.get("predicted_value"),
                        "unit": value.get("unit"),
                        "direction": value.get("direction"),
                        "confidence": value.get("confidence"),
                        "method": value.get("method"),
                        "expected_status": value.get("expected_status"),
                        "warnings": value.get("warnings", []),
                    }
                    for key, value in prediction["metrics"].items()
                },
                "risk": prediction.get("risk"),
                "rain": prediction.get("rain"),
                "summary": prediction.get("summary", []),
                "notes": prediction.get("notes", []),
            },
            "trend_context": {
                "pressure_change_hpa_3h": trend.get("pressure_change_hpa_3h"),
                "air_quality_slope_per_minute": trend.get("air_quality_slope_per_minute"),
                "temperature_slope_per_minute": trend.get("temperature_slope_per_minute"),
                "humidity_slope_per_minute": trend.get("humidity_slope_per_minute"),
            },
            "recent_baseline": {
                metric: {
                    "mean": value["mean"],
                    "sigma": value["sigma"],
                    "samples": value["samples"],
                }
                for metric, value in baselines.items()
                if value.get("samples")
            },
        }
        return context

    def context_json(self, context: dict[str, Any]) -> str:
        text = json.dumps(context, indent=1, default=str)
        limit = self.settings.chat_max_context_chars
        if len(text) > limit:
            logger.warning("chat_context_truncated", chars=len(text), limit=limit)
            # Keep the most decision-relevant sections when trimming.
            trimmed = {
                key: value
                for key, value in context.items()
                if key
                in (
                    "as_of",
                    "data_source",
                    "data_quality",
                    "device",
                    "current_reading",
                    "risk",
                    "anomalies",
                    "alerts_active",
                    "prediction",
                    "observations",
                    "statistics_last_6h",
                    "trend_context",
                )
            }
            text = json.dumps(trimmed, indent=1, default=str)[:limit]
        return text

    def build_messages(
        self,
        question: str,
        history: Sequence[dict[str, str]],
        context: dict[str, Any],
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": GROUNDING_RULES},
            {
                "role": "system",
                "content": "DATA SNAPSHOT (JSON, the only source of truth):\n"
                + self.context_json(context),
            },
        ]
        for turn in list(history)[-self.settings.chat_max_history_messages :]:
            role = turn.get("role")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": question})
        return messages

    # ------------------------------------------------------------------ answer
    async def answer(
        self,
        *,
        device_id: str,
        message: str,
        session_id: str,
        history: Sequence[dict[str, str]] = (),
    ) -> dict[str, Any]:
        started = time.perf_counter()
        context = self.build_context(device_id)
        grounding = "historical_data" if context["data_quality"]["has_any_data"] else "analysis_only"
        fallback_used = False
        warning: str | None = None
        model: str | None = None
        if not context["data_quality"]["has_any_data"]:
            # Nothing has ever been measured, so there is no environment to
            # describe. Asking the model anyway invites it to narrate a risk
            # score that only exists as a default, so the platform answers this
            # one deterministically and says exactly why.
            answer = self._fallback_answer(message, context)
            fallback_used = True
            grounding = "analysis_only"
            warning = (
                "No sensor readings have been received yet, so this answer comes from the "
                "platform's own state check rather than the language model."
            )
            logger.info("chatbot_no_data_shortcut")
        else:
            answer = ""
        try:
            if fallback_used:
                raise OllamaUnavailable("skipped: no readings available")
            messages = self.build_messages(message, history, context)
            answer, model = await self.client.chat(messages)
            if not answer:
                # A thinking model can spend its entire token budget on internal
                # reasoning and return nothing. One retry with a wider budget is
                # far better than dropping straight to the rule-based analyst.
                logger.warning("chat_empty_answer_retrying", model=model)
                answer, model = await self.client.chat(
                    messages, max_tokens=self.settings.ollama_num_predict * 2
                )
            if not answer:
                raise OllamaUnavailable("The model returned an empty response.")
        except OllamaUnavailable as exc:
            # Never hide the degradation: the client is always told that a
            # rule-based answer was substituted and why. The no-data shortcut
            # above already set its own, more accurate, explanation.
            if warning is None:
                warning = f"{FALLBACK_WARNING} Reason: {exc}"
                logger.warning("chatbot_fallback_used", error=str(exc))
            else:
                logger.info("chatbot_answered_without_model")
            answer = self._fallback_answer(message, context)
            fallback_used = True
            grounding = "analysis_only"

        latency_ms = round((time.perf_counter() - started) * 1000)
        citations = self._citations(message, context)
        self._persist(
            session_id=session_id,
            question=message,
            answer=answer,
            model=model,
            latency_ms=latency_ms,
            grounding=grounding,
            context=context,
            error=warning if fallback_used else None,
        )
        return {
            "session_id": session_id,
            "answer": answer,
            "model": model,
            "grounding": grounding,
            "data_available": bool(context["data_quality"]["has_any_data"]),
            "used_context": {
                "risk_score": context["risk"]["score"],
                "risk_level": context["risk"]["level"],
                "data_source": context["data_source"],
                "stale": context["data_quality"]["stale"],
                "anomalies": len(context["anomalies"]),
                "active_alerts": len(context["alerts_active"]),
                "prediction_available": context["prediction"]["data_sufficient"],
                "snapshot_at": context["as_of"],
            },
            "citations": citations,
            "latency_ms": latency_ms,
            "fallback_used": fallback_used,
            "warning": warning,
            "created_at": utcnow().isoformat(),
        }

    def prepare(
        self, device_id: str, message: str, history: Sequence[dict[str, str]]
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        """Build the data snapshot and prompt *before* a streaming response starts.

        FastAPI closes request-scoped dependencies before a StreamingResponse is
        consumed, so all database work has to happen up front.
        """
        context = self.build_context(device_id)
        messages = self.build_messages(message, history, context)
        return messages, context

    async def stream(
        self,
        *,
        device_id: str | None = None,
        message: str,
        session_id: str,
        history: Sequence[dict[str, str]] = (),
        messages: list[dict[str, str]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        if messages is None or context is None:
            assert device_id is not None, "device_id is required when no prepared context is given"
            messages, context = self.prepare(device_id, message, history)
        collected: list[str] = []
        model: str | None = None
        started = time.perf_counter()
        yield {
            "type": "meta",
            "session_id": session_id,
            "detail": "Answering from " + str(context["data_source"]) + " data",
        }
        if not context["data_quality"]["has_any_data"]:
            # Same reasoning as the non-streaming path: with no readings there is
            # nothing for the model to interpret, so answer deterministically.
            fallback = self._fallback_answer(message, context)
            yield {
                "type": "token",
                "content": fallback,
                "detail": "No sensor readings have been received yet.",
            }
            collected = [fallback]
        try:
            if collected:
                raise _ModelSkipped("no readings available")
            async for chunk, used_model in self.client.chat_stream(messages):
                model = used_model
                collected.append(chunk)
                yield {"type": "token", "content": chunk, "model": used_model}
        except _ModelSkipped:
            logger.info("chatbot_stream_answered_without_model")
        except OllamaUnavailable as exc:
            logger.warning("chatbot_stream_fallback", error=str(exc))
            fallback = self._fallback_answer(message, context)
            yield {
                "type": "token",
                "content": fallback,
                "detail": FALLBACK_WARNING,
            }
            collected = [fallback]
        if not collected:
            # Same failure mode as the non-streaming path: nothing came back, so
            # say that with the deterministic analyst instead of an empty bubble.
            logger.warning("chatbot_stream_empty", model=model)
            fallback = self._fallback_answer(message, context)
            yield {"type": "token", "content": fallback, "detail": FALLBACK_WARNING}
            collected = [fallback]
        answer = "".join(collected)
        latency_ms = round((time.perf_counter() - started) * 1000)
        self.persist_detached(
            session_id=session_id,
            question=message,
            answer=answer,
            model=model,
            latency_ms=latency_ms,
            grounding="historical_data" if context["data_quality"]["has_any_data"] else "analysis_only",
            context=context,
            error=None,
        )
        yield {"type": "done", "model": model, "content": answer, "detail": str(latency_ms)}

    def persist_detached(self, **kwargs: Any) -> None:
        """Persist a transcript with its own short-lived session.

        Used by the streaming endpoint, where the request-scoped session is already
        closed by the time the stream finishes.
        """
        from ..core.database import session_scope

        try:
            with session_scope() as session:
                ChatbotService(session, client=self.client)._persist(**kwargs)  # noqa: SLF001
        except Exception:  # pragma: no cover - persistence must never break chat
            logger.exception("chat_persist_detached_failed")

    # --------------------------------------------------------------- fallbacks
    def _fallback_answer(self, question: str, context: dict[str, Any]) -> str:
        """Deterministic analyst used when the LLM is unreachable."""
        text = question.lower()
        data = context["current_reading"]
        risk = context["risk"]
        quality = context["data_quality"]

        def metric(key: str) -> str:
            entry = data.get(key) or {}
            if not entry or entry.get("value") is None:
                return f"{key} has no reading"
            return f"{entry['value']} {entry.get('unit') or ''}".strip()

        if not quality["has_any_data"]:
            return (
                "No sensor data has been received yet, so there is nothing to analyse. "
                "The dashboard will populate as soon as the Arduino node sends its first payload."
            )

        header = ""
        if quality["stale"]:
            header = (
                f"Note: the latest reading is {humanize_seconds(quality['latest_reading_age_seconds'])} old, "
                "so this assessment may not reflect current conditions.\n"
            )

        if any(word in text for word in ("why", "risk", "dangerous", "unsafe", "safe")):
            factors = ", ".join(
                f"{item['factor']} +{item['points_added']:.0f}"
                for item in risk["contributions"][:4]
            ) or "no dominant factor"
            body = (
                f"Risk score is {risk['score']:.0f}/100 (level {risk['level']}, {risk['label']}). "
                f"Main contributors: {factors}. Reasons: "
                + "; ".join(risk["reasons"][:3])
                + f". Recommended actions: {'; '.join(risk['recommended_actions'][:2]) or 'none specific'}."
            )
        elif any(word in text for word in ("air quality", "pollution", "gas", "mq-135", "aqi")):
            body = (
                f"Air-quality index is {metric('air_quality_index')} (relative index from the MQ-135 "
                "against a clean-air baseline, not ppm). "
                f"Raw sensor value: {metric('air_quality_raw')}. "
                f"Interpretation: {(data.get('air_quality_index') or {}).get('interpretation')}."
            )
        elif "humid" in text:
            body = (
                f"Relative humidity is {metric('humidity_pct')} "
                f"({(data.get('humidity_pct') or {}).get('interpretation')}); "
                f"the 6-hour mean was {context['statistics_last_6h'].get('humidity_pct', {}).get('mean')} %RH."
            )
        elif "temperature" in text or "hot" in text or "cold" in text:
            stats = context["statistics_last_6h"].get("temperature_c", {})
            body = (
                f"Temperature is {metric('temperature_c')} "
                f"({(data.get('temperature_c') or {}).get('interpretation')}). "
                f"6-hour range {stats.get('min')} to {stats.get('max')} degC, trend {stats.get('trend')}."
            )
        elif "pressure" in text or "barometer" in text:
            body = (
                f"Pressure is {metric('pressure_hpa')}; it changed "
                f"{context['trend_context'].get('pressure_change_hpa_3h')} hPa over the last 3 hours."
            )
        elif "rain" in text or "wet" in text:
            rain = context["prediction"].get("rain") or {}
            body = (
                f"Rain sensor wetness is {metric('rain_pct')} "
                f"(status: {metric('rain_status') if 'rain_status' in data else 'derived'}). "
                f"Estimated probability of rain within {rain.get('horizon_minutes', 30)} minutes: "
                f"{round((rain.get('probability') or 0) * 100)}% (heuristic, confidence "
                f"{round((rain.get('confidence') or 0) * 100)}%)."
            )
        elif any(word in text for word in ("predict", "forecast", "next", "future", "likely", "will")):
            prediction = context["prediction"]
            if not prediction["data_sufficient"]:
                body = (
                    "There is insufficient historical data for a reliable prediction. "
                    f"Available samples: {prediction['samples_used']}."
                )
            else:
                body = " ".join(prediction["summary"][:3])
        elif any(word in text for word in ("anomal", "weird", "strange", "wrong")):
            anomalies = context["anomalies"]
            if not anomalies:
                body = "No anomalies are currently flagged for the latest reading."
            else:
                body = " | ".join(str(item.get("message")) for item in anomalies[:3])
        elif any(word in text for word in ("recommend", "advice", "should i", "action")):
            body = (
                "Recommended actions: "
                + "; ".join(risk["recommended_actions"][:4])
                + ". These follow from the current risk factors: "
                + ", ".join(item["factor"] for item in risk["contributions"][:3])
                + "."
            )
        elif any(word in text for word in ("sensor", "device", "arduino", "hardware", "online", "status")):
            device = context["device"]
            unhealthy = [
                item for item in context["sensor_health"] if item["status"] not in ("ok", "unknown")
            ]
            body = (
                f"Device {device.get('device_id')} is {device.get('status')} "
                f"(source: {device.get('source')}, firmware {device.get('firmware_version') or 'unknown'}). "
                + (
                    "Sensor issues: " + "; ".join(item["message"] for item in unhealthy[:3])
                    if unhealthy
                    else "All expected sensors are reporting normally."
                )
            )
        elif any(word in text for word in ("compare", "average", "baseline", "today", "trend")):
            stats = context["statistics_last_6h"]
            body = "Last 6 hours: " + " | ".join(
                f"{REGISTRY[key].label} mean {value['mean']} {value['unit']}, "
                f"min {value['min']}, max {value['max']}, trend {value['trend']}"
                for key, value in stats.items()
            ) + "."
        else:
            body = (
                f"Current conditions: {context['environment_classification']['label']}. "
                f"Risk {risk['score']:.0f}/100 ({risk['label']}). "
                f"Temperature {metric('temperature_c')}, humidity {metric('humidity_pct')}, "
                f"pressure {metric('pressure_hpa')}, air-quality index {metric('air_quality_index')}."
            )
        return header + body

    def _citations(self, question: str, context: dict[str, Any]) -> list[dict[str, Any]]:
        text = question.lower()
        wanted: list[str] = []
        if any(word in text for word in ("temperature", "hot", "cold", "trend", "compare")):
            wanted.extend(["temperature_c", "humidity_pct"])
        if any(word in text for word in ("air", "pollution", "gas")):
            wanted.extend(["air_quality_index", "air_quality_raw"])
        if "pressure" in text:
            wanted.append("pressure_hpa")
        if "rain" in text:
            wanted.extend(["rain_pct", "rain_raw"])
        if "light" in text or "dark" in text:
            wanted.append("light_pct")
        if not wanted:
            wanted = ["temperature_c", "humidity_pct", "air_quality_index", "pressure_hpa"]
        citations: list[dict[str, Any]] = []
        snapshot_at = str(context["as_of"])
        for key in dict.fromkeys(wanted):
            entry = context["current_reading"].get(key)
            if not entry or entry.get("value") is None:
                continue
            citations.append(
                {
                    "label": entry.get("label") or key,
                    "value": f"{entry['value']} {entry.get('unit') or ''}".strip(),
                    "source": "latest stored reading",
                    "timestamp": snapshot_at,
                }
            )
        citations.append(
            {
                "label": "Risk score",
                "value": f"{context['risk']['score']:.0f}/100 (level {context['risk']['level']} {context['risk']['label']})",
                "source": "risk model",
                "timestamp": snapshot_at,
            }
        )
        return citations

    # ---------------------------------------------------------------- persist
    def _persist(
        self,
        *,
        session_id: str,
        question: str,
        answer: str,
        model: str | None,
        latency_ms: int,
        grounding: str,
        context: dict[str, Any],
        error: str | None,
    ) -> None:
        try:
            self.repository.add(
                ChatMessage(
                    session_id=session_id,
                    role="user",
                    content=question,
                    created_at=utcnow(),
                    grounding=grounding,
                )
            )
            self.repository.add(
                ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=answer,
                    model=model,
                    created_at=utcnow(),
                    latency_ms=latency_ms,
                    grounding=grounding,
                    error=error,
                    context_snapshot={
                        "risk_score": context["risk"]["score"],
                        "risk_level": context["risk"]["level"],
                        "data_source": context["data_source"],
                        "snapshot_at": context["as_of"],
                    },
                )
            )
            self.session.commit()
        except Exception:  # pragma: no cover - chat persistence must never break chat
            self.session.rollback()
            logger.exception("chat_persist_failed", session_id=session_id)

    # ------------------------------------------------------- suggested prompts
    def suggested_questions(self, device_id: str) -> list[str]:
        try:
            overview = self.analytics.overview(device_id)
        except Exception:  # pragma: no cover
            return [
                "What is the current environmental risk?",
                "Explain the latest sensor readings.",
            ]
        questions: list[str] = []
        risk = overview.get("risk", {})
        if risk.get("level", 1) >= 4:
            questions.append("Why is the current risk level high?")
        else:
            questions.append("What is driving the current risk score?")
        if overview.get("anomalies"):
            questions.append("Why was an anomaly detected?")
        metrics = overview.get("metrics", {})
        if (metrics.get("air_quality_index") or 0) >= 40:
            questions.append("What is happening with the air quality?")
        questions.extend(
            [
                "What is likely to change in the next hour?",
                "Which sensor is currently the biggest concern?",
                "Compare today's humidity with the recent average.",
                "Is the environment becoming safer or more dangerous?",
                "Give me recommendations based on the current readings.",
            ]
        )
        if risk.get("level", 1) <= 2 and not overview.get("anomalies"):
            questions.insert(2, "Has the temperature been increasing today?")
        return questions[:6]

    def history(self, session_id: str) -> dict[str, Any]:
        messages = self.repository.history(session_id, limit=100)
        return {
            "session_id": session_id,
            "count": len(messages),
            "messages": [message.as_dict() for message in messages],
        }

    def clear(self, session_id: str) -> int:
        removed = self.repository.clear_session(session_id)
        self.session.commit()
        return removed

    def diagnostics(self, status: dict[str, Any]) -> dict[str, Any]:
        """Status payload for ``/chat/status`` (never leaks secrets)."""
        return {
            "available": bool(status.get("running") and status.get("model")),
            "host": status.get("host", self.settings.ollama_host),
            "model": status.get("model"),
            "models_available": status.get("models_available", []),
            "installed": bool(status.get("installed")),
            "running": bool(status.get("running")),
            "detail": status.get("detail", ""),
            "context_chars": self.settings.chat_max_context_chars,
            "generated_at": str(datetime.now().astimezone().isoformat()),
        }
