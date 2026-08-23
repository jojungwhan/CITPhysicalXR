"""Authenticated Fabric bridge for the bounded MindWave-to-Tello demo."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cit_integration_sdk import (
    CommandReplayCache,
    FabricAdapterClient,
    FabricConnectionConfiguration,
)
from cit_protocol import FabricResolvedCommand, HealthReport

from .backend import BrainDemoBackend, BrainDemoBackendError
from .contract import ARM_CAPABILITY, STATUS_CAPABILITY, STOP_CAPABILITY, build_manifest, build_node

_ARM_PARAMETERS = {
    "attentionEnabled",
    "attentionThreshold",
    "meditationEnabled",
    "meditationThreshold",
    "blinkEnabled",
    "blinkThreshold",
    "dwellSeconds",
    "instructorPresent",
    "flightAreaClear",
    "emergencyPlanReady",
}


@dataclass(frozen=True, slots=True)
class BridgeConfiguration:
    connection: FabricConnectionConfiguration
    host_id: str
    node_id: str
    activation_file: Path
    simulated: bool
    status_interval_seconds: float = 0.5


class BrainDemoCommandHandler:
    def __init__(self, backend: BrainDemoBackend, *, node_id: str) -> None:
        self._backend = backend
        self._node_id = node_id
        self._executions = CommandReplayCache[Mapping[str, object]]()

    def has_seen(self, command_id: str) -> bool:
        return self._executions.contains(command_id)

    def validate(self, command: FabricResolvedCommand) -> None:
        if command.targetNodeId != self._node_id:
            raise ValueError("Command target is not this bounded demo controller")
        if command.expiresAt <= datetime.now(UTC):
            raise ValueError("Command expired before demo-controller execution")
        parameters = command.parameters.model_dump(mode="json")
        if command.action == STOP_CAPABILITY:
            if parameters:
                raise ValueError("Demo stop does not accept parameters")
            return
        if command.action != ARM_CAPABILITY:
            raise ValueError("Only the bounded one-shot arm and stop capabilities are supported")
        if command.priority.value != "instructor_override":
            raise ValueError("Demo arming requires instructor priority")
        if set(parameters) != _ARM_PARAMETERS:
            raise ValueError("Demo arm parameters do not match the bounded contract")
        for confirmation in ("instructorPresent", "flightAreaClear", "emergencyPlanReady"):
            if parameters.get(confirmation) is not True:
                raise ValueError(f"{confirmation} must be explicitly confirmed")
        enabled = []
        for signal in ("attention", "meditation", "blink"):
            key = f"{signal}Enabled"
            if type(parameters.get(key)) is not bool:
                raise ValueError(f"{key} must be boolean")
            enabled.append(parameters[key])
        if not any(enabled):
            raise ValueError("Select at least one MindWave signal")
        _integer(parameters, "attentionThreshold", minimum=1, maximum=100)
        _integer(parameters, "meditationThreshold", minimum=1, maximum=100)
        _integer(parameters, "blinkThreshold", minimum=0, maximum=254)
        dwell = parameters.get("dwellSeconds")
        if isinstance(dwell, bool) or not isinstance(dwell, (int, float)) or not 0 <= dwell <= 10:
            raise ValueError("dwellSeconds must be between 0 and 10")

    async def execute(self, command: FabricResolvedCommand) -> Mapping[str, object]:
        command_id = str(command.commandId)
        if self._executions.contains(command_id):
            return {"duplicatePrevented": True}
        self.validate(command)
        parameters = command.parameters.model_dump(mode="json")
        if command.action == ARM_CAPABILITY:
            details = await self._backend.arm(parameters)
        else:
            details = await self._backend.stop(reason="fabric_command")
        remembered = dict(details)
        self._executions.remember(command_id, remembered)
        return {**remembered, "duplicatePrevented": False}


class FabricBrainDemoBridge:
    def __init__(self, configuration: BridgeConfiguration, *, backend: BrainDemoBackend) -> None:
        if configuration.status_interval_seconds < 0.25:
            raise ValueError("Demo status interval must be at least 0.25 seconds")
        self.configuration = configuration
        self._backend = backend
        self._handler = BrainDemoCommandHandler(backend, node_id=configuration.node_id)
        self._status: Mapping[str, object] = {}
        self._last_error: str | None = None

    async def run(self) -> None:
        started = False
        try:
            self._status = await self._backend.start()
            started = True
            node = build_node(
                at=datetime.now(UTC),
                host_id=self.configuration.host_id,
                site_id=self.configuration.connection.site_id,
                room_id=self.configuration.connection.room_id,
                node_id=self.configuration.node_id,
                simulated=self.configuration.simulated,
            )
            client = FabricAdapterClient(
                self.configuration.connection,
                manifest=build_manifest(),
                nodes=[node],
            )
            async with client.connected():
                tasks = (
                    asyncio.create_task(self._receive(client), name="brain-demo-fabric-receive"),
                    asyncio.create_task(self._heartbeat(client), name="brain-demo-heartbeat"),
                    asyncio.create_task(self._publish_status(client), name="brain-demo-status"),
                    asyncio.create_task(self._activation_watch(), name="brain-demo-activation"),
                )
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    task.result()
        finally:
            if started:
                await self._backend.close()

    async def _receive(self, client: FabricAdapterClient) -> None:
        while True:
            frame = await client.receive_json()
            frame_type = frame.get("frameType")
            if frame_type == "adapter.ack":
                continue
            if frame_type == "adapter.stop":
                if frame.get("nodeId") != self.configuration.node_id:
                    raise RuntimeError("Fabric stop frame targeted a different demo controller")
                self._status = await self._backend.stop(reason=str(frame.get("reason", "stop")))
                continue
            if frame_type != "adapter.command":
                raise RuntimeError(f"Unexpected Fabric adapter frame {frame_type!r}")
            command = FabricResolvedCommand.model_validate(frame.get("command"))
            await self._handle_command(client, command)

    async def _handle_command(
        self,
        client: FabricAdapterClient,
        command: FabricResolvedCommand,
    ) -> None:
        if self._handler.has_seen(str(command.commandId)):
            return
        try:
            self._handler.validate(command)
        except ValueError as error:
            self._last_error = str(error)[:500]
            await client.publish_lifecycle(
                command,
                "REJECTED",
                code="ADAPTER_PARAMETER_REJECTED",
                message=self._last_error,
            )
            return
        try:
            await client.publish_lifecycle(command, "ACCEPTED")
            await client.publish_lifecycle(command, "RUNNING")
            self._status = await self._handler.execute(command)
            self._last_error = None
            await client.publish_lifecycle(command, "SUCCEEDED", details=self._status)
        except (BrainDemoBackendError, OSError) as error:
            self._last_error = str(error)[:500]
            await client.publish_lifecycle(
                command,
                "FAILED",
                code="BRAIN_DEMO_OPERATION_FAILED",
                message=self._last_error,
            )

    async def _publish_status(self, client: FabricAdapterClient) -> None:
        while True:
            await asyncio.sleep(self.configuration.status_interval_seconds)
            try:
                self._status = await self._backend.status()
                self._last_error = None
            except (BrainDemoBackendError, OSError) as error:
                self._last_error = str(error)[:500]
                continue
            if self.configuration.activation_file.is_file():
                await client.publish_event(
                    topic=STATUS_CAPABILITY,
                    source_node_id=self.configuration.node_id,
                    payload=self._status,
                    ttl_ms=2_000,
                    data_classification="biosignal_derived",
                )

    async def _heartbeat(self, client: FabricAdapterClient) -> None:
        while True:
            await asyncio.sleep(5)
            healthy = self._last_error is None
            await client.publish_heartbeat(
                [
                    HealthReport.model_validate(
                        {
                            "schemaVersion": "1.0",
                            "nodeId": self.configuration.node_id,
                            "reportedAt": datetime.now(UTC),
                            "connectionState": "connected" if healthy else "degraded",
                            "healthState": "healthy" if healthy else "degraded",
                            "message": self._last_error,
                            "metrics": {
                                "oneShot": True,
                                "armed": self._status.get("armed") is True,
                                "phase": str(self._status.get("phase", "unknown")),
                                "unrestrictedFlightCommands": False,
                            },
                        }
                    )
                ]
            )

    async def _activation_watch(self) -> None:
        while not self.configuration.activation_file.is_file():  # noqa: ASYNC110
            await asyncio.sleep(0.1)
        while self.configuration.activation_file.is_file():  # noqa: ASYNC110
            await asyncio.sleep(0.1)


def _integer(parameters: Mapping[str, object], name: str, *, minimum: int, maximum: int) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value
