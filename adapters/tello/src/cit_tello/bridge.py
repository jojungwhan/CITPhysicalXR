"""Independent authenticated Fabric bridge for one Tello."""

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

from .backend import TelloBackend, TelloBackendError
from .contract import (
    EMERGENCY_STOP_CAPABILITY,
    LAND_CAPABILITY,
    MOVE_CAPABILITY,
    ROTATE_CAPABILITY,
    TAKEOFF_CAPABILITY,
    TELEMETRY_CAPABILITY,
    build_manifest,
    build_node,
)
from .media import TelloMediaPublisher


@dataclass(frozen=True, slots=True)
class BridgeConfiguration:
    connection: FabricConnectionConfiguration
    host_id: str
    node_id: str
    activation_file: Path
    simulated: bool
    ip_address: str | None
    brain2devices_drone_id: str | None = None
    telemetry_interval_seconds: float = 1.0
    media_publisher: TelloMediaPublisher | None = None


def _reported_error_detail(value: object) -> str | None:
    if not isinstance(value, Mapping) or not value:
        return None
    detail = value.get("detail") or value.get("title")
    return None if detail is None else str(detail)[:500]


def tello_health_report(
    *,
    node_id: str,
    at: datetime,
    telemetry: Mapping[str, object],
    last_error: str | None,
    telemetry_active: bool,
    camera_frames_published: int,
    camera_error: str | None,
) -> HealthReport:
    """Project the authoritative upstream link into one canonical Fabric heartbeat."""

    upstream_connection = telemetry.get("connection")
    upstream_disconnected = (
        isinstance(upstream_connection, str) and upstream_connection != "connected"
    )
    connection_error = _reported_error_detail(telemetry.get("connectionError"))
    message = (
        connection_error
        or last_error
        or (
            f"Brain2Devices reports Tello connection {upstream_connection}"
            if upstream_disconnected
            else None
        )
    )
    if upstream_disconnected:
        connection_state = "disconnected"
        health_state = "unhealthy"
    elif last_error is not None:
        connection_state = "degraded"
        health_state = "degraded"
    else:
        connection_state = "connected"
        health_state = "healthy"
    return HealthReport.model_validate(
        {
            "schemaVersion": "1.0",
            "nodeId": node_id,
            "reportedAt": at,
            "connectionState": connection_state,
            "healthState": health_state,
            "message": message,
            "batteryPercent": telemetry.get("batteryPercent"),
            "metrics": {
                "boundedManualFlightCommands": True,
                "takeoffEnabled": connection_state == "connected" and last_error is None,
                "telemetryActive": telemetry_active,
                "cameraFramesPublished": camera_frames_published,
                "cameraError": camera_error,
            },
        }
    )


class TelloCommandHandler:
    def __init__(self, backend: TelloBackend, *, node_id: str) -> None:
        self._backend = backend
        self._node_id = node_id
        self._executions = CommandReplayCache[Mapping[str, object]]()

    def has_seen(self, command_id: str) -> bool:
        return self._executions.contains(command_id)

    def validate(self, command: FabricResolvedCommand) -> None:
        if command.targetNodeId != self._node_id:
            raise ValueError("Command target is not this Tello node")
        if command.expiresAt <= datetime.now(UTC):
            raise ValueError("Command expired before Tello execution")
        supported = {
            TAKEOFF_CAPABILITY,
            MOVE_CAPABILITY,
            ROTATE_CAPABILITY,
            LAND_CAPABILITY,
            EMERGENCY_STOP_CAPABILITY,
        }
        if command.action not in supported:
            raise ValueError("Tello command is unsupported")
        parameters = command.parameters.model_dump(mode="json")
        if command.action in {LAND_CAPABILITY, EMERGENCY_STOP_CAPABILITY} and parameters:
            raise ValueError("Tello safe-state commands do not accept parameters")
        confirmations = {
            "instructorPresent",
            "flightAreaClear",
            "emergencyPlanReady",
        }
        if command.action == TAKEOFF_CAPABILITY:
            if set(parameters) != confirmations or not all(
                parameters.get(name) is True for name in confirmations
            ):
                raise ValueError("Tello takeoff requires all instructor safety confirmations")
        if command.action == MOVE_CAPABILITY:
            if set(parameters) != confirmations | {"direction", "distanceCentimeters"}:
                raise ValueError("Tello movement parameters are incomplete or unsupported")
            if not all(parameters.get(name) is True for name in confirmations):
                raise ValueError("Tello movement requires all instructor safety confirmations")
            if parameters.get("direction") not in {
                "forward",
                "back",
                "left",
                "right",
                "up",
                "down",
            }:
                raise ValueError("Tello movement direction is unsupported")
            distance = parameters.get("distanceCentimeters")
            if (
                isinstance(distance, bool)
                or not isinstance(distance, int)
                or not 20 <= distance <= 50
            ):
                raise ValueError("Tello movement must be between 20 and 50 centimeters")
        if command.action == ROTATE_CAPABILITY:
            if set(parameters) != confirmations | {"clockwise", "degrees"}:
                raise ValueError("Tello rotation parameters are incomplete or unsupported")
            if not all(parameters.get(name) is True for name in confirmations):
                raise ValueError("Tello rotation requires all instructor safety confirmations")
            clockwise = parameters.get("clockwise")
            degrees = parameters.get("degrees")
            if not isinstance(clockwise, bool):
                raise ValueError("Tello rotation direction must be boolean")
            if isinstance(degrees, bool) or not isinstance(degrees, int) or not 1 <= degrees <= 90:
                raise ValueError("Tello rotation must be between 1 and 90 degrees")

    async def execute(self, command: FabricResolvedCommand) -> Mapping[str, object]:
        command_id = str(command.commandId)
        if self._executions.contains(command_id):
            return {"duplicatePrevented": True}
        self.validate(command)
        parameters = command.parameters.model_dump(mode="json")
        if command.action == TAKEOFF_CAPABILITY:
            details = await self._backend.takeoff()
        elif command.action == MOVE_CAPABILITY:
            details = await self._backend.move(
                direction=str(parameters["direction"]),
                distance_centimeters=int(parameters["distanceCentimeters"]),
            )
        elif command.action == ROTATE_CAPABILITY:
            details = await self._backend.rotate(
                clockwise=bool(parameters["clockwise"]),
                degrees=int(parameters["degrees"]),
            )
        elif command.action == LAND_CAPABILITY:
            details = await self._backend.land(reason="fabric_command")
        else:
            details = await self._backend.emergency_stop(reason="fabric_command")
        remembered = dict(details)
        self._executions.remember(command_id, remembered)
        return {**remembered, "duplicatePrevented": False}


