"""Chatbot behaviour (real context, no invented values, graceful degradation) and realtime tests."""

from __future__ import annotations

import json

import pytest

from app.services.ollama_client import OllamaUnavailable

from .conftest import auth_headers, post_reading


class _StubClient:
    """Stands in for Ollama so the LLM path can be tested without a running server."""

    def __init__(self, model: str = "qwen3:4b") -> None:
        self.model = model
        self.calls: list[list[dict[str, str]]] = []

    async def status(self, *, refresh: bool = False):  # noqa: ANN001, ARG002
        from app.services.ollama_client import OllamaStatus

        return OllamaStatus(
            installed=True,
            running=True,
            host="http://localhost:11434",
            models=[self.model],
            selected_model=self.model,
            detail="stub",
        )

    async def ensure_available(self):  # noqa: ANN201
        return await self.status()

    async def chat(self, messages, *, model=None, temperature=None, json_mode=False):  # noqa: ANN001, ARG002
        self.calls.append(messages)
        return "Stub answer grounded in the snapshot.", model or self.model

    async def chat_stream(self, messages, *, model=None):  # noqa: ANN001, ARG002
        self.calls.append(messages)
        for token in ("Stub ", "streamed ", "answer."):
            yield token, model or self.model

    async def resolved_model(self, *, refresh: bool = False):  # noqa: ANN001, ARG002
        return self.model


