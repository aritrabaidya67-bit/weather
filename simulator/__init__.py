"""Simulation package.

``environment_model`` holds the physics and is imported by both the standalone
simulator process and the backend's built-in demo mode, guaranteeing that
simulated data traverses the same ingestion pipeline as physical hardware.
"""

from .environment_model import (  # noqa: F401
    SCENARIOS,
    EnvironmentSimulator,
    EnvironmentState,
    SensorFaultConfig,
)

__all__ = ["EnvironmentSimulator", "EnvironmentState", "SensorFaultConfig", "SCENARIOS"]
