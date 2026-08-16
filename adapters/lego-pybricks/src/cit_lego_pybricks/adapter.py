"""The LEGO hub adapter: host-controlled mode (FR-047).

The runtime holds the program and the hub holds the motors. Every student
action becomes one bounded frame, the hub acknowledges it, and telemetry comes
back as ordinary :class:`DeviceEvent` values that the rest of the system already
knows how to route.

What this adapter is *not* allowed to be is a second place where safety is
decided. It clamps in hub units because a percentage is not a fraction and the
conversion has to happen somewhere (FR-053: motor power caps, maximum command
duration), but arming, ownership, expiry, and the speed ceiling itself are all
settled before a command arrives here. The one rule this file owns alone is the
one no other layer can see: host mode and autonomous mode may not both own the
hub (FR-053), because a downloaded program keeps running after the runtime
stops talking.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from cit_protocol import CommandResult, DeviceCommandIntent, DeviceDescriptor, DeviceEvent
from cit_safety import CommandDisposition, InMemoryCommandLedger

from .capabilities import capabilities_for, sensor_port_for
from .diagnostics import (
    HubDiagnostic,
    HubTransportError,
    handshake_timeout,
    link_lost,
    model_mismatch,
)
from .hubs import HubModel, PortKind, decode_ports, hub_model
from .protocol import (
    PROTOCOL_VERSION,
    Frame,
    FrameError,
    Operation,
    decode,
    next_sequence,
    sanitize_text,
)
from .transport import HubTransport

ADAPTER_ID = "lego-pybricks"
ADAPTER_VERSION = "0.1.0"

#: The pseudo-port for readings that belong to the hub rather than to a socket.
HUB_PORT = "HUB"


class HubOwnership(StrEnum):
    """Who is driving the hub. Never both (FR-053)."""

    HOST = "host"
    AUTONOMOUS = "autonomous"


@dataclass(frozen=True, slots=True)
class HubSafetyLimits:
    """Hub-unit bounds. The supervisor's bounds are still applied first."""

    max_motor_percent: int = 75
    max_command_milliseconds: int = 2000
    heartbeat_interval_seconds: float = 0.2
    ack_timeout_seconds: float = 0.5
    handshake_timeout_seconds: float = 3.0

    def __post_init__(self) -> None:
        if not 5 <= self.max_motor_percent <= 100:
            raise ValueError("max_motor_percent must be within [5, 100]")
        if not 100 <= self.max_command_milliseconds <= 5000:
            raise ValueError("max_command_milliseconds must be within [100, 5000]")
        if self.heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds must be positive")
        # The hub stops on its own after this long without a frame, so the host
        # has to speak more often than that. FR-070 gives LEGO 500 ms.
        if self.heartbeat_interval_seconds >= 0.5:
            raise ValueError(
                "heartbeat_interval_seconds must be under the 500 ms LEGO watchdog (FR-070)"
            )