class FabricTelloBridge:
    def __init__(self, configuration: BridgeConfiguration, *, backend: TelloBackend) -> None:
        if configuration.telemetry_interval_seconds < 0.5:
            raise ValueError("Tello telemetry interval must be at least 0.5 seconds")
        self.configuration = configuration
        self._backend = backend
        self._handler = TelloCommandHandler(backend, node_id=configuration.node_id)
        self._last_telemetry: Mapping[str, object] = {}
        self._last_error: str | None = None

    async def run(self) -> None:
        started = False
        try:
            self._last_telemetry = await self._backend.start()
            started = True
            node = build_node(
                at=datetime.now(UTC),
                host_id=self.configuration.host_id,
                site_id=self.configuration.connection.site_id,
                room_id=self.configuration.connection.room_id,
                node_id=self.configuration.node_id,
                simulated=self.configuration.simulated,
                ip_address=self.configuration.ip_address,
                brain2devices_drone_id=self.configuration.brain2devices_drone_id,
            )
            client = FabricAdapterClient(
                self.configuration.connection,
                manifest=build_manifest(),
                nodes=[node],
            )
            async with client.connected():
                tasks = (
                    asyncio.create_task(self._receive(client), name="tello-fabric-receive"),
                    asyncio.create_task(self._heartbeat(client), name="tello-fabric-heartbeat"),
                    asyncio.create_task(self._telemetry(client), name="tello-telemetry"),
                    asyncio.create_task(self._activation_watch(), name="tello-activation-watch"),
                    *(
                        (
                            asyncio.create_task(
                                self.configuration.media_publisher.run(),
                                name="tello-media-publisher",
                            ),
                        )
                        if self.configuration.media_publisher is not None
                        else ()
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
                try:
                    await self._backend.land(reason="adapter_shutdown")
                except Exception:
                    # An unreachable Tello must rely on its own loss-of-link behavior.
                    pass
            await self._backend.close()

    async def _receive(self, client: FabricAdapterClient) -> None:
        while True:
            frame = await client.receive_json()
            frame_type = frame.get("frameType")
            if frame_type == "adapter.ack":
                continue
            if frame_type == "adapter.stop":
                if frame.get("nodeId") != self.configuration.node_id:
                    raise RuntimeError("Fabric stop frame targeted a different Tello")
                reason = str(frame.get("reason", "fabric_stop"))
                if "emergency" in reason.casefold():
                    await self._backend.emergency_stop(reason=reason)
                else:
                    await self._backend.land(reason=reason)
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
            details = await self._handler.execute(command)
            self._last_error = None
            await client.publish_lifecycle(command, "SUCCEEDED", details=details)
        except (TelloBackendError, OSError) as error:
            self._last_error = str(error)[:500]
            await client.publish_lifecycle(
                command,
                "FAILED",
                code="TELLO_OPERATION_FAILED",
                message=self._last_error,
            )

    async def _telemetry(self, client: FabricAdapterClient) -> None:
        while True:
            await asyncio.sleep(self.configuration.telemetry_interval_seconds)
            try:
                self._last_telemetry = await self._backend.telemetry()
                self._last_error = None
            except (TelloBackendError, OSError) as error:
                self._last_error = str(error)[:500]
                continue
            if not self.configuration.activation_file.is_file():
                continue
            await client.publish_event(
                topic=TELEMETRY_CAPABILITY,
                source_node_id=self.configuration.node_id,
                payload=self._last_telemetry,
                ttl_ms=3_000,
            )

    async def _heartbeat(self, client: FabricAdapterClient) -> None:
        while True:
            await asyncio.sleep(5)
            media_publisher = self.configuration.media_publisher
            await client.publish_heartbeat(
                [
                    tello_health_report(
                        node_id=self.configuration.node_id,
                        at=datetime.now(UTC),
                        telemetry=self._last_telemetry,
                        last_error=self._last_error,
                        telemetry_active=self.configuration.activation_file.is_file(),
                        camera_frames_published=(
                            media_publisher.frames_published if media_publisher is not None else 0
                        ),
                        camera_error=(
                            media_publisher.last_error if media_publisher is not None else None
                        ),
                    )
                ]
            )

    async def _activation_watch(self) -> None:
        while not self.configuration.activation_file.is_file():  # noqa: ASYNC110
            await asyncio.sleep(0.1)
        while self.configuration.activation_file.is_file():  # noqa: ASYNC110
            await asyncio.sleep(0.1)
