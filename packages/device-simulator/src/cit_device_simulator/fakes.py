"""Original, non-hardware fake adapters for foundation contract verification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from cit_protocol import CommandResult, DeviceCommandIntent, DeviceDescriptor, DeviceEvent
from cit_safety import CommandDisposition, InMemoryCommandLedger


@dataclass(slots=True)
class FakeDeviceAdapter:
    device_id: str
    display_name: str
    device_type: str
    model: str
    adapter_id: str
    capabilities: tuple[str, ...]
    available: bool = True
    connected: bool = field(default=False, init=False)
    _sequence: int = field(default=0, init=False, repr=False)
    _events: list[DeviceEvent] = field(default_factory=list, init=False, repr=False)
    _ledger: InMemoryCommandLedger = field(
        default_factory=InMemoryCommandLedger, init=False, repr=False
    )

    async def detect(self) -> bool:
        return self.available

    def describe(self) -> DeviceDescriptor:
        return DeviceDescriptor.model_validate(
            {
                "deviceId": self.device_id,
                "displayName": self.display_name,
                "deviceType": self.device_type,
                "model": self.model,
                "adapterId": self.adapter_id,
                "adapterVersion": "0.0.0",
                "physical": False,
                "capabilities": list(self.capabilities),
                "safetyProfile": "simulation-only",
            }
        )

    async def connect(self, *, at: datetime) -> None:
        if not self.available:
            raise RuntimeError(f"Fake adapter {self.adapter_id!r} is unavailable")
        self.connected = True
        self._record_event("connection", "connection.connected", {}, at=at)

    async def disconnect(self, *, at: datetime) -> None:
        self.connected = False
        self._record_event("connection", "connection.disconnected", {}, at=at)

    async def execute(self, command: DeviceCommandIntent, *, now: datetime) -> CommandResult:
        if command.deviceId != self.device_id:
            return CommandResult.model_validate(
                {
                    "commandId": command.commandId,
                    "deviceId": self.device_id,
                    "status": "rejected",
                    "message": f"Command targets a different device: {command.deviceId}",
                    "recordedAt": now,
                    "details": {"code": "DEVICE_NOT_FOUND"},
                }
            )
        if not self.connected:
            return CommandResult.model_validate(
                {
                    "commandId": command.commandId,
                    "deviceId": self.device_id,
                    "status": "rejected",
                    "message": "Device adapter is offline",
                    "recordedAt": now,
                    "details": {"code": "DEVICE_OFFLINE"},
                }
            )
        if command.capability not in self.capabilities:
            return CommandResult.model_validate(
                {
                    "commandId": command.commandId,
                    "deviceId": self.device_id,
                    "status": "rejected",
                    "message": f"Unsupported capability: {command.capability}",
                    "recordedAt": now,
                    "details": {"code": "DEVICE_CAPABILITY_UNSUPPORTED"},
                }
            )
        disposition = self._ledger.claim(command, now=now)
        if disposition is CommandDisposition.EXPIRED:
            return CommandResult.model_validate(
                {
                    "commandId": command.commandId,
                    "deviceId": self.device_id,
                    "status": "expired",
                    "message": "Command expiry time has passed",
                    "recordedAt": now,
                    "details": {"code": "COMMAND_EXPIRED"},
                }
            )
        if disposition is CommandDisposition.DUPLICATE:
            return CommandResult.model_validate(
                {
                    "commandId": command.commandId,
                    "deviceId": self.device_id,
                    "status": "duplicate",
                    "message": "Command identity was already executed",
                    "recordedAt": now,
                    "details": {"code": "COMMAND_DUPLICATE"},
                }
            )
        return CommandResult.model_validate(
            {
                "commandId": command.commandId,
                "deviceId": self.device_id,
                "status": "completed",
                "recordedAt": now,
                "details": {
                    "capability": command.capability,
                    "action": command.action,
                },
            }
        )

    async def emit_telemetry(
        self, name: str, values: Mapping[str, Any], *, at: datetime
    ) -> DeviceEvent:
        return self._record_event("telemetry", name, values, at=at)

    async def set_battery(self, percent: int, *, at: datetime) -> DeviceEvent:
        if not any(capability.endswith(".battery") for capability in self.capabilities):
            raise RuntimeError(f"Fake device {self.device_id!r} has no battery capability")
        if not 0 <= percent <= 100:
            raise ValueError("Battery percentage must be between 0 and 100")
        warning = percent <= 20
        name = "telemetry.battery_warning" if warning else "telemetry.battery"
        return await self.emit_telemetry(
            name,
            {"percent": percent, "warning": warning},
            at=at,
        )

    async def emit_sensor(
        self, capability: str, values: Mapping[str, Any], *, at: datetime
    ) -> DeviceEvent:
        if not capability.startswith("sensor.") or capability not in self.capabilities:
            raise RuntimeError(
                f"Fake device {self.device_id!r} does not support sensor {capability!r}"
            )
        return self._record_event("sensor", capability, values, at=at)

    async def stop(self, *, reason: str, at: datetime) -> None:
        self._record_event("safety", "safety.stopped", {"reason": reason}, at=at)

    async def inject_failure(self, failure_kind: str, *, at: datetime) -> None:
        if failure_kind not in {"network", "process"}:
            raise ValueError("Fake failure kind must be 'network' or 'process'")
        await self.stop(reason=f"{failure_kind}-failure", at=at)
        self.connected = False
        self.available = False
        self._record_event(
            "connection",
            "connection.failed",
            {"failureKind": failure_kind},
            at=at,
        )

    async def recover(self, *, at: datetime) -> None:
        self.available = True
        self.connected = False
        self._record_event("connection", "connection.recovered", {}, at=at)

    async def reconcile(self, *, at: datetime) -> DeviceDescriptor:
        if not self.connected:
            raise RuntimeError("Cannot reconcile a disconnected fake adapter")
        descriptor = self.describe()
        self._record_event(
            "diagnostic",
            "diagnostic.reconciled",
            {"capabilities": list(self.capabilities)},
            at=at,
        )
        return descriptor

    def drain_events(self) -> tuple[DeviceEvent, ...]:
        events = tuple(self._events)
        self._events.clear()
        return events

    def _record_event(
        self,
        category: str,
        name: str,
        values: Mapping[str, Any],
        *,
        at: datetime,
    ) -> DeviceEvent:
        self._sequence += 1
        event = DeviceEvent.model_validate(
            {
                "eventId": str(uuid4()),
                "deviceId": self.device_id,
                "sequence": self._sequence,
                "category": category,
                "name": name,
                "values": dict(values),
                "receivedAt": at,
            }
        )
        self._events.append(event)
        return event


def create_fake_s1_adapter() -> FakeDeviceAdapter:
    return FakeDeviceAdapter(
        device_id="fake-s1-main",
        display_name="Fake RoboMaster S1",
        device_type="robot",
        model="robomaster-s1",
        adapter_id="fake-robomaster-s1",
        capabilities=(
            "drive.velocity",
            "drive.stop",
            "gimbal.pitch_yaw",
            "gimbal.stop",
            "led.set",
            "telemetry.battery",
            "telemetry.attitude",
        ),
    )


def create_fake_leap_adapter() -> FakeDeviceAdapter:
    return FakeDeviceAdapter(
        device_id="fake-leap-main",
        display_name="Fake Leap Motion",
        device_type="input",
        model="leap-motion",
        adapter_id="fake-leap-motion",
        capabilities=(
            "input.hand_tracking",
            "input.gesture",
            "telemetry.tracking",
        ),
    )


def create_fake_lego_adapter() -> FakeDeviceAdapter:
    return FakeDeviceAdapter(
        device_id="fake-lego-main",
        display_name="Fake LEGO Hub",
        device_type="robot",
        model="lego-spike",
        adapter_id="fake-lego-pybricks",
        capabilities=(
            "drive.velocity",
            "drive.stop",
            "motor.speed",
            "motor.stop",
            "sensor.distance",
            "sensor.color",
            "hub.battery",
        ),
    )


def create_fake_quest_adapter() -> FakeDeviceAdapter:
    return FakeDeviceAdapter(
        device_id="fake-quest-main",
        display_name="Fake Quest Client",
        device_type="xr_client",
        model="quest-2-baseline",
        adapter_id="fake-quest-gateway",
        capabilities=(
            "input.controller",
            "input.hand_tracking",
            "xr.hud",
            "xr.object",
            "telemetry.battery",
        ),
    )
