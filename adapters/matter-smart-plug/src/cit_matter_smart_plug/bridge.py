"""Authenticated Fabric bridge for one standard Matter plug endpoint."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from cit_integration_sdk import (
    CommandReplayCache,
    FabricAdapterClient,
    FabricConnectionConfiguration,
)
from cit_protocol import FabricResolvedCommand, HealthReport

from .backend import MatterSmartPlug, SmartPlugError
from .contract import POWER_SET_CAPABILITY, POWER_STATE_CAPABILITY, build_manifest, build_node

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BridgeConfiguration:
    connection: FabricConnectionConfiguration
    host_id: str
    node_id: str
    activation_file: Path
    matter_node_id: int
    endpoint_id: int
    display_name: str
    vendor_name: str
    product_name: str
    poll_interval_seconds: float = 5.0


class MatterCommandHandler:
    def __init__(self, backend: MatterSmartPlug, *, node_id: str) -> None:
        self._backend = backend
        self._node_id = node_id
        self._executions = CommandReplayCache[bool]()

    def has_seen(self, command_id: str) -> bool:
        return self._executions.contains(command_id)

    def validate(self, command: FabricResolvedCommand) -> bool:
        if command.targetNodeId != self._node_id:
            raise ValueError("Command target is not this Matter plug node")
        if command.expiresAt <= datetime.now(UTC):
            raise ValueError("Command expired before adapter execution")
        if command.action != POWER_SET_CAPABILITY:
            raise ValueError(f"Unsupported Matter plug action {command.action!r}")
        parameters = command.parameters.model_dump(mode="json")
        if set(parameters) != {"on"} or type(parameters.get("on")) is not bool:
            raise ValueError("Matter plug command requires exactly one boolean 'on' parameter")
        return cast(bool, parameters["on"])

    async def execute(self, command: FabricResolvedCommand) -> tuple[bool, bool]:
        command_id = str(command.commandId)
        if self._executions.contains(command_id):
            return True, self._executions.get(command_id)
        on = self.validate(command)
        state = await self._backend.set_power(on)
        self._executions.remember(command_id, state)
        return False, state


class FabricMatterBridge:
    def __init__(self, configuration: BridgeConfiguration, *, backend: MatterSmartPlug) -> None:
        if configuration.poll_interval_seconds < 1:
            raise ValueError("poll_interval_seconds must be at least one second")
        self.configuration = configuration
        self._backend = backend
        self._handler = MatterCommandHandler(backend, node_id=configuration.node_id)
        self._last_state: bool | None = None
        self._last_error: str | None = None
        self._state_publication_enabled = asyncio.Event()

    async def run(self) -> None:
        started = False
        try:
            self._last_state = await self._backend.start()
            started = True
            if self._last_state:
                self._last_state = await self._backend.set_power(False)
            node = build_node(
                at=datetime.now(UTC),
                host_id=self.configuration.host_id,
                site_id=self.configuration.connection.site_id,
                room_id=self.configuration.connection.room_id,
                node_id=self.configuration.node_id,
                matter_node_id=self.configuration.matter_node_id,
                endpoint_id=self.configuration.endpoint_id,
                display_name=self.configuration.display_name,
                vendor_name=self.configuration.vendor_name,
                product_name=self.configuration.product_name,
            )
            client = FabricAdapterClient(
                self.configuration.connection,
                manifest=build_manifest(),
                nodes=[node],
            )
            async with client.connected():
                tasks = (
                    asyncio.create_task(self._receive(client), name="matter-fabric-receive"),
                    asyncio.create_task(self._heartbeat(client), name="matter-fabric-heartbeat"),
                    asyncio.create_task(self._publish_state_changes(client), name="matter-state"),
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
                    LOGGER.exception("Matter smart-plug safe-state command failed during shutdown")
            await self._backend.close()

    async def _receive(self, client: FabricAdapterClient) -> None:
        while True:
            frame = await client.receive_json()
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
            duplicate, state = await self._handler.execute(command)
            self._last_state = state
            self._last_error = None
            self._state_publication_enabled.set()
            await client.publish_lifecycle(
                command,
                "SUCCEEDED",
                details={"on": state, "duplicatePrevented": duplicate},
            )
            await self._publish_state(
                client,
                state=state,
                source="command",
                correlation_id=command.correlationId,
                causation_id=str(command.commandId),
            )
        except (SmartPlugError, OSError) as error:
            self._last_error = str(error)[:500]
            await client.publish_lifecycle(
                command,
                "FAILED",
                code="MATTER_SMART_PLUG_OPERATION_FAILED",
                message=self._last_error,
            )

    async def _publish_state_changes(self, client: FabricAdapterClient) -> None:
        while self.configuration.activation_file.is_file():
            try:
                await asyncio.wait_for(self._state_publication_enabled.wait(), timeout=0.1)
                break
            except TimeoutError:
                pass
        while self.configuration.activation_file.is_file():
            await asyncio.sleep(self.configuration.poll_interval_seconds)
            state = await self._backend.read_state()
            if state != self._last_state:
                self._last_state = state
                await self._publish_state(client, state=state, source="matter-subscription")

    async def _publish_state(
        self,
        client: FabricAdapterClient,
        *,
        state: bool,
        source: str,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> None:
        await client.publish_event(
            topic=POWER_STATE_CAPABILITY,
            source_node_id=self.configuration.node_id,
            payload={
                "on": state,
                "source": source,
                "vendorBrand": self.configuration.vendor_name or "Matter",
                "cloudDependency": False,
            },
            ttl_ms=5_000,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    async def _heartbeat(self, client: FabricAdapterClient) -> None:
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
                        "cloudDependency": False,
                        "matterEndpoint": self.configuration.endpoint_id,
                    },
                }
            )
            await client.publish_heartbeat([report])
