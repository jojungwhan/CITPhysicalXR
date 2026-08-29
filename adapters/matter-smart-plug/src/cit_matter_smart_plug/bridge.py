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
from .contract import (
    ELECTRICAL_STATE_CAPABILITY,
    POWER_SET_CAPABILITY,
    POWER_STATE_CAPABILITY,
    build_manifest,
    build_node,
)
from .matter_client import ElectricalMeasurements

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
        self._last_electrical: ElectricalMeasurements | None = None
        self._electrical_telemetry_available = False
        self._last_error: str | None = None
        self._state_publication_enabled = asyncio.Event()
        self._state_publication_session_id: str | None = None

    async def run(self) -> None:
        started = False
        try:
            self._last_state = await self._backend.start()
            started = True
            if self._last_state:
                self._last_state = await self._backend.set_power(False)
            initial_electrical = await self._read_optional_electrical()
            self._electrical_telemetry_available = initial_electrical is not None
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
                electrical_telemetry=self._electrical_telemetry_available,
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
        except Exception as error:
            LOGGER.exception(
                "Matter adapter stopped unexpectedly node_id=%s "
                "bootstrap_session_id=%s error_type=%s",
                self.configuration.node_id,
                self.configuration.connection.session_id,
                type(error).__name__,
            )
            raise
        finally:
            if started:
                LOGGER.info(
                    "Matter shutdown safe state starting node_id=%s previous_on=%s",
                    self.configuration.node_id,
                    self._last_state,
                )
                try:
                    self._last_state = await self._backend.set_power(False)
                    LOGGER.info(
                        "Matter shutdown safe state completed node_id=%s resulting_on=%s",
                        self.configuration.node_id,
                        self._last_state,
                    )
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
                self._state_publication_session_id = None
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
        requested_on = command.parameters.model_dump(mode="json").get("on")
        LOGGER.info(
            "Matter command received node_id=%s command_id=%s command_session_id=%s "
            "action=%s requested_on=%s",
            self.configuration.node_id,
            command.commandId,
            command.sessionId,
            command.action,
            requested_on,
        )
        if self._handler.has_seen(str(command.commandId)):
            LOGGER.info(
                "Matter duplicate command ignored node_id=%s command_id=%s",
                self.configuration.node_id,
                command.commandId,
            )
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
            LOGGER.info(
                "Matter command verified node_id=%s command_id=%s resulting_on=%s "
                "duplicate_prevented=%s",
                self.configuration.node_id,
                command.commandId,
                state,
                duplicate,
            )
            self._last_state = state
            self._last_error = None
            self._state_publication_session_id = str(command.sessionId)
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
                session_id=str(command.sessionId),
                correlation_id=command.correlationId,
                causation_id=str(command.commandId),
            )
            await self._publish_current_electrical(
                client,
                source="command",
                session_id=str(command.sessionId),
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
            try:
                state = await self._backend.read_state()
                session_id = self._state_publication_session_id
                if state != self._last_state:
                    self._last_state = state
                    if session_id is not None:
                        await self._publish_state(
                            client,
                            state=state,
                            source="matter-subscription",
                            session_id=session_id,
                        )
                if session_id is not None:
                    await self._publish_current_electrical(
                        client,
                        source="matter-subscription",
                        session_id=session_id,
                    )
            except (SmartPlugError, OSError) as error:
                # A controller read can time out on a momentary RF or mDNS
                # stall. Keep polling: dropping the adapter here would leave
                # the plug disconnected until someone relaunched it by hand.
                self._last_error = str(error)[:500]
                LOGGER.warning(
                    "Matter state poll failed node_id=%s error_type=%s error=%s",
                    self.configuration.node_id,
                    type(error).__name__,
                    self._last_error,
                )

    async def _publish_state(
        self,
        client: FabricAdapterClient,
        *,
        state: bool,
        source: str,
        session_id: str,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> None:
        await client.publish_event(
            topic=POWER_STATE_CAPABILITY,
            source_node_id=self.configuration.node_id,
            session_id=session_id,
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
        LOGGER.info(
            "Matter state event queued node_id=%s event_session_id=%s on=%s source=%s "
            "correlation_id=%s",
            self.configuration.node_id,
            session_id,
            state,
            source,
            correlation_id or "generated",
        )

    async def _read_optional_electrical(self) -> ElectricalMeasurements | None:
        try:
            return await self._backend.read_electrical_measurements()
        except SmartPlugError as error:
            LOGGER.warning("Optional Matter electrical telemetry is unavailable: %s", error)
            return None

    async def _publish_current_electrical(
        self,
        client: FabricAdapterClient,
        *,
        source: str,
        session_id: str,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> None:
        if not self._electrical_telemetry_available:
            return
        measurements = await self._read_optional_electrical()
        if measurements is None or measurements == self._last_electrical:
            return
        self._last_electrical = measurements
        payload = _electrical_payload(measurements)
        payload.update(
            {
                "source": source,
                "standard": "Matter 1.3",
                "vendorBrand": self.configuration.vendor_name or "Matter",
                "productName": self.configuration.product_name,
                "cloudDependency": False,
            }
        )
        await client.publish_event(
            topic=ELECTRICAL_STATE_CAPABILITY,
            source_node_id=self.configuration.node_id,
            session_id=session_id,
            payload=payload,
            ttl_ms=15_000,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        LOGGER.info(
            "Matter electrical event queued node_id=%s event_session_id=%s source=%s "
            "measurement_fields=%s correlation_id=%s",
            self.configuration.node_id,
            session_id,
            source,
            ",".join(sorted(_electrical_payload(measurements))),
            correlation_id or "generated",
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
                        "electricalTelemetryAvailable": (self._electrical_telemetry_available),
                    },
                }
            )
            await client.publish_heartbeat([report])


def _electrical_payload(measurements: ElectricalMeasurements) -> dict[str, object]:
    values = {
        "activePowerWatts": measurements.active_power_watts,
        "voltageVolts": measurements.voltage_volts,
        "activeCurrentAmperes": measurements.active_current_amperes,
        "cumulativeEnergyKilowattHours": measurements.cumulative_energy_kilowatt_hours,
        "frequencyHertz": measurements.frequency_hertz,
        "powerFactorRatio": measurements.power_factor_ratio,
    }
    return {key: value for key, value in values.items() if value is not None}
