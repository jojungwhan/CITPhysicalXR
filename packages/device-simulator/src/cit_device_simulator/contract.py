"""The hardware-neutral device adapter boundary established in Milestone 0."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from cit_protocol import CommandResult, DeviceCommandIntent, DeviceDescriptor, DeviceEvent


@runtime_checkable
class DeviceAdapter(Protocol):
    """Contract all fake and future subprocess/network adapters must satisfy."""

    device_id: str
    capabilities: tuple[str, ...]

    async def detect(self) -> bool: ...

    def describe(self) -> DeviceDescriptor: ...

    async def connect(self, *, at: datetime) -> None: ...

    async def disconnect(self, *, at: datetime) -> None: ...

    async def execute(self, command: DeviceCommandIntent, *, now: datetime) -> CommandResult: ...

    async def emit_telemetry(
        self, name: str, values: Mapping[str, Any], *, at: datetime
    ) -> DeviceEvent: ...

    async def stop(self, *, reason: str, at: datetime) -> None: ...

    async def recover(self, *, at: datetime) -> None: ...

    async def reconcile(self, *, at: datetime) -> DeviceDescriptor: ...

    def drain_events(self) -> tuple[DeviceEvent, ...]: ...
