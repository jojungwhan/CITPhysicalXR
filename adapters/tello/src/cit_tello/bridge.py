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
        if command.action not in {LAND_CAPABILITY, EMERGENCY_STOP_CAPABILITY}:
            raise ValueError(
                "Tello takeoff and movement are intentionally unavailable in this safe slice"
            )
        if command.parameters.model_dump(mode="json"):
            raise ValueError("Tello safe-state commands do not accept parameters")

    async def execute(self, command: FabricResolvedCommand) -> Mapping[str, object]:
        command_id = str(command.commandId)
        if self._executions.contains(command_id):
            return {"duplicatePrevented": True}
        self.validate(command)
        if command.action == LAND_CAPABILITY:
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
                                "safeFlightCommandsOnly": True,
                                "takeoffEnabled": False,
                                "telemetryActive": self.configuration.activation_file.is_file(),
                                "cameraFramesPublished": (
                                    self.configuration.media_publisher.frames_published
                                    if self.configuration.media_publisher is not None
                                    else 0
                                ),
                                "cameraError": (
                                    self.configuration.media_publisher.last_error
                                    if self.configuration.media_publisher is not None
                                    else None
                                ),
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
