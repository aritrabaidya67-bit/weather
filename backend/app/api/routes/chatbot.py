"""Chatbot endpoints.

The browser only ever talks to these routes; the Ollama host/port is never
exposed. Every answer is grounded in a structured snapshot of the platform's own
data, and the response tells the client whether the LLM or the built-in
rule-based analyst produced it.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from fastapi.responses import StreamingResponse

from ...core.config import get_settings
from ...core.database import session_scope
from ...core.logging import get_logger
from ...core.security import client_identity, get_chat_limiter, get_chat_status_limiter
from ...schemas import (
    ChatHistoryResponse,
    ChatRequest,
    ChatResponse,
    ChatStatusResponse,
    SuggestedQuestionsResponse,
)
from ..deps import ChatOwnerDep, SessionDep, resolve_device_id
from ..services import ChatbotService, get_ollama_client


def _enforce_chat_status_budget(request: Request) -> None:
    """Rate-limit the moderately expensive chat support endpoints."""
    limiter = get_chat_status_limiter()
    allowed, retry_after = limiter.check(client_identity(request))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait a moment.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )

logger = get_logger("app.api.chat")
router = APIRouter(prefix="/chat", tags=["chatbot"])


def _session_id(request: ChatRequest) -> str:
    return request.session_id or f"chat-{uuid.uuid4().hex[:12]}"


@router.get("/status", response_model=ChatStatusResponse, summary="Ollama availability and detected model")
async def chat_status(request: Request, session: SessionDep) -> Any:
    _enforce_chat_status_budget(request)
    client = get_ollama_client()
    status_snapshot = await client.status(refresh=True)
    return ChatbotService(session, client=client).diagnostics(status_snapshot.as_dict())


@router.post("", response_model=ChatResponse, summary="Ask a question about the environment data")
async def chat(session: SessionDep, request: ChatRequest, http_request: Request, _: ChatOwnerDep) -> Any:
    limiter = get_chat_limiter()
    allowed, retry_after = limiter.check(client_identity(http_request))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many chat requests. Please wait a moment.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    device_id = resolve_device_id(session, request.device_id)
    # The client is resolved here (not inside the service) so tests and future
    # transport changes can inject a different model backend.
    service = ChatbotService(session, client=get_ollama_client())
    result = await service.answer(
        device_id=device_id,
        message=request.message,
        session_id=_session_id(request),
        history=[turn.model_dump() for turn in request.history],
    )
    logger.info(
        "chat_answered",
        session_id=result["session_id"],
        model=result.get("model"),
        fallback=result["fallback_used"],
        latency_ms=result["latency_ms"],
    )
    return result


@router.post(
    "/stream",
    summary="Streaming chat answer (Server-Sent Events style NDJSON)",
    response_class=StreamingResponse,
)
async def chat_stream(request: ChatRequest, http_request: Request, _: ChatOwnerDep) -> Any:
    limiter = get_chat_limiter()
    allowed, retry_after = limiter.check(client_identity(http_request))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many chat requests. Please wait a moment.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    # All database work happens before streaming starts: FastAPI tears down
    # request-scoped dependencies before a StreamingResponse body is consumed.
    with session_scope() as session:
        device_id = resolve_device_id(session, request.device_id)
        service = ChatbotService(session, client=get_ollama_client())
        messages, context = service.prepare(
            device_id, request.message, [turn.model_dump() for turn in request.history]
        )
    session_id = _session_id(request)

    async def generator() -> AsyncIterator[bytes]:
        try:
            async for chunk in service.stream(
                message=request.message,
                session_id=session_id,
                messages=messages,
                context=context,
            ):
                yield (json.dumps(chunk, default=str) + "\n").encode("utf-8")
        except Exception as exc:  # noqa: BLE001 - the stream must terminate cleanly
            logger.exception("chat_stream_failed")
            yield (
                json.dumps({"type": "error", "detail": str(exc), "session_id": session_id}) + "\n"
            ).encode("utf-8")
        finally:
            yield (json.dumps({"type": "done", "session_id": session_id}) + "\n").encode("utf-8")

    return StreamingResponse(
        generator(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/suggestions", response_model=SuggestedQuestionsResponse, summary="Context-aware suggested questions")
def suggestions(
    request: Request,
    session: SessionDep,
    _: ChatOwnerDep,
    device_id: str | None = None,
) -> Any:
    _enforce_chat_status_budget(request)
    resolved = resolve_device_id(session, device_id)
    return {
        "questions": ChatbotService(session).suggested_questions(resolved),
        "generated_from": "current data snapshot",
    }


@router.get(
    "/history/{session_id}",
    response_model=ChatHistoryResponse,
    summary="Stored conversation",
    description=(
        "Requires a valid device or admin API key. Chat transcripts are operator data: "
        "knowing a session id alone is not authorization."
    ),
)
def history(
    request: Request,
    session: SessionDep,
    _: ChatOwnerDep,
    session_id: str = Path(max_length=64),
) -> Any:
    return ChatbotService(session).history(session_id)


@router.delete(
    "/history/{session_id}",
    summary="Clear a stored conversation",
    description="State-mutating operation: requires a valid device or admin API key.",
)
def clear(
    request: Request,
    session: SessionDep,
    _: ChatOwnerDep,
    session_id: str = Path(max_length=64),
) -> dict[str, Any]:
    removed = ChatbotService(session).clear(session_id)
    return {"success": True, "session_id": session_id, "deleted_messages": removed}


@router.get(
    "/context/{device_id}",
    summary="The exact structured context sent to the model (debugging)",
    description="Requires a valid device or admin API key: this is the full platform data snapshot.",
)
def context(
    request: Request,
    session: SessionDep,
    _: ChatOwnerDep,
    device_id: str = Path(min_length=3, max_length=64),
) -> dict[str, Any]:
    _enforce_chat_status_budget(request)
    service = ChatbotService(session)
    snapshot = service.build_context(device_id)
    settings = get_settings()
    text = service.context_json(snapshot)
    return {
        "device_id": device_id,
        "context_chars": len(text),
        "context_limit": settings.chat_max_context_chars,
        "snapshot": snapshot,
        "notes": [
            "This is exactly what the model receives as its data source; the model is instructed "
            "never to introduce values that are not present here."
        ],
    }
