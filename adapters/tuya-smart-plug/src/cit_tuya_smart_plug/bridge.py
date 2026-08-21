"""Authenticated Fabric client for one allowlisted smart-plug node."""

from __future__ import annotations

import asyncio
import json
import logging
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

from .backend import SmartPlugBackend, SmartPlugError
from .contract import (
    POWER_SET_CAPABILITY,
    POWER_STATE_CAPABILITY,
    build_manifest,
    build_node,
)

LOGGER = logging.getLogger(__name__)


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
    node_id: str
    activation_file: Path
    simulated: bool
    vendor_brand: str
    model: str
    protocol_version: str
    switch_dps: int
    device_address: str | None
    poll_interval_seconds: float = 5.0


@dataclass(frozen=True, slots=True)
class CommandExecution:
    duplicate: bool
    state: bool


class SmartPlugCommandHandler:
    """Validate one exact command shape and suppress duplicate execution."""

    def __init__(self, backend: SmartPlugBackend, *, node_id: str) -> None:
        self._backend = backend
        self._node_id = node_id
        self._seen_command_ids: set[str] = set()

    def has_seen(self, command_id: str) -> bool:
        return command_id in self._seen_command_ids

    def validate(self, command: FabricResolvedCommand) -> bool:
        if command.targetNodeId != self._node_id:
            raise ValueError("Command target is not this smart-plug node")
        if command.expiresAt <= datetime.now(UTC):
            raise ValueError("Command expired before adapter execution")
        if command.action != POWER_SET_CAPABILITY:
            raise ValueError(f"Unsupported smart-plug action {command.action!r}")
        parameters = command.parameters.model_dump(mode="json")
        if set(parameters) != {"on"} or type(parameters.get("on")) is not bool:
            raise ValueError("Smart-plug command requires exactly one boolean 'on' parameter")
        return cast(bool, parameters["on"])

    async def execute(self, command: FabricResolvedCommand) -> CommandExecution:
        command_id = str(command.commandId)
        if command_id in self._seen_command_ids:
            return CommandExecution(duplicate=True, state=await self._backend.read_state())
        on = self.validate(command)
        state = await self._backend.set_power(on)
        self._seen_command_ids.add(command_id)
        return CommandExecution(duplicate=False, state=state)