class PybricksHubAdapter:
    """One LEGO hub, addressed by its exact device id."""

    def __init__(
        self,
        *,
        device_id: str,
        display_name: str,
        transport: HubTransport,
        model: HubModel,
        ports: Mapping[str, PortKind],
        limits: HubSafetyLimits | None = None,
        safety_profile: str = "lego-student",
    ) -> None:
        self.device_id = device_id
        self.display_name = display_name
        self.model = model
        self.safety_profile = safety_profile
        self.limits = limits or HubSafetyLimits()
        self.ownership = HubOwnership.HOST
        self._transport = transport
        self._ports: dict[str, PortKind] = dict(ports)
        self.capabilities: tuple[str, ...] = capabilities_for(model, self._ports)
        self._available = True
        self._connected = False
        self._battery_percent: int | None = None
        self._hub_protocol_version: int | None = None
        self._sequence = 0
        self._event_sequence = 0
        self._events: list[DeviceEvent] = []
        self._ledger = InMemoryCommandLedger()
        self._last_heartbeat_at: datetime | None = None
        self._pending_diagnostics: list[str] = []

    # ------------------------------------------------------------- inspection

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def ports(self) -> Mapping[str, PortKind]:
        return dict(self._ports)

    @property
    def battery_percent(self) -> int | None:
        return self._battery_percent

    async def detect(self) -> bool:
        return self._available

    def describe(self) -> DeviceDescriptor:
        return DeviceDescriptor.model_validate(
            {
                "deviceId": self.device_id,
                "displayName": self.display_name,
                "deviceType": "robot",
                "model": self.model.model_id,
                "adapterId": ADAPTER_ID,
                "adapterVersion": ADAPTER_VERSION,
                "physical": True,
                "capabilities": list(self.capabilities),
                "safetyProfile": self.safety_profile,
            }
        )

    # ------------------------------------------------------------- connection

    async def connect(self, *, at: datetime) -> None:
        """Open the link and complete the handshake, or fail with a diagnostic."""

        await self._transport.connect()
        try:
            hello = await self._handshake()
        except HubTransportError:
            await self._transport.disconnect()
            self._available = False
            raise

        reported_model = hello.argument(1)
        if reported_model != self.model.model_id:
            await self._transport.disconnect()
            self._available = False
            raise HubTransportError(model_mismatch(self.model.model_id, reported_model))

        self._connected = True
        self._hub_protocol_version = hello.integer(0)
        self._battery_percent = hello.integer(2)
        self._ports = decode_ports(self.model, hello.argument(3))
        self.capabilities = capabilities_for(self.model, self._ports)
        self._last_heartbeat_at = at
        self._record_event(
            "connection",
            "connection.connected",
            {
                "hubName": self._transport.hub_name,
                "hubModel": self.model.model_id,
                "protocolVersion": self._hub_protocol_version,
                "batteryPercent": self._battery_percent,
                "ports": {port: kind.value for port, kind in sorted(self._ports.items())},
                "minimumFirmware": self.model.minimum_firmware,
            },
            at=at,
        )

    async def disconnect(self, *, at: datetime) -> None:
        """FR-053: leave nothing turning behind."""

        if self._connected:
            await self._send_best_effort(Operation.STOP_ALL, ("disconnect",))
        self._connected = False
        await self._transport.disconnect()
        self._record_event("connection", "connection.disconnected", {}, at=at)

    async def recover(self, *, at: datetime) -> None:
        self._available = True
        self._connected = False
        self._record_event("connection", "connection.recovered", {}, at=at)

    async def reconcile(self, *, at: datetime) -> DeviceDescriptor:
        """FR-087. Ask the hub again rather than trusting what we remember."""

        if not self._connected:
            raise HubTransportError(link_lost(self._transport.hub_name, "not connected"))
        hello = await self._handshake()
        self._battery_percent = hello.integer(2)
        self._ports = decode_ports(self.model, hello.argument(3))
        self.capabilities = capabilities_for(self.model, self._ports)
        descriptor = self.describe()
        self._record_event(
            "diagnostic",
            "diagnostic.reconciled",
            {
                "capabilities": list(self.capabilities),
                "batteryPercent": self._battery_percent,
            },
            at=at,
        )
        return descriptor

    async def _handshake(self) -> Frame:
        frame = self._next_frame(
            Operation.HELLO,
            (str(PROTOCOL_VERSION), "cit-runtime"),
        )
        await self._transport.send_line(frame.encode_line())
        reply = await self._await_frame(
            {Operation.HELLO},
            timeout_seconds=self.limits.handshake_timeout_seconds,
        )
        if reply is None:
            raise HubTransportError(
                handshake_timeout(self._transport.hub_name, self.limits.handshake_timeout_seconds)
            )
        return reply

    # ---------------------------------------------------------------- commands

    async def execute(self, command: DeviceCommandIntent, *, now: datetime) -> CommandResult:
        if command.deviceId != self.device_id:
            return self._reject(
                command,
                "DEVICE_NOT_FOUND",
                f"Command targets a different device: {command.deviceId}",
                now=now,
            )
        if not self._connected:
            return self._reject(
                command,
                "DEVICE_OFFLINE",
                "The LEGO hub is not connected",
                now=now,
            )
        if self.ownership is HubOwnership.AUTONOMOUS:
            return self._reject(
                command,
                "SAFETY_POLICY_DENIED",
                (
                    "This hub is running its own downloaded program. Take it back into "
                    "host mode before sending commands to it."
                ),
                now=now,
            )
        if command.capability not in self.capabilities:
            return self._reject(
                command,
                "DEVICE_CAPABILITY_UNSUPPORTED",
                f"Unsupported capability: {command.capability}",
                now=now,
            )

        disposition = self._ledger.claim(command, now=now)
        if disposition is CommandDisposition.EXPIRED:
            return self._result(command, "expired", now=now, code="COMMAND_EXPIRED")
        if disposition is CommandDisposition.DUPLICATE:
            return self._result(command, "duplicate", now=now, code="COMMAND_DUPLICATE")

        try:
            frame = self._frame_for(command)
        except ValueError as error:
            return self._reject(
                command,
                "DEVICE_CAPABILITY_UNSUPPORTED",
                str(error),
                now=now,
            )

        try:
            await self._transport.send_line(frame.encode_line())
            reply = await self._await_frame(
                {Operation.ACK, Operation.ERROR},
                timeout_seconds=self.limits.ack_timeout_seconds,
                sequence=frame.sequence,
                at=now,
            )
        except HubTransportError as error:
            self._mark_link_lost(error.diagnostic, at=now)
            return self._reject(command, "DEVICE_OFFLINE", error.diagnostic.summary, now=now)

        if reply is None:
            diagnostic = link_lost(
                self._transport.hub_name,
                f"no acknowledgement within {self.limits.ack_timeout_seconds:.1f} s",
            )
            self._mark_link_lost(diagnostic, at=now)
            return self._reject(command, "DEVICE_OFFLINE", diagnostic.summary, now=now)

        if reply.operation is Operation.ERROR:
            return self._reject(
                command,
                "DEVICE_CAPABILITY_UNSUPPORTED",
                f"The hub refused {command.capability!r}: {reply.argument(1)}",
                now=now,
            )

        self._last_heartbeat_at = now
        self._drain_transport(at=now)
        return self._result(
            command,
            "completed",
            now=now,
            details={
                "capability": command.capability,
                "action": command.action,
                "operation": frame.operation.value,
                "arguments": list(frame.arguments),
            },
        )

    async def stop(self, *, reason: str, at: datetime) -> None:
        """Never raises: a stop that can throw is not a stop."""

        await self._send_best_effort(Operation.STOP_ALL, (sanitize_text(reason) or "stop",))
        self._record_event("safety", "safety.stopped", {"reason": reason}, at=at)

    async def emit_telemetry(
        self, name: str, values: Mapping[str, Any], *, at: datetime
    ) -> DeviceEvent:
        return self._record_event("telemetry", name, values, at=at)

    async def tick(self, *, at: datetime) -> tuple[DeviceEvent, ...]:
        """Keep the hub's watchdog fed and turn what it says into events.

        The runtime calls this from the same loop that drives the safety
        watchdogs. Nothing here is a background task: a heartbeat that lives in
        a task of its own keeps a hub alive after the loop that was supposed to
        supervise it has died.
        """

        if not self._connected:
            return ()
        if not self._transport.connected:
            self._mark_link_lost(
                link_lost(self._transport.hub_name, "the transport reported a closed link"),
                at=at,
            )
            return self.drain_events()

        self._drain_transport(at=at)

        last = self._last_heartbeat_at
        due = last is None or (at - last).total_seconds() >= self.limits.heartbeat_interval_seconds
        if due:
            self._last_heartbeat_at = at
            interval_ms = int(self.limits.heartbeat_interval_seconds * 1000)
            await self._send_best_effort(Operation.HEARTBEAT, (str(interval_ms),))
            self._drain_transport(at=at)
        return self.drain_events()

    def drain_events(self) -> tuple[DeviceEvent, ...]:
        events = tuple(self._events)
        self._events.clear()
        return events

    # -------------------------------------------------------------- autonomy

    def take_autonomous_ownership(self, *, instructor_id: str) -> None:
        """FR-048/FR-053. Only an instructor moves the hub out of host mode."""

        if not instructor_id:
            raise PermissionError("Only an instructor may hand a hub its own program")
        self.ownership = HubOwnership.AUTONOMOUS

    def take_host_ownership(self) -> None:
        self.ownership = HubOwnership.HOST

    async def install_program(self, source: str, *, name: str, at: datetime) -> None:
        """Download a compiled program (FR-048). Never part of starting a lesson."""

        if self.ownership is not HubOwnership.AUTONOMOUS:
            raise PermissionError(
                "A hub must be handed to autonomous mode by an instructor before a program "
                "can be installed on it"
            )
        if not self._connected:
            raise HubTransportError(link_lost(self._transport.hub_name, "not connected"))
        await self._send_best_effort(Operation.STOP_ALL, ("program-install",))
        await self._transport.download_program(source, name=name)
        self._record_event(
            "program",
            "program.installed",
            {"program": name, "characters": len(source)},
            at=at,
        )

    # --------------------------------------------------------------- internals

    def _frame_for(self, command: DeviceCommandIntent) -> Frame:
        arguments = dict(command.arguments)
        capability = command.capability

        if capability.startswith("motor."):
            return self._motor_frame(capability, arguments)
        if capability.startswith("drive."):
            return self._drive_frame(capability, arguments)
        if capability.startswith("sensor."):
            return self._sensor_frame(capability)
        if capability == "hub.display":
            text = sanitize_text(str(arguments.get("text", "")))
            return self._next_frame(Operation.DISPLAY, (text or "cit",))
        if capability == "hub.sound":
            frequency = self._integer(arguments, "frequency", default=440, low=50, high=10000)
            milliseconds = self._duration_ms(arguments)
            return self._next_frame(Operation.SOUND, (str(frequency), str(milliseconds)))
        if capability in {"hub.battery", "hub.button"}:
            return self._next_frame(Operation.SENSOR_READ, (HUB_PORT, capability.split(".", 1)[1]))
        raise ValueError(f"{capability!r} has no hub operation")

    def _motor_frame(self, capability: str, arguments: Mapping[str, Any]) -> Frame:
        port = self._motor_port(arguments)
        if capability == "motor.stop":
            return self._next_frame(Operation.MOTOR_STOP, (port,))
        percent = self._motor_percent(arguments)
        if capability in {"motor.run", "motor.run_time"}:
            return self._next_frame(
                Operation.MOTOR_RUN,
                (port, str(percent), str(self._duration_ms(arguments))),
            )
        angle = self._integer(arguments, "angle", default=90, low=-3600, high=3600)
        operation = (
            Operation.MOTOR_RUN_ANGLE
            if capability == "motor.run_angle"
            else Operation.MOTOR_RUN_TARGET
        )
        return self._next_frame(operation, (port, str(angle), str(percent)))

    def _drive_frame(self, capability: str, arguments: Mapping[str, Any]) -> Frame:
        if capability == "drive.stop":
            return self._next_frame(Operation.MOTOR_STOP, ("ALL",))
        percent = self._motor_percent(arguments)
        if capability == "drive.velocity":
            turn = self._integer(arguments, "turnRate", default=0, low=-100, high=100)
            return self._next_frame(
                Operation.DRIVE,
                (str(percent), str(turn), str(self._duration_ms(arguments))),
            )
        if capability == "drive.straight":
            millimetres = self._integer(
                arguments, "distanceMillimetres", default=100, low=-2000, high=2000
            )
            return self._next_frame(Operation.DRIVE_STRAIGHT, (str(millimetres), str(percent)))
        angle = self._integer(arguments, "angle", default=90, low=-720, high=720)
        return self._next_frame(Operation.TURN, (str(angle), str(percent)))

    def _sensor_frame(self, capability: str) -> Frame:
        kind = capability.split(".", 1)[1]
        if kind in {"gyro", "imu"}:
            return self._next_frame(Operation.SENSOR_READ, (HUB_PORT, kind))
        port = sensor_port_for(self._ports, capability)
        if port is None:
            raise ValueError(
                f"No port on this hub reports {capability!r}. Plug the sensor in, then "
                "reconnect the hub so its ports are read again."
            )
        return self._next_frame(Operation.SENSOR_READ, (port, kind))

    def _motor_port(self, arguments: Mapping[str, Any]) -> str:
        raw = arguments.get("port")
        if raw is None:
            motors = [port for port, kind in self._ports.items() if kind is PortKind.MOTOR]
            if len(motors) != 1:
                available = ", ".join(sorted(motors)) or "none"
                raise ValueError(
                    "This block does not say which port the motor is in. "
                    f"Motor ports on this hub: {available}."
                )
            return motors[0]
        port = str(raw).upper()
        if port == "ALL":
            return port
        if not self.model.has_port(port):
            raise ValueError(
                f"{self.model.display_name} has no port {port}. "
                f"Ports: {', '.join(self.model.ports)}."
            )
        if self._ports.get(port) is not PortKind.MOTOR:
            found = self._ports.get(port, PortKind.EMPTY).value
            raise ValueError(
                f"Port {port} has no motor in it (the hub reports {found}). "
                "Plug the motor in, then reconnect the hub."
            )
        return port

    def _motor_percent(self, arguments: Mapping[str, Any]) -> int:
        """Normalized speed in, hub percent out, clamped to the hub ceiling."""

        raw = arguments.get("speed", 0.0)
        try:
            speed = float(raw)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Speed {raw!r} is not a number") from error
        percent = round(max(-1.0, min(1.0, speed)) * 100)
        ceiling = self.limits.max_motor_percent
        return max(-ceiling, min(ceiling, percent))

    def _duration_ms(self, arguments: Mapping[str, Any]) -> int:
        raw = arguments.get("durationSeconds")
        if raw is None:
            return self.limits.max_command_milliseconds
        try:
            seconds = float(raw)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Duration {raw!r} is not a number") from error
        milliseconds = round(abs(seconds) * 1000)
        # An unbounded movement is not permitted to exist (FR-053), so zero
        # means "the shortest step this hub takes", not "forever".
        return max(1, min(self.limits.max_command_milliseconds, milliseconds))

    @staticmethod
    def _integer(
        arguments: Mapping[str, Any], name: str, *, default: int, low: int, high: int
    ) -> int:
        raw = arguments.get(name, default)
        try:
            value = round(float(raw))
        except (TypeError, ValueError) as error:
            raise ValueError(f"{name} {raw!r} is not a number") from error
        return max(low, min(high, value))

    def _next_frame(self, operation: Operation, arguments: tuple[str, ...]) -> Frame:
        self._sequence = next_sequence(self._sequence)
        return Frame(sequence=self._sequence, operation=operation, arguments=arguments)

    async def _send_best_effort(self, operation: Operation, arguments: tuple[str, ...]) -> None:
        frame = self._next_frame(operation, arguments)
        try:
            await self._transport.send_line(frame.encode_line())
        except HubTransportError:
            # A hub that cannot be reached has already stopped on its own
            # watchdog. Raising here would turn one dead hub into a failed
            # stop-all for every other device in the room.
            self._connected = False

    async def _await_frame(
        self,
        operations: set[Operation],
        *,
        timeout_seconds: float,
        sequence: int | None = None,
        at: datetime | None = None,
    ) -> Frame | None:
        """Wait for one reply, turning anything else the hub says into events.

        A batch is processed to the end even after the reply is found. A hub
        answers ``SENSOR_READ`` with an ``ACK`` and then the reading, both in the
        same notification, and returning at the ``ACK`` would drop the reading
        the student asked for.
        """

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        while True:
            matched: Frame | None = None
            for frame in self._read_frames():
                if (
                    matched is None
                    and frame.operation in operations
                    and (sequence is None or frame.integer(0) == sequence)
                ):
                    matched = frame
                    continue
                self._queue_unsolicited(frame, at=at)
            if matched is not None:
                return matched
            if loop.time() >= deadline:
                return None
            await asyncio.sleep(0.005)

    def _read_frames(self) -> tuple[Frame, ...]:
        frames: list[Frame] = []
        for line in self._transport.drain_lines():
            try:
                frames.append(decode(line))
            except FrameError as error:
                self._pending_diagnostics.append(str(error))
        return tuple(frames)

    def _drain_transport(self, *, at: datetime) -> None:
        for frame in self._read_frames():
            self._queue_unsolicited(frame, at=at)
        for message in self._pending_diagnostics:
            self._record_event("diagnostic", "diagnostic.bad_frame", {"reason": message}, at=at)
        self._pending_diagnostics.clear()

    def _queue_unsolicited(self, frame: Frame, *, at: datetime | None = None) -> None:
        moment = at or self._last_heartbeat_at
        if moment is None:
            return
        if frame.operation is Operation.TELEMETRY:
            kind = frame.argument(0)
            values: dict[str, Any] = {"value": _numeric(frame.argument(1))}
            if len(frame.arguments) > 2:
                values["unit"] = frame.argument(2)
            if kind == "button":
                # FR-053: the button on the hub is a stop control, so it is a
                # safety event, not a sensor reading.
                self._record_event(
                    "safety",
                    "safety.hub_button",
                    {"button": frame.argument(1)},
                    at=moment,
                )
                return
            category = "telemetry" if kind == "battery" else "sensor"
            self._record_event(category, f"{category}.{kind}", values, at=moment)
        elif frame.operation is Operation.ERROR:
            self._record_event(
                "diagnostic",
                "diagnostic.hub_error",
                {"code": frame.argument(1), "sequence": frame.argument(0)},
                at=moment,
            )

    def _mark_link_lost(self, diagnostic: HubDiagnostic, *, at: datetime) -> None:
        self._connected = False
        self._available = False
        self._record_event(
            "connection",
            "connection.failed",
            {"code": diagnostic.code, "reason": diagnostic.detail},
            at=at,
        )

    def _record_event(
        self,
        category: str,
        name: str,
        values: Mapping[str, Any],
        *,
        at: datetime,
    ) -> DeviceEvent:
        self._event_sequence += 1
        event = DeviceEvent.model_validate(
            {
                "eventId": str(uuid4()),
                "deviceId": self.device_id,
                "sequence": self._event_sequence,
                "category": category,
                "name": name,
                "values": dict(values),
                "receivedAt": at,
            }
        )
        self._events.append(event)
        return event

    def _result(
        self,
        command: DeviceCommandIntent,
        status: str,
        *,
        now: datetime,
        code: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> CommandResult:
        payload: dict[str, Any] = {
            "commandId": command.commandId,
            "deviceId": self.device_id,
            "status": status,
            "recordedAt": now,
        }
        combined: dict[str, Any] = dict(details or {})
        if code is not None:
            combined["code"] = code
        if combined:
            payload["details"] = combined
        return CommandResult.model_validate(payload)

    def _reject(
        self,
        command: DeviceCommandIntent,
        code: str,
        message: str,
        *,
        now: datetime,
    ) -> CommandResult:
        return CommandResult.model_validate(
            {
                "commandId": command.commandId,
                "deviceId": self.device_id,
                "status": "rejected",
                "message": message[:500],
                "recordedAt": now,
                "details": {"code": code},
            }
        )


def _numeric(raw: str) -> float | int | str:
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def build_adapter(
    *,
    device_id: str,
    display_name: str,
    transport: HubTransport,
    model_id: str,
    ports: Mapping[str, PortKind],
    limits: HubSafetyLimits | None = None,
    safety_profile: str = "lego-student",
) -> PybricksHubAdapter:
    """Convenience constructor that resolves the hub model by id."""

    return PybricksHubAdapter(
        device_id=device_id,
        display_name=display_name,
        transport=transport,
        model=hub_model(model_id),
        ports=ports,
        limits=limits,
        safety_profile=safety_profile,
    )
