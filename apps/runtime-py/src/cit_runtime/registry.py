"""Device registry and discovery.

FR-004 stores what the runtime knows about a device; FR-005 defines how devices
arrive. Discovery is an interface with a configured/fake provider now so that
M2's S1, M4's LEGO, and M5's Quest providers plug in without touching callers.

FR-019 is enforced here by construction: lookup is by exact ``deviceId`` only.
There is no lookup by family, display-name substring, proximity, or last use.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from cit_device_simulator import DeviceAdapter
from cit_protocol import DeviceDescriptor


class DeviceConnectionState(StrEnum):
    DISCOVERED = "discovered"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RegisteredDevice:
    """A descriptor plus the runtime-owned state the UI renders (UI 11.3)."""

    descriptor: DeviceDescriptor
    state: DeviceConnectionState
    discovered_at: datetime
    last_seen_at: datetime
    assigned_session_id: str | None = None
    failure_reason: str | None = None

    @property
    def device_id(self) -> str:
        return self.descriptor.deviceId

    @property
    def physical(self) -> bool:
        return self.descriptor.physical


class DiscoveryProvider(Protocol):
    """FR-005. Hardware providers land in M2/M4/M5 behind this same shape."""

    provider_id: str

    async def discover(self) -> Sequence[DeviceAdapter]: ...


class ConfiguredDiscoveryProvider:
    """Yields a fixed adapter set: the simulation-first default (FR-062)."""

    provider_id = "configured"

    def __init__(self, adapters: Iterable[DeviceAdapter]) -> None:
        self._adapters = tuple(adapters)

    async def discover(self) -> Sequence[DeviceAdapter]:
        return self._adapters


class DeviceAssignmentError(RuntimeError):
    pass


class DeviceRegistry:
    """Holds adapters and their runtime state. Sends no commands itself."""

    def __init__(self) -> None:
        self._devices: dict[str, RegisteredDevice] = {}
        self._adapters: dict[str, DeviceAdapter] = {}

    async def discover_from(self, provider: DiscoveryProvider, *, at: datetime) -> tuple[str, ...]:
        found: list[str] = []
        for adapter in await provider.discover():
            if not await adapter.detect():
                continue
            descriptor = adapter.describe()
            self._adapters[descriptor.deviceId] = adapter
            existing = self._devices.get(descriptor.deviceId)
            if existing is None:
                self._devices[descriptor.deviceId] = RegisteredDevice(
                    descriptor=descriptor,
                    state=DeviceConnectionState.DISCOVERED,
                    discovered_at=at,
                    last_seen_at=at,
                )
            else:
                self._devices[descriptor.deviceId] = replace(
                    existing, descriptor=descriptor, last_seen_at=at
                )
            found.append(descriptor.deviceId)
        return tuple(found)

    def get(self, device_id: str) -> RegisteredDevice:
        try:
            return self._devices[device_id]
        except KeyError as error:
            raise KeyError(f"Unknown device {device_id!r}") from error

    def adapter(self, device_id: str) -> DeviceAdapter:
        try:
            return self._adapters[device_id]
        except KeyError as error:
            raise KeyError(f"Unknown device {device_id!r}") from error

    def list(self) -> tuple[RegisteredDevice, ...]:
        return tuple(self._devices[key] for key in sorted(self._devices))

    def physical_device_ids(self) -> tuple[str, ...]:
        return tuple(device.device_id for device in self.list() if device.physical)

    async def connect(self, device_id: str, *, at: datetime) -> RegisteredDevice:
        device = self.get(device_id)
        adapter = self.adapter(device_id)
        self._devices[device_id] = replace(device, state=DeviceConnectionState.CONNECTING)
        try:
            await adapter.connect(at=at)
        except Exception as error:
            self._devices[device_id] = replace(
                device,
                state=DeviceConnectionState.FAILED,
                last_seen_at=at,
                failure_reason=str(error),
            )
            raise
        updated = replace(
            device,
            state=DeviceConnectionState.CONNECTED,
            last_seen_at=at,
            failure_reason=None,
        )
        self._devices[device_id] = updated
        return updated

    async def disconnect(self, device_id: str, *, at: datetime) -> RegisteredDevice:
        device = self.get(device_id)
        await self.adapter(device_id).disconnect(at=at)
        updated = replace(device, state=DeviceConnectionState.DISCONNECTED, last_seen_at=at)
        self._devices[device_id] = updated
        return updated

    async def reconcile(self, device_id: str, *, at: datetime) -> RegisteredDevice:
        """FR-087. Refresh capabilities after an adapter reconnects."""

        descriptor = await self.adapter(device_id).reconcile(at=at)
        updated = replace(self.get(device_id), descriptor=descriptor, last_seen_at=at)
        self._devices[device_id] = updated
        return updated

    def mark_failed(self, device_id: str, *, reason: str, at: datetime) -> RegisteredDevice:
        updated = replace(
            self.get(device_id),
            state=DeviceConnectionState.FAILED,
            failure_reason=reason,
            last_seen_at=at,
        )
        self._devices[device_id] = updated
        return updated

    # ----------------------------------------------------------- assignment

    def assign(self, device_id: str, *, session_id: str) -> RegisteredDevice:
        """FR-006. One session at a time; reassignment must be explicit."""

        device = self.get(device_id)
        if device.assigned_session_id not in (None, session_id):
            raise DeviceAssignmentError(
                f"Device {device_id!r} is already assigned to session "
                f"{device.assigned_session_id!r}"
            )
        updated = replace(device, assigned_session_id=session_id)
        self._devices[device_id] = updated
        return updated

    def release(self, device_id: str) -> RegisteredDevice:
        updated = replace(self.get(device_id), assigned_session_id=None)
        self._devices[device_id] = updated
        return updated

    def release_session(self, session_id: str) -> tuple[str, ...]:
        released: list[str] = []
        for device in self.list():
            if device.assigned_session_id == session_id:
                self.release(device.device_id)
                released.append(device.device_id)
        return tuple(released)
