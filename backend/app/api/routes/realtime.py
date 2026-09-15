"""Realtime endpoints (WebSocket with a Server-Sent Events fallback).

Topics: ``reading``, ``risk``, ``anomaly``, ``alert``, ``prediction``, ``device``,
``system``. Both transports replay recent events so a client that reconnects (or
an SSE client sending ``Last-Event-ID``) does not miss anything important.
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any, AsyncIterator

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from ...core.logging import get_logger
from ...core.realtime import TOPICS, bus
from ..deps import ReadAccessDep

logger = get_logger("app.api.realtime")
router = APIRouter(prefix="/realtime", tags=["realtime"])


def _parse_topics(raw: str | None) -> list[str]:
    if not raw:
        return list(TOPICS)
    requested = [item.strip() for item in raw.split(",") if item.strip()]
    valid = [topic for topic in requested if topic in TOPICS]
    return valid or list(TOPICS)


@router.get("/status", summary="Realtime bus status")
def status(_: ReadAccessDep) -> dict[str, Any]:
    return {
        "subscribers": bus.subscriber_count,
        "topics": list(TOPICS),
        "last_event_id": bus.last_event_id(),
        "buffered_events": sum(1 for _ in bus.iter_history()),
        "websocket_url": "/api/v1/realtime/ws",
        "sse_url": "/api/v1/realtime/events",
    }


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    topics = _parse_topics(websocket.query_params.get("topics"))
    try:
        last_event_id = int(websocket.query_params.get("last_event_id") or 0)
    except ValueError:
        last_event_id = 0
    await websocket.accept()
    logger.info("websocket_connected", topics=topics, client=str(websocket.client))
    try:
        await websocket.send_json(
            {
                "topic": "system",
                "data": {"message": "connected", "topics": topics},
                "id": bus.last_event_id(),
            }
        )
        for event in bus.history(topics, after_id=last_event_id):
            await websocket.send_json(event.to_message())

        async with bus.subscribe() as queue:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    await websocket.send_json({"topic": "system", "data": {"message": "ping"}})
                    continue
                if event.topic in topics:
                    await websocket.send_json(event.to_message())
    except WebSocketDisconnect:
        logger.info("websocket_disconnected", topics=topics)
    except Exception as exc:  # noqa: BLE001 - a broken socket must not spam the logs as an error
        # The type and message are logged at warning level (a dropped client is
        # routine); the full traceback goes to debug so a real defect is still
        # diagnosable without flooding production logs.
        logger.warning("websocket_error", topics=topics, error_type=type(exc).__name__, error=str(exc))
        logger.debug("websocket_error_detail", topics=topics, exc_info=True)


@router.get("/events", summary="Server-Sent Events stream (fallback for the WebSocket)")
async def events(
    request: Request,
    _: ReadAccessDep,
    topics: Annotated[str | None, Query(description="Comma separated topic list")] = None,
    last_event_id: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[
        int,
        Query(
            ge=0,
            le=100,
            description="Close the stream after N events (0 = stream until the client disconnects)",
        ),
    ] = 0,
) -> Any:
    selected = _parse_topics(topics)
    header_id = request.headers.get("last-event-id")
    if header_id:
        try:
            last_event_id = max(last_event_id, int(header_id))
        except ValueError:
            pass

    async def generator() -> AsyncIterator[bytes]:
        sent = 0
        yield b": connected\n\n"
        for event in bus.history(selected, after_id=last_event_id):
            yield _sse(event.to_message())
            sent += 1
            if limit and sent >= limit:
                return
        async with bus.subscribe() as queue:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield b": keep-alive\n\n"
                    continue
                if event.topic in selected:
                    yield _sse(event.to_message())
                    sent += 1
                    if limit and sent >= limit:
                        return

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(message: dict[str, Any]) -> bytes:
    payload = json.dumps(message.get("data", {}), default=str)
    return (
        f"id: {message.get('id')}\nevent: {message.get('topic')}\ndata: {payload}\n\n"
    ).encode("utf-8")
