"""Process-local device lease primitives for the Milestone 0 contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4


class LeaseMode(StrEnum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True, slots=True)
class DeviceLease:
    lease_id: UUID
    device_id: str
    session_id: str
    mode: LeaseMode
    acquired_at: datetime
    expires_at: datetime


class DeviceLeaseConflict(RuntimeError):
    def __init__(self, *, device_id: str, holder_session_id: str) -> None:
        self.device_id = device_id
        self.holder_session_id = holder_session_id
        super().__init__(
            f"Device {device_id!r} already has a write lease held by session {holder_session_id!r}"
        )


class InMemoryDeviceLeaseRegistry:
    """Tracks foundation-only leases without dispatching device commands."""

    def __init__(self) -> None:
        self._leases: dict[UUID, DeviceLease] = {}

    def acquire(
        self,
        *,
        device_id: str,
        session_id: str,
        mode: LeaseMode,
        now: datetime,
        ttl: timedelta,
    ) -> DeviceLease:
        self._leases = {
            lease_id: lease for lease_id, lease in self._leases.items() if lease.expires_at > now
        }
        if mode is LeaseMode.WRITE:
            for lease in self._leases.values():
                if lease.device_id == device_id and lease.mode is LeaseMode.WRITE:
                    raise DeviceLeaseConflict(
                        device_id=device_id,
                        holder_session_id=lease.session_id,
                    )

        lease = DeviceLease(
            lease_id=uuid4(),
            device_id=device_id,
            session_id=session_id,
            mode=mode,
            acquired_at=now,
            expires_at=now + ttl,
        )
        self._leases[lease.lease_id] = lease
        return lease
