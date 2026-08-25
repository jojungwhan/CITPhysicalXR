"""Authenticated Fabric bridge around the existing LEGO adapter boundary."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from cit_integration_sdk import FabricAdapterClient, FabricConnectionConfiguration
from cit_integration_sdk.bounded_demo import BoundedGroundDemonstration
from cit_protocol import DeviceCommandIntent, FabricResolvedCommand, HealthReport

from .adapter import PybricksHubAdapter
from .diagnostics import HubDiagnostic, HubTransportError
from .fabric_contract import (
    BATTERY_STATE_CAPABILITY,
    GROUND_DEMONSTRATION_CAPABILITY,
    GROUND_NUDGE_CAPABILITY,
    GROUND_STOP_CAPABILITY,
    GROUND_VELOCITY_CAPABILITY,
    SENSOR_STATE_CAPABILITY,
    build_manifest,
    build_node,
)


@dataclass(frozen=True, slots=True)
class FabricLegoConfiguration:
    connection: FabricConnectionConfiguration
    host_id: str
    activation_file: Path
    simulated: bool


class LegoCommandHandler:
    def __init__(self, adapter: PybricksHubAdapter) -> None:
        self._adapter = adapter
        self._demo_context: FabricResolvedCommand | None = None
        self._demonstration = BoundedGroundDemonstration(
            drive=self._demo_drive,
            stop=self._demo_stop,
            # LEGO's hub agent executes and stops each short DRIVE frame before
            # acknowledging it, unlike streaming-velocity robot transports.
            # Resume immediately so the 120 mm/s calibration covers about
            # 100 mm per leg instead of spending most of the window stopped.
            keepalive_seconds=0.001,
        )

    def validate(self, command: FabricResolvedCommand) -> None:
        if command.action == GROUND_DEMONSTRATION_CAPABILITY:
            if command.targetNodeId != self._adapter.device_id:
                raise ValueError("Command target is not this LEGO hub")
            if command.expiresAt <= datetime.now(UTC):
                raise ValueError("Command expired before LEGO execution")
            self._demonstration_distance(command.parameters.model_dump(mode="json"))
            if "drive.velocity" not in self._adapter.capabilities:
                raise ValueError("This LEGO hub does not expose ground mobility")
            return
        self.translate(command)

    def translate(self, command: FabricResolvedCommand) -> DeviceCommandIntent:
        if command.targetNodeId != self._adapter.device_id:
            raise ValueError("Command target is not this LEGO hub")
        if command.expiresAt <= datetime.now(UTC):
            raise ValueError("Command expired before LEGO execution")
        parameters = command.parameters.model_dump(mode="json")
        if command.action == GROUND_STOP_CAPABILITY:
            if parameters:
                raise ValueError("Ground-robot stop does not accept parameters")
            capability = "drive.stop"
            action = "stop"
            arguments: dict[str, object] = {}
        elif command.action == GROUND_VELOCITY_CAPABILITY:
            expected = {
                "forwardMetersPerSecond",
                "rightMetersPerSecond",
                "clockwiseRadiansPerSecond",
            }
            if set(parameters) != expected:
                raise ValueError("Ground velocity requires the three canonical velocity fields")
            forward = self._number(parameters, "forwardMetersPerSecond")
            right = self._number(parameters, "rightMetersPerSecond")
            clockwise = self._number(parameters, "clockwiseRadiansPerSecond")
            if abs(right) > 1e-9:
                raise ValueError("This differential-drive LEGO hub cannot strafe")
            if abs(forward) > 0.35 or abs(clockwise) > 0.6108652382:
                raise ValueError("LEGO velocity exceeds the canonical classroom bounds")
            capability = "drive.velocity"
            action = "run"
            arguments = {
                "speed": forward / 0.35,
                "turnRate": round(clockwise / 0.6108652382 * 100),
                "durationSeconds": 0.2,
            }
        elif command.action == GROUND_NUDGE_CAPABILITY:
            if set(parameters) != {"direction"}:
                raise ValueError("Ground nudge requires exactly one direction")
            direction = parameters.get("direction")
            if direction not in {"forward", "backward", "left", "right", "stop"}:
                raise ValueError("Ground nudge direction is invalid")
            if direction == "stop":
                capability = "drive.stop"
                action = "stop"
                arguments = {}
            else:
                capability = "drive.velocity"
                action = "run"
                speed, turn_rate = {
                    "forward": (0.12 / 0.35, 0),
                    "backward": (-0.12 / 0.35, 0),
                    "left": (0, -66),
                    "right": (0, 66),
                }[direction]
                arguments = {
                    "speed": speed,
                    "turnRate": turn_rate,
                    "durationSeconds": 0.2,
                }
        else:
            raise ValueError(f"Unsupported LEGO Fabric action {command.action!r}")
        return DeviceCommandIntent.model_validate(
            {
                "commandId": command.commandId,
                "sessionId": command.sessionId,
                "deviceId": self._adapter.device_id,
                "capability": capability,
                "action": action,
                "arguments": arguments,
                "source": "system",
                "issuedAt": command.requestedAt,
                "expiresAt": command.expiresAt,
                "idempotencyKey": command.idempotencyKey,
                "safetyContext": {
                    "policyId": command.safetyProfile,
                    "armed": True,
                    "deadmanActive": True,
                },
            }
        )

    async def execute(self, command: FabricResolvedCommand) -> dict[str, object]:
        self.validate(command)
        if command.action == GROUND_DEMONSTRATION_CAPABILITY:
            distance = self._demonstration_distance(command.parameters.model_dump(mode="json"))
            self._demo_context = command
            await self._demonstration.start(distance_meters=distance)
            return {
                "started": True,
                "distanceMetersEachWay": distance,
                "preemptibleBy": GROUND_STOP_CAPABILITY,
            }
        await self._demonstration.cancel(reason="superseded_by_command")
        intent = self.translate(command)
        result = await self._adapter.execute(intent, now=datetime.now(UTC))
        status = result.status.value
        if status not in {"completed", "duplicate"}:
            raise ValueError(result.message or f"LEGO command ended as {status}")
        details = result.details.model_dump(mode="json") if result.details else {}
        return {
            "legacyStatus": status,
            **details,
        }

    async def safe_stop(self, *, reason: str) -> None:
        await self._demonstration.cancel(reason=reason, force_stop=True)

    async def _demo_drive(self, direction: str, pulse: int) -> None:
        context = self._demo_context
        if context is None:
            raise RuntimeError("LEGO demonstration context is unavailable")
        now = datetime.now(UTC)
        # The Pybricks hub maps normalized percent onto a 1000 mm/s DriveBase
        # ceiling. A normalized 0.12 therefore represents about 120 mm/s.
        speed = 0.12 if direction == "forward" else -0.12
        intent = DeviceCommandIntent.model_validate(
            {
                "commandId": str(uuid4()),
                "sessionId": context.sessionId,
                "deviceId": self._adapter.device_id,
                "capability": "drive.velocity",
                "action": "run",
                "arguments": {
                    "speed": speed,
                    "turnRate": 0,
                    "durationSeconds": 0.15,
                },
                "source": "system",
                "issuedAt": now,
                "expiresAt": now + timedelta(seconds=1),
                "idempotencyKey": f"{context.idempotencyKey}:{direction}:{pulse}",
                "safetyContext": {
                    "policyId": context.safetyProfile,
                    "armed": True,
                    "deadmanActive": True,
                },
            }
        )
        result = await self._adapter.execute(intent, now=now)
        if result.status.value not in {"completed", "duplicate"}:
            raise RuntimeError(result.message or "LEGO demonstration pulse failed")

    async def _demo_stop(self, reason: str) -> None:
        await self._adapter.stop(reason=reason, at=datetime.now(UTC))

    @staticmethod
    def _demonstration_distance(parameters: dict[str, object]) -> float:
        if set(parameters) != {"distanceMeters"}:
            raise ValueError("Ground demonstration requires exactly distanceMeters")
        distance = LegoCommandHandler._number(parameters, "distanceMeters")
        if not 0.05 <= distance <= 0.1:
            raise ValueError("Ground demonstration distance must be from 0.05 through 0.1 metres")
        return distance

    @staticmethod
    def _number(parameters: dict[str, object], name: str) -> float:
        raw = parameters.get(name)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"{name} must be numeric")
        return float(raw)


class LegoTelemetryPoller:
    """Rate-limited, read-only sampling for Fabric sensor presentation."""

    def __init__(
        self,
        adapter: PybricksHubAdapter,
        *,
        session_id: str,
        interval_seconds: float = 0.5,
    ) -> None:
        if interval_seconds < 0.2:
            raise ValueError("LEGO telemetry polling must be at least 200 ms")
        self._adapter = adapter
        self._session_id = session_id
        self._interval_seconds = interval_seconds
        self._last_poll_at: datetime | None = None
        self._next_index = 0

    async def poll_if_due(self, *, at: datetime) -> None:
        readable = tuple(
            capability
            for capability in self._adapter.capabilities
            if capability.startswith("sensor.") or capability == "hub.battery"
        )
        if not readable:
            return
        if (
            self._last_poll_at is not None
            and (at - self._last_poll_at).total_seconds() < self._interval_seconds
        ):
            return
        capability = readable[self._next_index % len(readable)]
        self._next_index += 1
        self._last_poll_at = at
        operation_id = str(uuid4())
        result = await self._adapter.execute(
            DeviceCommandIntent.model_validate(
                {
                    "commandId": operation_id,
                    "sessionId": self._session_id,
                    "deviceId": self._adapter.device_id,
                    "capability": capability,
                    "action": "read",
                    "arguments": {},
                    "source": "system",
                    "issuedAt": at,
                    "expiresAt": at + timedelta(seconds=2),
                    "idempotencyKey": operation_id,
                    "safetyContext": {
                        "policyId": "lego-monitoring",
                        "armed": False,
                        "deadmanActive": False,
                    },
                }
            ),
            now=at,
        )
        if result.status.value not in {"completed", "duplicate"}:
            raise HubTransportError(
                HubDiagnostic(
                    code="LEGO_TELEMETRY_READ_FAILED",
                    summary=result.message or f"Could not read {capability}",
                    detail="The hub rejected a read-only monitoring request.",
                    recovery="Check the declared port map and reconnect the hub.",
                )
            )


class FabricLegoBridge:
    def __init__(
        self,
        configuration: FabricLegoConfiguration,
        *,
        adapter: PybricksHubAdapter,
    ) -> None:
        self.configuration = configuration
        self._adapter = adapter
        self._handler = LegoCommandHandler(adapter)
        self._telemetry = LegoTelemetryPoller(
            adapter,
            session_id=configuration.connection.session_id,
        )
        self._last_error: str | None = None

    async def run(self) -> None:
        await self._adapter.connect(at=datetime.now(UTC))
        try:
            node = build_node(
                self._adapter,
                at=datetime.now(UTC),
                host_id=self.configuration.host_id,
                site_id=self.configuration.connection.site_id,
                room_id=self.configuration.connection.room_id,
                simulated=self.configuration.simulated,
            )
            client = FabricAdapterClient(
                self.configuration.connection,
                manifest=build_manifest(),
                nodes=[node],
            )
            async with client.connected():
                tasks = (
                    asyncio.create_task(self._receive(client), name="lego-fabric-receive"),
                    asyncio.create_task(self._tick(client), name="lego-watchdog-and-events"),
                    asyncio.create_task(self._heartbeat(client), name="lego-heartbeat"),
                    asyncio.create_task(self._activation_watch(), name="lego-activation-watch"),
                )
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    task.result()
        finally:
            await self._handler.safe_stop(reason="fabric_bridge_shutdown")
            await self._adapter.disconnect(at=datetime.now(UTC))

    async def _receive(self, client: FabricAdapterClient) -> None:
        while True:
            frame = await client.receive_json()
            frame_type = frame.get("frameType")
            if frame_type == "adapter.ack":
                continue
            if frame_type == "adapter.stop":
                if frame.get("nodeId") != self._adapter.device_id:
                    raise RuntimeError("Fabric stop frame targeted a different LEGO hub")
                await self._handler.safe_stop(reason=str(frame.get("reason", "fabric_stop")))
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
        except (ValueError, HubTransportError, OSError) as error:
            self._last_error = str(error)[:500]
            await self._adapter.stop(reason="command_failure", at=datetime.now(UTC))
            await client.publish_lifecycle(
                command,
                "FAILED",
                code="LEGO_OPERATION_FAILED",
                message=self._last_error,
            )

    async def _tick(self, client: FabricAdapterClient) -> None:
        while True:
            await asyncio.sleep(0.05)
            at = datetime.now(UTC)
            if self.configuration.activation_file.is_file():
                try:
                    await self._telemetry.poll_if_due(at=at)
                    self._last_error = None
                except (HubTransportError, OSError) as error:
                    self._last_error = str(error)[:500]
            events = await self._adapter.tick(at=at)
            if not self.configuration.activation_file.is_file():
                continue
            for event in events:
                topic = (
                    BATTERY_STATE_CAPABILITY
                    if event.name == "telemetry.battery"
                    else SENSOR_STATE_CAPABILITY
                )
                await client.publish_event(
                    topic=topic,
                    source_node_id=self._adapter.device_id,
                    payload={
                        "category": event.category.value,
                        "name": event.name,
                        "values": event.values.model_dump(mode="json"),
                        "legacySequence": event.sequence,
                    },
                )

    async def _heartbeat(self, client: FabricAdapterClient) -> None:
        while True:
            await asyncio.sleep(5)
            healthy = self._adapter.connected and self._last_error is None
            await client.publish_heartbeat(
                [
                    HealthReport.model_validate(
                        {
                            "schemaVersion": "1.0",
                            "nodeId": self._adapter.device_id,
                            "reportedAt": datetime.now(UTC),
                            "connectionState": "connected" if healthy else "degraded",
                            "healthState": "healthy" if healthy else "degraded",
                            "message": self._last_error,
                            "metrics": {
                                "batteryPercent": self._adapter.battery_percent,
                                "watchdogMilliseconds": 500,
                                "lessonActive": self.configuration.activation_file.is_file(),
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
