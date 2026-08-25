"""Fabric command boundary for the bounded fleet sequence."""

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

from .fleet_backend import FleetSequenceBackend, FleetSequenceBackendError
from .fleet_contract import (
    ARM_CAPABILITY,
    START_CAPABILITY,
    STATUS_CAPABILITY,
    STOP_CAPABILITY,
    build_manifest,
    build_node,
)

_ARM_PARAMETERS = {
    "droneIds",
    "allowedSourceNodeIds",
    "launchIntervalSeconds",
    "minimumBatteryPercent",
    "instructorPresent",
    "flightAreaClear",
    "emergencyPlanReady",
    "independentRoutesConfirmed",
}


@dataclass(frozen=True, slots=True)
class BridgeConfiguration:
    connection: FabricConnectionConfiguration
    host_id: str
    node_id: str
    activation_file: Path
    simulated: bool
    status_interval_seconds: float = 0.5


class FleetSequenceCommandHandler:
    def __init__(self, backend: FleetSequenceBackend, *, node_id: str) -> None:
        self._backend = backend
        self._node_id = node_id
        self._executions = CommandReplayCache[Mapping[str, object]]()

    def has_seen(self, command_id: str) -> bool:
        return self._executions.contains(command_id)

    def validate(self, command: FabricResolvedCommand) -> None:
        if command.targetNodeId != self._node_id:
            raise ValueError("Command target is not this fleet sequence controller")
        if command.expiresAt <= datetime.now(UTC):
            raise ValueError("Command expired before fleet-controller execution")
        parameters = command.parameters.model_dump(mode="json")
        if command.action == STOP_CAPABILITY:
            if parameters:
                raise ValueError("Fleet stop does not accept parameters")
            return
        if command.action == START_CAPABILITY:
            if parameters:
                raise ValueError("Fleet start does not accept parameters")
            if command.priority.value not in {"instructor_override", "lesson_automation"}:
                raise ValueError("Fleet start requires a tutor or approved lesson trigger")
            if command.priority.value == "lesson_automation" and command.sourceNodeId is None:
                raise ValueError("Lesson-triggered fleet start requires an exact source node")
            return
        if command.action != ARM_CAPABILITY:
            raise ValueError("Only fleet arm, start, and stop are supported")
        if command.priority.value != "instructor_override":
            raise ValueError("Fleet arming requires instructor priority")
        if set(parameters) != _ARM_PARAMETERS:
            raise ValueError("Fleet arm parameters do not match the bounded contract")
        for confirmation in (
            "instructorPresent",
            "flightAreaClear",
            "emergencyPlanReady",
            "independentRoutesConfirmed",
        ):
            if parameters.get(confirmation) is not True:
                raise ValueError(f"{confirmation} must be explicitly confirmed")
        _identifier_list(parameters.get("droneIds"), "droneIds", minimum=1, maximum=8)
        _identifier_list(
            parameters.get("allowedSourceNodeIds"),
            "allowedSourceNodeIds",
            minimum=0,
            maximum=8,
        )
        _number(
            parameters.get("launchIntervalSeconds"),
            "launchIntervalSeconds",
            minimum=1,
            maximum=15,
        )
        _integer(
            parameters.get("minimumBatteryPercent"),
            "minimumBatteryPercent",
            minimum=20,
            maximum=100,
        )

    async def execute(self, command: FabricResolvedCommand) -> Mapping[str, object]:
        command_id = str(command.commandId)
        if self._executions.contains(command_id):
            return {"duplicatePrevented": True}
        self.validate(command)
        parameters = command.parameters.model_dump(mode="json")
        if command.action == ARM_CAPABILITY:
            details = await self._backend.arm(parameters)
        elif command.action == START_CAPABILITY:
            details = await self._backend.trigger(source_node_id=command.sourceNodeId)
        else:
            details = await self._backend.stop(reason="fabric_command")
        remembered = dict(details)
        self._executions.remember(command_id, remembered)
        return {**remembered, "duplicatePrevented": False}


class FabricFleetSequenceBridge:
    def __init__(
        self,
        configuration: BridgeConfiguration,
        *,
        backend: FleetSequenceBackend,
    ) -> None:
        if configuration.status_interval_seconds < 0.25:
            raise ValueError("Fleet status interval must be at least 0.25 seconds")
        self.configuration = configuration
        self._backend = backend
        self._handler = FleetSequenceCommandHandler(backend, node_id=configuration.node_id)
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
                    asyncio.create_task(self._receive(client), name="fleet-sequence-receive"),
                    asyncio.create_task(self._heartbeat(client), name="fleet-sequence-heartbeat"),
                    asyncio.create_task(self._publish_status(client), name="fleet-sequence-status"),
                    asyncio.create_task(
                        self._activation_watch(),
                        name="fleet-sequence-activation",
                    ),
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
                    raise RuntimeError("Fabric stop frame targeted a different fleet controller")
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
        except (FleetSequenceBackendError, ValueError, OSError) as error:
            self._last_error = str(error)[:500]
            await client.publish_lifecycle(
                command,
                "FAILED",
                code="FLEET_SEQUENCE_OPERATION_FAILED",
                message=self._last_error,
            )

    async def _publish_status(self, client: FabricAdapterClient) -> None:
        while True:
            await asyncio.sleep(self.configuration.status_interval_seconds)
            try:
                self._status = await self._backend.status()
                self._last_error = None
            except (FleetSequenceBackendError, OSError) as error:
                self._last_error = str(error)[:500]
                continue
            if self.configuration.activation_file.is_file():
                await client.publish_event(
                    topic=STATUS_CAPABILITY,
                    source_node_id=self.configuration.node_id,
                    payload=self._status,
                    ttl_ms=2_000,
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
                                "active": self._status.get("active") is True,
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


def _identifier_list(
    value: object,
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{name} must contain {minimum} to {maximum} identifiers")
    if any(not isinstance(item, str) or not item or len(item) > 128 for item in value):
        raise ValueError(f"{name} contains an invalid identifier")
    result = tuple(value)
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _number(value: object, name: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not minimum <= result <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return result


def _integer(value: object, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value