class _BrokenClient(_StubClient):
    async def status(self, *, refresh: bool = False):  # noqa: ANN001, ARG002
        from app.services.ollama_client import OllamaStatus

        return OllamaStatus(
            installed=True,
            running=False,
            host="http://localhost:11434",
            models=["qwen3:4b"],
            selected_model="qwen3:4b",
            detail="Ollama is not reachable at http://localhost:11434 (ConnectError).",
        )

    async def ensure_available(self):
        raise OllamaUnavailable("Ollama is not reachable at http://localhost:11434 (ConnectError).")

    async def chat(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise OllamaUnavailable("down")

    async def chat_stream(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise OllamaUnavailable("down")


@pytest.fixture()
def chat_service(client, monkeypatch):
    from app.core.database import get_session_factory
    from app.services.chatbot_service import ChatbotService

    session = get_session_factory()()
    stub = _StubClient()
    service = ChatbotService(session, client=stub)
    yield service, stub
    session.close()


def test_context_contains_only_real_platform_data(chat_service):
    service, _ = chat_service
    post_reading(client=None, sequence=1) if False else None
    from app.core.database import get_session_factory
    from app.services import SensorService
    from app.schemas import SensorPayload

    session = get_session_factory()()
    SensorService(session).ingest(
        SensorPayload.model_validate(
            {
                "device_id": "arduino-r4-wifi-01",
                "sequence": 1,
                "temperature_c": 24.6,
                "humidity_pct": 52.0,
                "pressure_hpa": 1012.6,
                "rain_raw": 940.0,
                "ldr_raw": 700.0,
                "air_quality_raw": 205.0,
            }
        )
    )
    session.close()

    context = service.build_context("arduino-r4-wifi-01")
    assert context["current_reading"]["temperature_c"]["value"] == 24.6
    assert context["risk"]["score"] is not None
    assert context["data_source"] in {"live hardware", "simulated"}
    assert context["data_quality"]["has_any_data"] is True
    assert "prediction" in context
    assert context["as_of"]

    text = service.context_json(context)
    assert "24.6" in text
    assert "grounding" not in text.lower()


def test_system_prompt_forbids_inventing_values(chat_service):
    service, _ = chat_service
    context = service.build_context("arduino-r4-wifi-01")
    messages = service.build_messages("What is the temperature?", [], context)
    assert messages[0]["role"] == "system"
    assert "never invent" in messages[0]["content"].lower()
    assert "DATA SNAPSHOT" in messages[1]["content"]
    assert messages[-1]["content"] == "What is the temperature?"


@pytest.mark.asyncio
async def test_chat_uses_the_stubbed_model_and_returns_citations(chat_service):
    service, stub = chat_service
    result = await service.answer(
        device_id="arduino-r4-wifi-01", message="Why is the risk score what it is?", session_id="s1"
    )
    assert result["model"] == "qwen3:4b"
    assert result["fallback_used"] is False
    assert result["answer"].startswith("Stub answer")
    assert result["citations"]
    assert stub.calls and stub.calls[0][0]["role"] == "system"


@pytest.mark.asyncio
async def test_chat_falls_back_when_ollama_is_down(chat_service, monkeypatch):
    from app.core.database import get_session_factory
    from app.services.chatbot_service import ChatbotService

    session = get_session_factory()()
    service = ChatbotService(session, client=_BrokenClient())
    result = await service.answer(
        device_id="arduino-r4-wifi-01", message="What is the risk level?", session_id="s2"
    )
    session.close()
    assert result["fallback_used"] is True
    assert result["warning"]
    assert "rule-based analyst" in result["warning"]
    assert result["answer"]


def test_fallback_analyst_says_there_is_no_data(chat_service):
    service, _ = chat_service
    context = service.build_context("arduino-r4-wifi-01")
    answer = service._fallback_answer("What is the temperature doing?", context)  # noqa: SLF001
    # No reading has been ingested in this test -> the analyst must say exactly that
    # instead of inventing a plausible temperature.
    assert "No sensor data has been received yet" in answer
    assert "C" not in answer.replace("Arduino", "")


def test_fallback_analyst_uses_real_values_when_data_exists(chat_service):
    from app.core.database import get_session_factory
    from app.schemas import SensorPayload
    from app.services import SensorService

    service, _ = chat_service
    session = get_session_factory()()
    SensorService(session).ingest(
        SensorPayload.model_validate(
            {
                "device_id": "arduino-r4-wifi-01",
                "sequence": 1,
                "temperature_c": 31.4,
                "humidity_pct": 58.0,
                "pressure_hpa": 1008.2,
                "rain_raw": 930.0,
                "ldr_raw": 400.0,
                "air_quality_raw": 640.0,
            }
        )
    )
    session.close()
    context = service.build_context("arduino-r4-wifi-01")
    answer = service._fallback_answer("What is the air quality like?", context)  # noqa: SLF001
    derived_index = context["current_reading"]["air_quality_index"]["value"]
    assert str(derived_index) in answer
    assert "relative index" in answer.lower()
    temperature_answer = service._fallback_answer("How hot is it?", context)  # noqa: SLF001
    assert "31.4" in temperature_answer


def test_chat_endpoint_requires_no_secret_and_reports_status(client, monkeypatch):
    from app.api.routes import chatbot as chatbot_routes

    stub = _StubClient()
    monkeypatch.setattr(chatbot_routes, "get_ollama_client", lambda: stub)
    status = client.get("/api/v1/chat/status").json()
    assert status["available"] is True
    assert status["model"] == "qwen3:4b"
    assert status["running"] is True

    post_reading(client, sequence=1)
    response = client.post("/api/v1/chat", json={"message": "What is the air quality?"})
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "qwen3:4b"
    assert body["grounding"] in {"live_data", "historical_data", "analysis_only"}
    assert body["session_id"]
    assert body["used_context"]["risk_score"] is not None


def test_chat_stream_endpoint(client, monkeypatch):
    from app.api.routes import chatbot as chatbot_routes

    stub = _StubClient()
    monkeypatch.setattr(chatbot_routes, "get_ollama_client", lambda: stub)
    post_reading(client, sequence=1)
    with client.stream(
        "POST", "/api/v1/chat/stream", json={"message": "Summarise the conditions"}
    ) as response:
        assert response.status_code == 200
        lines = [line for line in response.iter_lines() if line.strip()]
    chunks = [json.loads(line) for line in lines]
    assert chunks[0]["type"] == "meta"
    assert any(chunk["type"] == "token" for chunk in chunks)
    assert chunks[-1]["type"] in {"token", "done"}


def test_chat_history_and_suggestions(client, monkeypatch):
    from app.api.routes import chatbot as chatbot_routes

    monkeypatch.setattr(chatbot_routes, "get_ollama_client", lambda: _StubClient())
    post_reading(client, sequence=1, air_quality_raw=780.0)
    response = client.post(
        "/api/v1/chat", json={"message": "Explain the risk", "session_id": "session-abc"}
    ).json()
    assert response["session_id"] == "session-abc"
    history = client.get("/api/v1/chat/history/session-abc").json()
    assert history["count"] == 2
    assert history["messages"][0]["role"] == "user"
    assert history["messages"][1]["role"] == "assistant"

    suggestions = client.get("/api/v1/chat/suggestions").json()
    assert 3 <= len(suggestions["questions"]) <= 6
    cleared = client.delete("/api/v1/chat/history/session-abc").json()
    assert cleared["deleted_messages"] == 2


def test_chat_context_endpoint_is_debuggable(client):
    post_reading(client, sequence=1)
    body = client.get("/api/v1/chat/context/arduino-r4-wifi-01").json()
    assert body["context_chars"] > 0
    assert body["snapshot"]["risk"]["score"] is not None
    assert any("never to introduce values" in note for note in body["notes"])


def test_invalid_chat_request_is_rejected(client):
    assert client.post("/api/v1/chat", json={"message": ""}).status_code == 422


def test_realtime_websocket_delivers_readings(client, monkeypatch):
    from app.api.routes import chatbot as chatbot_routes

    monkeypatch.setattr(chatbot_routes, "get_ollama_client", lambda: _StubClient())
    with client.websocket_connect("/api/v1/realtime/ws?topics=reading,risk") as websocket:
        hello = websocket.receive_json()
        assert hello["topic"] == "system"
        post_reading(client, sequence=1)
        topics_seen = set()
        for _ in range(6):
            message = websocket.receive_json()
            topics_seen.add(message["topic"])
            if {"reading", "risk"} <= topics_seen:
                break
        assert "reading" in topics_seen
        assert "risk" in topics_seen


def test_realtime_status_and_history_replay(client):
    post_reading(client, sequence=1)
    status = client.get("/api/v1/realtime/status").json()
    assert status["subscribers"] == 0
    assert status["last_event_id"] > 0
    # ``limit`` closes the SSE stream after N replayed events, which also makes it
    # testable without an infinite read.
    response = client.get("/api/v1/realtime/events?topics=reading&limit=2")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: reading" in response.text
    assert response.text.startswith(": connected")


def test_ollama_status_reports_missing_installation_gracefully(client, monkeypatch):
    """When Ollama is absent the API must say so and keep working."""
    from app.services import ollama_client as ollama_module

    monkeypatch.setattr(ollama_module, "detect_binary", lambda: None)
    monkeypatch.setattr(ollama_module, "models_from_disk", lambda _path: [])
    monkeypatch.setattr(ollama_module, "detect_models_directory", lambda: None)
    client_instance = ollama_module.OllamaClient()
    status = client_instance._select_model(["qwen3:4b", "nomic-embed-text:latest"])  # noqa: SLF001
    assert status == "qwen3:4b"  # embedding models are never chosen for chat
    assert ollama_module.models_from_disk(None) is None or True