class FabricSmartPlugBridge:
    def __init__(
        self,
        configuration: BridgeConfiguration,
        *,
        backend: SmartPlugBackend,
    ) -> None:
        if configuration.vendor_brand not in {"tuya", "gosund"}:
            raise ValueError("vendor_brand must be 'tuya' or 'gosund'")
        if configuration.poll_interval_seconds < 1:
            raise ValueError("poll_interval_seconds must be at least one second")
        self.configuration = configuration
        self._backend = backend
        self._handler = SmartPlugCommandHandler(backend, node_id=configuration.node_id)
        self._send_lock = asyncio.Lock()
        self._sequence = time.time_ns()
        self._last_state: bool | None = None
        self._last_error: str | None = None

    async def run(self) -> None:
        started = False
        try:
            self._last_state = await self._backend.start()
            started = True
            if self._last_state:
                # Attaching an approved classroom load always begins in the declared
                # fail-closed state. The instructor must explicitly arm/start/on.
                self._last_state = await self._backend.set_power(False)
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
                    asyncio.create_task(self._publish_state_changes(socket), name="plug-state"),
                )
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    task.result()
        finally:
            if started:
                try:
                    self._last_state = await self._backend.set_power(False)
                except Exception:
                    LOGGER.exception("Smart-plug safe-state command failed during bridge shutdown")
            await self._backend.close()

    async def _authenticate_and_register(self, socket: AdapterSocket) -> None:
        authentication = AdapterAuthenticationFrame.model_validate(
            {
                "frameType": "adapter.authenticate",
                "frameId": str(uuid4()),
                "protocolVersion": 1,
                "credential": self.configuration.adapter_token,
                "sentAt": datetime.now(UTC),
            }
        )
        await self._send(socket, authentication)
        welcome = await self._receive_json(socket)
        if welcome.get("frameType") != "adapter.welcome":
            raise RuntimeError("Fabric did not accept smart-plug adapter authentication")
        node = build_node(
            at=datetime.now(UTC),
            host_id=self.configuration.host_id,
            site_id=self.configuration.site_id,
            room_id=self.configuration.room_id,
            node_id=self.configuration.node_id,
            simulated=self.configuration.simulated,
            vendor_brand=self.configuration.vendor_brand,
            model=self.configuration.model,
            protocol_version=self.configuration.protocol_version,
            switch_dps=self.configuration.switch_dps,
            device_address=self.configuration.device_address,
        )
        registration = AdapterRegistrationFrame.model_validate(
            {
                "frameType": "adapter.register",
                "frameId": str(uuid4()),
                "protocolVersion": 1,
                "manifest": build_manifest().model_dump(mode="json", exclude_none=True),
                "nodes": [node.model_dump(mode="json", exclude_none=True)],
                "sentAt": datetime.now(UTC),
            }
        )
        await self._send(socket, registration)
        registered = await self._receive_json(socket)
        if registered.get("frameType") != "adapter.registered":
            raise RuntimeError("Fabric did not accept smart-plug registration")
        if registered.get("registeredNodeIds") != [self.configuration.node_id]:
            raise RuntimeError("Fabric registered a different smart-plug node")

    async def _receive(self, socket: AdapterSocket) -> None:
        while True:
            frame = await self._receive_json(socket)
            frame_type = frame.get("frameType")
            if frame_type == "adapter.ack":
                continue
            if frame_type == "adapter.stop":
                if frame.get("nodeId") != self.configuration.node_id:
                    raise RuntimeError("Fabric stop frame targeted a different node")
                self._last_state = await self._backend.set_power(False)
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
            self._last_state = execution.state
            self._last_error = None
            await self._lifecycle(
                socket,
                command,
                "SUCCEEDED",
                details={
                    "on": execution.state,
                    "duplicatePrevented": execution.duplicate,
                },
            )
            await self._publish_state(
                socket,
                state=execution.state,
                source="command",
                correlation_id=command.correlationId,
                causation_id=str(command.commandId),
            )
        except (SmartPlugError, OSError) as error:
            self._last_error = str(error)[:500]
            await self._lifecycle(
                socket,
                command,
                "FAILED",
                code="SMART_PLUG_OPERATION_FAILED",
                message=self._last_error,
            )

    async def _publish_state_changes(self, socket: AdapterSocket) -> None:
        while not self.configuration.activation_file.is_file():  # noqa: ASYNC110
            await asyncio.sleep(0.1)
        state = await self._backend.read_state()
        self._last_state = state
        await self._publish_state(socket, state=state, source="initial")
        while self.configuration.activation_file.is_file():
            await asyncio.sleep(self.configuration.poll_interval_seconds)
            state = await self._backend.read_state()
            if state != self._last_state:
                self._last_state = state
                await self._publish_state(socket, state=state, source="poll")

    async def _publish_state(
        self,
        socket: AdapterSocket,
        *,
        state: bool,
        source: str,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> None:
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
                    "topic": POWER_STATE_CAPABILITY,
                    "sourceNodeId": self.configuration.node_id,
                    "sourceCapability": POWER_STATE_CAPABILITY,
                    "siteId": self.configuration.site_id,
                    "roomId": self.configuration.room_id,
                    "sessionId": self.configuration.session_id,
                    "timestamp": now,
                    "monotonicTimestamp": time.monotonic_ns(),
                    "sequence": self._next_sequence(),
                    "correlationId": correlation_id or str(uuid4()),
                    "causationId": causation_id,
                    "confidence": 1.0,
                    "ttlMs": 5_000,
                    "dataClassification": "operational",
                    "payload": {
                        "on": state,
                        "source": source,
                        "vendorBrand": self.configuration.vendor_brand,
                    },
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
            report = HealthReport.model_validate(
                {
                    "schemaVersion": "1.0",
                    "nodeId": self.configuration.node_id,
                    "reportedAt": now,
                    "connectionState": "connected" if healthy else "degraded",
                    "healthState": "healthy" if healthy else "degraded",
                    "message": self._last_error,
                    "metrics": {
                        "on": self._last_state,
                        "safeStateOff": True,
                        "pollIntervalSeconds": self.configuration.poll_interval_seconds,
                    },
                }
            )
            frame = AdapterHeartbeatFrame.model_validate(
                {
                    "frameType": "adapter.heartbeat",
                    "frameId": str(uuid4()),
                    "protocolVersion": 1,
                    "reports": [report.model_dump(mode="json", exclude_none=True)],
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

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence
