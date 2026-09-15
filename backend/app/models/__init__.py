"""ORM models.

The persistence layer is intentionally narrow: one wide reading table for the
time series plus small tables for alerts, devices, prediction snapshots and chat
history. Wide-and-simple beats a normalised EAV schema for this data volume and
keeps aggregation queries readable.
"""

from .alert import Alert
from .chat import ChatMessage
from .device import Device
from .prediction import PredictionRecord
from .reading import SensorReading

__all__ = ["Alert", "ChatMessage", "Device", "PredictionRecord", "SensorReading"]
