"""Background scheduler.

Four periodic jobs, all cheap and all guarded so a failure in one never impacts
the request path:

1. **offline watchdog** - flags devices that stopped sending and raises an alert.
2. **prediction snapshots** - generates and stores forecasts every N minutes
   (deliberately *not* on every ingested reading: the LLM and the statistical
   models are never invoked per-sample).
3. **forecast evaluation** - scores stored forecasts against the readings that
   actually arrived, so the platform can report its own accuracy.
4. **retention** - prunes old readings/predictions/alerts.

A lightweight status heartbeat is also published on the realtime bus so the
dashboard notices a silent backend.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from ..core.config import get_settings
from ..core.database import session_scope
from ..core.logging import get_logger
from ..core.realtime import bus
from ..utils.timeutils import utcnow

logger = get_logger("app.background")


class BackgroundScheduler:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.tasks: list[asyncio.Task[None]] = []
        self._stop = asyncio.Event()
        self.last_runs: dict[str, str] = {}
        self.counters: dict[str, int] = {
            "offline_events": 0,
            "prediction_snapshots": 0,
            "predictions_evaluated": 0,
            "pruned_readings": 0,
        }
        self._last_ollama_state: bool | None = None

    async def start(self) -> None:
        if not self.settings.background_workers_enabled:
            logger.info("background_workers_disabled")
            return
        self._stop.clear()
        self.tasks = [
            asyncio.create_task(self._watchdog_loop(), name="device-watchdog"),
            asyncio.create_task(self._prediction_loop(), name="prediction-snapshots"),
            asyncio.create_task(self._retention_loop(), name="retention"),
            asyncio.create_task(self._heartbeat_loop(), name="status-heartbeat"),
            asyncio.create_task(self._ollama_loop(), name="ollama-probe"),
        ]
        logger.info("background_workers_started", jobs=len(self.tasks))

    async def stop(self) -> None:
        self._stop.set()
        for task in self.tasks:
            task.cancel()
        for task in self.tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown must not raise
                pass
        self.tasks = []
        logger.info("background_workers_stopped")

    # ------------------------------------------------------------------- loops
    async def _sleep(self, seconds: float) -> bool:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
            return False  # stop requested
        except asyncio.TimeoutError:
            return True

    async def _watchdog_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self._watchdog_tick)
            except Exception:  # noqa: BLE001
                logger.exception("watchdog_tick_failed")
            if not await self._sleep(5.0):
                return

    async def _prediction_loop(self) -> None:
        # give the API a moment to come up before the first snapshot
        if not await self._sleep(20.0):
            return
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self._prediction_tick)
            except Exception:  # noqa: BLE001
                logger.exception("prediction_tick_failed")
            if not await self._sleep(self.settings.prediction_snapshot_interval_minutes * 60):
                return

    async def _retention_loop(self) -> None:
        if not await self._sleep(300.0):
            return
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self._retention_tick)
            except Exception:  # noqa: BLE001
                logger.exception("retention_tick_failed")
            if not await self._sleep(3600.0):
                return

    async def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            try:
                bus.publish(
                    "system",
                    {
                        "message": "heartbeat",
                        "server_time": utcnow().isoformat(),
                        "subscribers": bus.subscriber_count,
                        "background": self.counters,
                    },
                )
            except Exception:  # noqa: BLE001
                logger.exception("heartbeat_failed")
            if not await self._sleep(15.0):
                return

    async def _ollama_loop(self) -> None:
        """Keep the Ollama availability snapshot warm so /status and /chat/status
        answer instantly instead of blocking on a network probe."""
        while not self._stop.is_set():
            try:
                from .ollama_client import get_ollama_client

                status = await get_ollama_client().status(refresh=True)
                available = bool(status.running and status.selected_model)
                if self._last_ollama_state != available:
                    self._last_ollama_state = available
                    logger.info(
                        "ollama_availability_changed",
                        available=available,
                        model=status.selected_model,
                        detail=status.detail[:160],
                    )
                    bus.publish(
                        "system",
                        {
                            "message": "Ollama availability changed",
                            "ollama_available": available,
                            "model": status.selected_model,
                            "detail": status.detail,
                        },
                    )
                self.last_runs["ollama_probe"] = utcnow().isoformat()
            except Exception:  # noqa: BLE001
                logger.exception("ollama_probe_failed")
            if not await self._sleep(60.0):
                return

    # ------------------------------------------------------------------- ticks
    def _watchdog_tick(self) -> None:
        from .alert_service import AlertService
        from .device_service import DeviceService

        with session_scope() as session:
            device_service = DeviceService(session)
            alert_service = AlertService(session)
            for transition in device_service.offline_transitions():
                alert = alert_service.raise_device_offline(
                    transition["device_id"], transition.get("age_seconds")
                )
                if alert:
                    self.counters["offline_events"] += 1
        self.last_runs["watchdog"] = utcnow().isoformat()

    def _prediction_tick(self) -> None:
        from .prediction_service import PredictionService

        device_id = None
        with session_scope() as session:
            from .device_service import DeviceService

            device_id = DeviceService(session).primary_device_id()
        with session_scope() as session:
            service = PredictionService(session)
            result = service.forecast(device_id, persist=True)
            if result.get("data_sufficient"):
                self.counters["prediction_snapshots"] += 1
            evaluated = service.evaluate_pending()
            self.counters["predictions_evaluated"] += evaluated
            bus.publish(
                "prediction",
                {
                    "device_id": device_id,
                    "generated_at": result.get("generated_at"),
                    "primary_horizon_minutes": result.get("primary_horizon_minutes"),
                    "risk": result.get("risk"),
                    "summary": result.get("summary", [])[:3],
                    "data_sufficient": result.get("data_sufficient"),
                },
            )
        self.last_runs["predictions"] = utcnow().isoformat()

    def _retention_tick(self) -> None:
        from ..repositories import ReadingRepository

        cutoff = utcnow() - timedelta(days=self.settings.retention_days)
        with session_scope() as session:
            removed = ReadingRepository(session).delete_older_than(cutoff)
            self.counters["pruned_readings"] += removed
        if removed:
            logger.info("retention_pruned", readings=removed, cutoff=cutoff.isoformat())
        self.last_runs["retention"] = utcnow().isoformat()

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.settings.background_workers_enabled,
            "jobs": [task.get_name() for task in self.tasks],
            "last_runs": dict(self.last_runs),
            "counters": dict(self.counters),
        }


scheduler = BackgroundScheduler()
