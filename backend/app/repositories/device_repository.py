"""Persistence queries for registered devices."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Device


class DeviceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, device_id: str) -> Device | None:
        return self.session.get(Device, device_id)

    def get_or_create(self, device_id: str, **defaults) -> Device:
        device = self.get(device_id)
        if device is None:
            device = Device(device_id=device_id, **defaults)
            self.session.add(device)
            self.session.flush()
        return device

    def list(self) -> list[Device]:
        return list(
            self.session.execute(select(Device).order_by(Device.last_seen_at.desc())).scalars().all()
        )

    def primary(self, fallback_id: str) -> Device | None:
        device = self.get(fallback_id)
        if device is not None:
            return device
        devices = self.list()
        return devices[0] if devices else None

    def commit(self) -> None:
        self.session.commit()
