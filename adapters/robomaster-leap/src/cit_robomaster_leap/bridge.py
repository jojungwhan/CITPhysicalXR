"""Authenticated Fabric adapter client and deterministic command handler."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

from cit_protocol import (
    AdapterAuthenticationFrame,
    AdapterCommandLifecycleFrame,
    AdapterEventFrame,
    AdapterHeartbeatFrame,
    AdapterRegistrationFrame,
    FabricCommandLifecycleEvent,
    FabricResolvedCommand,
    HealthReport,
    to_wire,
)
from websockets.asyncio.client import connect
from websockets.typing import Origin

from .backend import (
    GestureSignal,
    RobotBackend,
    VendorLeapProcess,
    VendorProcessError,
    demo_gesture_signals,
    validate_velocity_parameters,
)
from .contract import (
    GESTURE_CAPABILITY,
    ROBOT_STOP_CAPABILITY,
    ROBOT_TELEMETRY_CAPABILITY,
    ROBOT_VELOCITY_CAPABILITY,
    build_manifest,
    build_nodes,
)


class AdapterSocket(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...


@dataclass(frozen=True, slots=True)
class BridgeConfiguration:
    adapter_url: str
    adapter_token: str = field(repr=False)
    fabric_origin: str
    session_id: str
    site_id: str
    room_id: str
    host_id: str
    leap_node_id: str
    robot_node_id: str
    activation_file: Path
    input_mode: str
    robot_mode: str
    preferred_hand: str


@dataclass(frozen=True, slots=True)
class CommandExecution:
    duplicate: bool
    details: Mapping[str, object]


class RobotCommandHandler:
    """Fail-closed adapter-level validation and duplicate suppression."""

    def __init__(self, backend: RobotBackend, *, robot_node_id: str) -> None:
        self._backend = backend
        self._robot_node_id = robot_node_id
        self._seen_command_ids: set[str] = set()

    def has_seen(self, command_id: str) -> bool:
        return command_id in self._seen_command_ids

    def validate(self, command: FabricResolvedCommand) -> None:
        if command.targetNodeId != self._robot_node_id:
            raise ValueError("Command target is not this RoboMaster node")
        if command.expiresAt <= datetime.now(UTC):
            raise ValueError("Command expired before adapter execution")
        parameters = command.parameters.model_dump(mode="json")
        if command.action == ROBOT_STOP_CAPABILITY:
            if parameters:
                raise ValueError("Ground-robot stop does not accept parameters")
            return
        if command.action == ROBOT_VELOCITY_CAPABILITY:
            validate_velocity_parameters(parameters)
            return
        raise ValueError(f"Unsupported RoboMaster action {command.action!r}")

    async def execute(self, command: FabricResolvedCommand) -> CommandExecution:
        command_id = str(command.commandId)
        if command_id in self._seen_command_ids:
            return CommandExecution(duplicate=True, details={"duplicatePrevented": True})
        self.validate(command)
        parameters = command.parameters.model_dump(mode="json")
        if command.action == ROBOT_STOP_CAPABILITY:
            if parameters:
                raise ValueError("Ground-robot stop does not accept parameters")
            await self._backend.stop(reason="fabric_command")
            details: Mapping[str, object] = {"stopped": True}
        elif command.action == ROBOT_VELOCITY_CAPABILITY:
            forward, right, clockwise = validate_velocity_parameters(parameters)
            details = await self._backend.set_velocity(
                forward=forward,
                right=right,
                clockwise=clockwise,
                idempotency_key=command.idempotencyKey,
            )
        else:
            raise ValueError(f"Unsupported RoboMaster action {command.action!r}")
        self._seen_command_ids.add(command_id)
        return CommandExecution(duplicate=False, details=details)


class FabricRobotLeapBridge:
    def __init__(
        self,
        configuration: BridgeConfiguration,
        *,
        robot: RobotBackend,
        leap: VendorLeapProcess | None,
    ) -> None:
        if configuration.input_mode not in {"demo", "leap"}:
            raise ValueError("input_mode must be 'demo' or 'leap'")
        if configuration.input_mode == "leap" and leap is None:
            raise ValueError("Physical Leap input requires a Leap process")
        self.configuration = configuration
        self._robot = robot
        self._leap = leap
        self._handler = RobotCommandHandler(robot, robot_node_id=configuration.robot_node_id)
        self._send_lock = asyncio.Lock()
        base_sequence = time.time_ns()
        self._sequences = {
            configuration.leap_node_id: base_sequence,
            configuration.robot_node_id: base_sequence,
        }
        self._last_error: str | None = None

    async def run(self) -> None:
        await self._robot.start()
        try:
            async with connect(
                self.configuration.adapter_url,
                origin=Origin(self.configuration.fabric_origin),
                max_size=131_072,
                open_timeout=10,
                close_timeout=3,
            ) as raw_socket:
                socket = cast(AdapterSocket, raw_socket)
                await self._authenticate_and_register(socket)
                tasks = (
                    asyncio.create_task(self._receive(socket), name="fabric-receive"),
                    asyncio.create_task(self._heartbeat(socket), name="fabric-heartbeat"),
                    asyncio.create_task(self._publish_input(socket), name="leap-input"),
                )
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    task.result()
        finally:
            await self._robot.stop(reason="fabric_bridge_shutdown")
            if self._leap is not None:
                await self._leap.close()
            await self._robot.close()

    async def _authenticate_and_register(self, socket: AdapterSocket) -> None:
        now = datetime.now(UTC)
        authentication = AdapterAuthenticationFrame.model_validate(
            {
                "frameType": "adapter.authenticate",
                "frameId": str(uuid4()),
                "protocolVersion": 1,
                "credential": self.configuration.adapter_token,
                "sentAt": now,
            }
        )
        await self._send(socket, authentication)
        welcome = await self._receive_json(socket)
        if welcome.get("frameType") != "adapter.welcome":
            raise RuntimeError("Fabric did not accept adapter authentication")
        leap_node, robot_node = build_nodes(
            at=datetime.now(UTC),
            host_id=self.configuration.host_id,
            site_id=self.configuration.site_id,
            room_id=self.configuration.room_id,
            leap_node_id=self.configuration.leap_node_id,
            robot_node_id=self.configuration.robot_node_id,
            leap_simulated=self.configuration.input_mode == "demo",
            robot_simulated=self.configuration.robot_mode == "dry-run",
            robot_mode=self.configuration.robot_mode,
            preferred_hand=self.configuration.preferred_hand,
        )
        registration = AdapterRegistrationFrame.model_validate(
            {
                "frameType": "adapter.register",
                "frameId": str(uuid4()),
                "protocolVersion": 1,
                "manifest": build_manifest().model_dump(mode="json", exclude_none=True),
                "nodes": [
                    leap_node.model_dump(mode="json", exclude_none=True),
                    robot_node.model_dump(mode="json", exclude_none=True),
                ],
                "sentAt": datetime.now(UTC),
            }
        )
        await self._send(socket, registration)
        registered = await self._receive_json(socket)
        if registered.get("frameType") != "adapter.registered":
            raise RuntimeError("Fabric did not accept RoboMaster/Leap registration")
        expected = {self.configuration.leap_node_id, self.configuration.robot_node_id}
        received = set(registered.get("registeredNodeIds", []))
        if received != expected:
            raise RuntimeError("Fabric registered a different node set")

    async def _receive(self, socket: AdapterSocket) -> None:
        while True:
            frame = await self._receive_json(socket)
            frame_type = frame.get("frameType")
            if frame_type == "adapter.ack":
                continue
            if frame_type == "adapter.stop":
                await self._robot.stop(reason=str(frame.get("reason", "fabric_stop")))
                continue
            if frame_type != "adapter.command":
                raise RuntimeError(f"Unexpected Fabric adapter frame {frame_type!r}")
            command = FabricResolvedCommand.model_validate(frame.get("command"))
            await self._handle_command(socket, command)

    async def _handle_command(
        self,
        socket: AdapterSocket,
        command: FabricResolvedCommand,
    ) -> None:
        if self._handler.has_seen(str(command.commandId)):
            return
        await asyncio.sleep(0)
        try:
            self._handler.validate(command)
        except ValueError as error:
            self._last_error = str(error)[:500]
            await self._lifecycle(
                socket,
                command,
                "REJECTED",
                code="ADAPTER_PARAMETER_REJECTED",
                message=self._last_error,
            )
            return
        try:
            await self._lifecycle(socket, command, "ACCEPTED")
            await self._lifecycle(socket, command, "RUNNING")
            execution = await self._handler.execute(command)
            await self._lifecycle(
                socket,
                command,
                "SUCCEEDED",
                details=dict(execution.details),
            )
            if command.action == ROBOT_VELOCITY_CAPABILITY:
                await self._publish_robot_telemetry(socket, command, execution.details)
        except ValueError as error:
            self._last_error = str(error)[:500]
            await self._lifecycle(
                socket,
                command,
                "FAILED",
                code="ADAPTER_PARAMETER_REJECTED",
                message=self._last_error,
            )
        except VendorProcessError as error:
            self._last_error = str(error)[:500]
            await self._robot.stop(reason="vendor_process_failure")
            await self._lifecycle(
                socket,
                command,
                "FAILED",
                code="VENDOR_PROCESS_FAILED",
                message=self._last_error,
            )

    async def _publish_input(self, socket: AdapterSocket) -> None:
        # The signal comes from another process creating an exact sentinel file;
        # an asyncio.Event cannot observe that cross-process state.
        while not self.configuration.activation_file.is_file():  # noqa: ASYNC110
            await asyncio.sleep(0.1)
        if self.configuration.input_mode == "demo":
            for signal in demo_gesture_signals():
                await self._publish_gesture(socket, signal)
                await asyncio.sleep(0.25)
            while self.configuration.activation_file.is_file():  # noqa: ASYNC110
                await asyncio.sleep(0.25)
            return
        leap = self._leap
        if leap is None:
            raise RuntimeError("Leap process is unavailable")
        async for signal in leap.events():
            if not self.configuration.activation_file.is_file():
                return
            await self._publish_gesture(socket, signal)

    async def _publish_gesture(self, socket: AdapterSocket, signal: GestureSignal) -> None:
        now = datetime.now(UTC)
        frame = AdapterEventFrame.model_validate(
            {
                "frameType": "adapter.event",
                "frameId": str(uuid4()),
                "protocolVersion": 1,
                "event": {
                    "messageId": str(uuid4()),
                    "schemaVersion": "1.0",
                    "messageType": "event",
                    "topic": GESTURE_CAPABILITY,
                    "sourceNodeId": self.configuration.leap_node_id,
                    "sourceCapability": GESTURE_CAPABILITY,
                    "siteId": self.configuration.site_id,
                    "roomId": self.configuration.room_id,
                    "sessionId": self.configuration.session_id,
                    "timestamp": now,
                    "monotonicTimestamp": time.monotonic_ns(),
                    "sequence": self._next_sequence(self.configuration.leap_node_id),
                    "correlationId": str(uuid4()),
                    "confidence": signal.confidence,
                    "ttlMs": 250,
                    "dataClassification": "operational",
                    "payload": {
                        "forwardMetersPerSecond": signal.forward_meters_per_second,
                        "rightMetersPerSecond": signal.right_meters_per_second,
                        "clockwiseRadiansPerSecond": signal.clockwise_radians_per_second,
                        "state": signal.state,
                        "reason": signal.reason,
                        "tracking": signal.tracking,
                        "vendorSequence": signal.sequence,
                    },
                },
                "sentAt": now,
            }
        )
        await self._send(socket, frame)

    async def _publish_robot_telemetry(
        self,
        socket: AdapterSocket,
        command: FabricResolvedCommand,
        details: Mapping[str, object],
    ) -> None:
        now = datetime.now(UTC)
        bounded = details.get("bounded")
        payload = (
            bounded if isinstance(bounded, dict) else command.parameters.model_dump(mode="json")
        )
        frame = AdapterEventFrame.model_validate(
            {
                "frameType": "adapter.event",
                "frameId": str(uuid4()),
                "protocolVersion": 1,
                "event": {
                    "messageId": str(uuid4()),
                    "schemaVersion": "1.0",
                    "messageType": "event",
                    "topic": ROBOT_TELEMETRY_CAPABILITY,
                    "sourceNodeId": self.configuration.robot_node_id,
                    "sourceCapability": ROBOT_TELEMETRY_CAPABILITY,
                    "siteId": self.configuration.site_id,
                    "roomId": self.configuration.room_id,
                    "sessionId": self.configuration.session_id,
                    "timestamp": now,
                    "monotonicTimestamp": time.monotonic_ns(),
                    "sequence": self._next_sequence(self.configuration.robot_node_id),
                    "correlationId": command.correlationId,
                    "causationId": str(command.commandId),
                    "confidence": 1.0,
                    "ttlMs": 2_000,
                    "dataClassification": "operational",
                    "payload": payload,
                },
                "sentAt": now,
            }
        )
        await self._send(socket, frame)

    async def _heartbeat(self, socket: AdapterSocket) -> None:
        while True:
            await asyncio.sleep(5)
            now = datetime.now(UTC)
            healthy = self._last_error is None
            reports = [
                HealthReport.model_validate(
                    {
                        "schemaVersion": "1.0",
                        "nodeId": node_id,
                        "reportedAt": now,
                        "connectionState": "connected" if healthy else "degraded",
                        "healthState": "healthy" if healthy else "degraded",
                        "message": self._last_error,
                        "metrics": {
                            "inputActive": self.configuration.activation_file.is_file(),
                            "upstreamWatchdogMilliseconds": 200,
                        },
                    }
                )
                for node_id in (
                    self.configuration.leap_node_id,
                    self.configuration.robot_node_id,
                )
            ]
            frame = AdapterHeartbeatFrame.model_validate(
                {
                    "frameType": "adapter.heartbeat",
                    "frameId": str(uuid4()),
                    "protocolVersion": 1,
                    "reports": [
                        report.model_dump(mode="json", exclude_none=True) for report in reports
                    ],
                    "sentAt": now,
                }
            )
            await self._send(socket, frame)

    async def _lifecycle(
        self,
        socket: AdapterSocket,
        command: FabricResolvedCommand,
        stage: str,
        *,
        code: str | None = None,
        message: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        now = datetime.now(UTC)
        lifecycle = FabricCommandLifecycleEvent.model_validate(
            {
                "messageId": str(uuid4()),
                "schemaVersion": "1.0",
                "messageType": "command.lifecycle",
                "commandId": command.commandId,
                "requestMessageId": command.requestMessageId,
                "sessionId": command.sessionId,
                "targetNodeId": command.targetNodeId,
                "stage": stage,
                "occurredAt": now,
                "correlationId": command.correlationId,
                "code": code,
                "message": message,
                "details": dict(details or {}),
            }
        )
        frame = AdapterCommandLifecycleFrame.model_validate(
            {
                "frameType": "adapter.command_lifecycle",
                "frameId": str(uuid4()),
                "protocolVersion": 1,
                "lifecycle": lifecycle.model_dump(mode="json", exclude_none=True),
                "sentAt": now,
            }
        )
        await self._send(socket, frame)

    async def _send(self, socket: AdapterSocket, model: Any) -> None:
        payload = json.dumps(to_wire(model), separators=(",", ":"))
        async with self._send_lock:
            await socket.send(payload)

    @staticmethod
    async def _receive_json(socket: AdapterSocket) -> dict[str, Any]:
        raw = await socket.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        value: object = json.loads(raw)
        if not isinstance(value, dict):
            raise RuntimeError("Fabric frame must be an object")
        return value

    def _next_sequence(self, node_id: str) -> int:
        self._sequences[node_id] += 1
        return self._sequences[node_id]
