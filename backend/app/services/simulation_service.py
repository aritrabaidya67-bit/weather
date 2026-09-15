"""Built-in demo mode.

When ``SIMULATION_MODE=true`` the backend generates readings itself using the very
same environmental model as the standalone simulator (``simulator/environment_model.py``)
and pushes each payload through ``SensorService.ingest`` - the identical
pipeline used for real Arduino data. Nothing is faked at the API or database
layer: rows are stored with ``source="simulation"``, the UI labels them as
simulated, and an informational alert is raised to make the mode obvious.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.database import session_scope
from ..core.logging import get_logger
from ..core.realtime import bus
from ..schemas import SensorPayload
from .sensor_service import IngestionRejected, SensorService

logger = get_logger("app.simulation")


def _load_model():
    """Import the shared simulation model, tolerating either sys.path layout."""
    try:
        from simulator.environment_model import EnvironmentSimulator, SCENARIOS
    except ImportError:  # running from inside backend/ with a different sys.path
        project_root = Path(__file__).resolve().parents[3]
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from simulator.environment_model import EnvironmentSimulator, SCENARIOS

    return EnvironmentSimulator, SCENARIOS


class SimulationRunner:
    """Background task that feeds simulated readings into the real pipeline."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.task: asyncio.Task[None] | None = None
        self.simulator: Any = None
        self.generated = 0
        self.rejected = 0
        self._stop = asyncio.Event()

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    async def start(self) -> None:
        if self.running:
            return
        EnvironmentSimulator, _ = _load_model()
        self.simulator = EnvironmentSimulator(
            self.settings.simulation_scenario,
            seed=self.settings.simulation_seed,
            device_id=self.settings.simulation_device_id,
            transmission_interval_ms=int(self.settings.simulation_interval_seconds * 1000),
            speed=self.settings.simulation_speed,
        )
        self._stop.clear()
        self.task = asyncio.create_task(self._loop(), name="simulation-runner")
        logger.info(
            "simulation_mode_started",
            scenario=self.settings.simulation_scenario,
            device_id=self.settings.simulation_device_id,
            interval_seconds=self.settings.simulation_interval_seconds,
        )
        bus.publish(
            "system",
            {
                "message": "Simulation mode started",
                "scenario": self.settings.simulation_scenario,
                "device_id": self.settings.simulation_device_id,
            },
        )

    async def stop(self) -> None:
        self._stop.set()
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown must not raise
                pass
            self.task = None
        logger.info("simulation_mode_stopped", generated=self.generated, rejected=self.rejected)

    async def _loop(self) -> None:
        interval = max(0.25, self.settings.simulation_interval_seconds)
        while not self._stop.is_set():
            started = asyncio.get_event_loop().time()
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a simulator hiccup must not kill the API
                logger.exception("simulation_tick_failed")
            elapsed = asyncio.get_event_loop().time() - started
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=max(0.0, interval - elapsed))
            except asyncio.TimeoutError:
                continue

    async def _tick(self) -> None:
        assert self.simulator is not None
        payload_dict = self.simulator.step(dt_seconds=self.settings.simulation_interval_seconds)
        try:
            parsed = SensorPayload.model_validate(payload_dict)
        except Exception as exc:  # noqa: BLE001 - simulation bug, report and continue
            logger.error("simulation_payload_invalid", error=str(exc))
            return

        def _ingest() -> dict[str, Any]:
            with session_scope() as session:
                return SensorService(session).ingest(
                    parsed, raw_body=payload_dict, source_override="simulation"
                )

        try:
            result = await asyncio.to_thread(_ingest)
            self.generated += 1
            if self.generated % 20 == 0:
                logger.info(
                    "simulation_progress",
                    generated=self.generated,
                    risk_level=result.get("risk_level"),
                    risk_score=result.get("risk_score"),
                )
        except IngestionRejected as exc:
            self.rejected += 1
            logger.warning("simulation_payload_rejected", detail=exc.detail)
        except Exception:  # noqa: BLE001
            logger.exception("simulation_ingest_failed")

    def status(self) -> dict[str, Any]:
        _, SCENARIOS = _load_model()
        return {
            "enabled": self.settings.simulation_mode,
            "running": self.running,
            "scenario": self.settings.simulation_scenario,
            "scenario_label": SCENARIOS.get(
                self.settings.simulation_scenario, {}
            ).get("label", "unknown"),
            "device_id": self.settings.simulation_device_id,
            "interval_seconds": self.settings.simulation_interval_seconds,
            "speed": self.settings.simulation_speed,
            "generated": self.generated,
            "rejected": self.rejected,
            "scenarios": [{"key": key, "label": value["label"]} for key, value in SCENARIOS.items()],
        }


runner = SimulationRunner()
