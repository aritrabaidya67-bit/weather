"""In-process realtime event bus.

Sensor ingestion publishes events here; the WebSocket and Server-Sent Events
endpoints fan them out to browsers. The bus keeps a small ring buffer per topic
so a client that reconnects (or an SSE client using ``Last-Event-ID``) can catch
up on what it missed instead of showing a stale dashboard.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, AsyncIterator, Iterator

from .logging import get_logger

logger = get_logger("app.realtime")

TOPICS = (
    "reading",
    "risk",
    "anomaly",
    "alert",
    "prediction",
    "device",
    "system",
)


@dataclass(slots=True)
class Event:
    topic: str
    payload: dict[str, Any]
    event_id: int
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_message(self) -> dict[str, Any]:
        return {
            "id": self.event_id,
            "topic": self.topic,
            "timestamp": self.created_at.isoformat(),
            "data": self.payload,
        }


class EventBus:
    def __init__(self, history_size: int = 200, queue_size: int = 100) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._history: dict[str, deque[Event]] = {
            topic: deque(maxlen=history_size) for topic in TOPICS
        }
        self._counter = 0
        self._queue_size = queue_size
        self._lock = asyncio.Lock()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, topic: str, payload: dict[str, Any]) -> Event:
        """Publish an event. Safe to call from worker threads and async code."""
        self._counter += 1
        event = Event(topic=topic, payload=payload, event_id=self._counter)
        if topic in self._history:
            self._history[topic].append(event)
        subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Slow consumer: drop the oldest event rather than stalling ingestion.
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except Exception:  # pragma: no cover - defensive
                    pass
        return event

    def history(self, topics: list[str], after_id: int = 0) -> list[Event]:
        events: list[Event] = []
        for topic in topics:
            for event in self._history.get(topic, ()):
                if event.event_id > after_id:
                    events.append(event)
        events.sort(key=lambda e: e.event_id)
        return events

    def last_event_id(self) -> int:
        return self._counter

    async def subscribe(self) -> AsyncIterator[asyncio.Queue[Event]]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._queue_size)
        async with self._lock:
            self._subscribers.add(queue)
        logger.debug("realtime_client_connected", subscribers=len(self._subscribers))
        try:
            yield queue
        finally:
            async with self._lock:
                self._subscribers.discard(queue)
            logger.debug("realtime_client_disconnected", subscribers=len(self._subscribers))

    def iter_history(self) -> Iterator[Event]:
        for topic in TOPICS:
            yield from self._history[topic]


bus = EventBus()


def publish_reading(payload: dict[str, Any]) -> None:
    bus.publish("reading", payload)


def publish_system(message: str, **fields: Any) -> None:
    bus.publish("system", {"message": message, **fields})
