"""Authenticated, bounded Fabric bridge for one selected Sphero BOLT."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cit_integration_sdk import (
    CommandReplayCache,
    FabricAdapterClient,
    FabricConnectionConfiguration,
)
from cit_integration_sdk.bounded_demo import BoundedGroundDemonstration
from cit_protocol import FabricResolvedCommand, HealthReport

from .fabric_contract import (
    AIM_RESET_CAPABILITY,
    GROUND_DEMONSTRATION_CAPABILITY,
    GROUND_NUDGE_CAPABILITY,
    GROUND_STOP_CAPABILITY,
    GROUND_VELOCITY_CAPABILITY,
    LIGHT_SET_CAPABILITY,
    SENSOR_STATE_CAPABILITY,
    build_manifest,
    build_node,
)
from .policy import SPHERO_DEADMAN_MILLISECONDS, SPHERO_DEADMAN_SECONDS
from .transport import SpheroTransport


@dataclass(frozen=True, slots=True)
class FabricSpheroConfiguration:
    connection: FabricConnectionConfiguration
    host_id: str
    node_id: str
    display_name: str
    activation_file: Path
    simulated: bool


class SpheroCommandHandler:
    def __init__(self, *, node_id: str, transport: SpheroTransport) -> None:
        self.node_id = node_id
        self.transport = transport
        self._replay = CommandReplayCache[dict[str, object]]()
        self._write_lock = asyncio.Lock()
        self._last_velocity_at: float | None = None
        self._velocity_active = False
        self._demonstration = BoundedGroundDemonstration(
            drive=self._demo_drive,
            stop=self._demo_stop,
        )

    async def execute(self, command: FabricResolvedCommand) -> tuple[dict[str, object], bool]:
        if command.targetNodeId != self.node_id:
            raise ValueError("Command target is not this Sphero BOLT")
        if command.expiresAt <= datetime.now(UTC):
            raise ValueError("Command expired before Sphero BOLT execution")
        replay_key = command.idempotencyKey
        if self._replay.contains(replay_key):
            return self._replay.get(replay_key), True
        parameters = command.parameters.model_dump(mode="json")
        if command.action == GROUND_DEMONSTRATION_CAPABILITY:
            self._expect_keys(parameters, {"distanceMeters"})
            distance = self._number(parameters, "distanceMeters")
            await self._demonstration.start(distance_meters=distance)
            details = {
                "started": True,
                "distanceMetersEachWay": distance,
                "preemptibleBy": GROUND_STOP_CAPABILITY,
            }
            self._replay.remember(replay_key, details)
            return details, False
        if command.action in {
            GROUND_STOP_CAPABILITY,
            GROUND_VELOCITY_CAPABILITY,
            GROUND_NUDGE_CAPABILITY,
            AIM_RESET_CAPABILITY,
        }:
            await self._demonstration.cancel(reason="superseded_by_command")
        async with self._write_lock:
            details = await self._execute_once(command.action, parameters)
        self._replay.remember(replay_key, details)
        return details, False

    async def _execute_once(self, action: str, parameters: dict[str, object]) -> dict[str, object]:
        if action == GROUND_STOP_CAPABILITY:
            self._expect_keys(parameters, set())
            await self.transport.stop()
            self._velocity_active = False
            self._last_velocity_at = None
            return {"safeState": "stopped"}
        if action == GROUND_VELOCITY_CAPABILITY:
            self._expect_keys(
                parameters,
                {
                    "forwardMetersPerSecond",
                    "rightMetersPerSecond",
                    "clockwiseRadiansPerSecond",
                },
            )
            forward = self._number(parameters, "forwardMetersPerSecond")
            right = self._number(parameters, "rightMetersPerSecond")
            clockwise = self._number(parameters, "clockwiseRadiansPerSecond")
            roll = await self.transport.set_velocity(forward, right, clockwise)
            self._velocity_active = roll.speed_value > 0
            self._last_velocity_at = time.monotonic() if self._velocity_active else None
            return {
                "headingDegrees": roll.heading_degrees,
                "speedValue": roll.speed_value,
                "watchdogMilliseconds": SPHERO_DEADMAN_MILLISECONDS,
            }
        if action == GROUND_NUDGE_CAPABILITY:
            self._expect_keys(parameters, {"direction"})
            direction = self._direction(parameters)
            if direction == "stop":
                await self.transport.stop()
                self._velocity_active = False
                self._last_velocity_at = None
                return {"direction": direction, "safeState": "stopped"}
            forward, right = {
                "forward": (0.12, 0.0),
                "backward": (-0.12, 0.0),
                "left": (0.0, -0.12),
                "right": (0.0, 0.12),
            }[direction]
            roll = await self.transport.set_velocity(forward, right, 0.0)
            self._velocity_active = roll.speed_value > 0
            self._last_velocity_at = time.monotonic() if self._velocity_active else None
            return {
                "direction": direction,
                "headingDegrees": roll.heading_degrees,
                "speedValue": roll.speed_value,
                "watchdogMilliseconds": SPHERO_DEADMAN_MILLISECONDS,
            }
        if action == LIGHT_SET_CAPABILITY:
            self._expect_keys(parameters, {"red", "green", "blue"})
            red = self._integer(parameters, "red", minimum=0, maximum=255)
            green = self._integer(parameters, "green", minimum=0, maximum=255)
            blue = self._integer(parameters, "blue", minimum=0, maximum=255)
            await self.transport.set_color(red, green, blue)
            return {"red": red, "green": green, "blue": blue}
        if action == AIM_RESET_CAPABILITY:
            self._expect_keys(parameters, set())
            await self.transport.stop()
            await self.transport.reset_aim()
            self._velocity_active = False
            self._last_velocity_at = None
            return {"aim": "current-direction-is-forward", "safeState": "stopped"}
        raise ValueError(f"Unsupported Sphero BOLT Fabric action {action!r}")

    async def deadman_tick(self, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        if (
            self._velocity_active
            and self._last_velocity_at is not None
            and current - self._last_velocity_at >= SPHERO_DEADMAN_SECONDS
        ):
            async with self._write_lock:
                await self.transport.stop()
            self._velocity_active = False
            self._last_velocity_at = None
            return True
        return False

    async def safe_stop(self) -> None:
        await self._demonstration.cancel(reason="safe_stop", force_stop=True)

    async def _demo_drive(self, direction: str, _pulse: int) -> None:
        forward = 0.12 if direction == "forward" else -0.12
        async with self._write_lock:
            roll = await self.transport.set_velocity(forward, 0.0, 0.0)
            self._velocity_active = roll.speed_value > 0
            self._last_velocity_at = time.monotonic() if self._velocity_active else None

    async def _demo_stop(self, _reason: str) -> None:
        if self.transport.connected:
            async with self._write_lock:
                await self.transport.stop()
        self._velocity_active = False
        self._last_velocity_at = None

    @staticmethod
    def _expect_keys(parameters: dict[str, object], expected: set[str]) -> None:
        if set(parameters) != expected:
            raise ValueError(f"Command parameters must be exactly {sorted(expected)}")

    @staticmethod
    def _number(parameters: dict[str, object], name: str) -> float:
        raw = parameters.get(name)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"{name} must be numeric")
        return float(raw)

    @staticmethod
    def _direction(parameters: dict[str, object]) -> str:
        value = parameters.get("direction")
        if value not in {"forward", "backward", "left", "right", "stop"}:
            raise ValueError("direction must be forward, backward, left, right, or stop")
        return str(value)

    @classmethod
    def _integer(
        cls, parameters: dict[str, object], name: str, *, minimum: int, maximum: int
    ) -> int:
        raw = cls._number(parameters, name)
        if not raw.is_integer() or not minimum <= raw <= maximum:
            raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
        return int(raw)


class FabricSpheroBridge:
    def __init__(
        self, configuration: FabricSpheroConfiguration, transport: SpheroTransport
    ) -> None:
        self.configuration = configuration
        self.transport = transport
        self.handler = SpheroCommandHandler(node_id=configuration.node_id, transport=transport)
        self._last_error: str | None = None

    async def run(self) -> None:
        await self.transport.connect()
        try:
            client = FabricAdapterClient(
                self.configuration.connection,
                manifest=build_manifest(),
                nodes=[
                    build_node(
                        node_id=self.configuration.node_id,
                        display_name=self.configuration.display_name,
                        at=datetime.now(UTC),
                        host_id=self.configuration.host_id,
                        site_id=self.configuration.connection.site_id,
                        room_id=self.configuration.connection.room_id,
                        simulated=self.configuration.simulated,
                    )
                ],
            )
            async with client.connected():
                tasks = (
                    asyncio.create_task(self._receive(client), name="sphero-receive"),
                    asyncio.create_task(self._tick(client), name="sphero-deadman-sensors"),
                    asyncio.create_task(self._heartbeat(client), name="sphero-heartbeat"),
                )
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    task.result()
        finally:
            try:
                await self.handler.safe_stop()
            finally:
                await self.transport.disconnect()

    async def _receive(self, client: FabricAdapterClient) -> None:
        while True:
            frame = await client.receive_json()
            frame_type = frame.get("frameType")
            if frame_type == "adapter.ack":
                continue
            if frame_type == "adapter.stop":
                if frame.get("nodeId") != self.configuration.node_id:
                    raise RuntimeError("Fabric stop frame targeted a different Sphero BOLT")
                await self.handler.safe_stop()
                continue
            if frame_type != "adapter.command":
                raise RuntimeError(f"Unexpected Fabric adapter frame {frame_type!r}")
            await self._handle_command(
                client, FabricResolvedCommand.model_validate(frame.get("command"))
            )

    async def _handle_command(
        self, client: FabricAdapterClient, command: FabricResolvedCommand
    ) -> None:
        try:
            await client.publish_lifecycle(command, "ACCEPTED")
            await client.publish_lifecycle(command, "RUNNING")
            details, replayed = await self.handler.execute(command)
            self._last_error = None
            await client.publish_lifecycle(
                command, "SUCCEEDED", details={**details, "replayed": replayed}
            )
        except ValueError as error:
            self._last_error = str(error)[:500]
            await client.publish_lifecycle(
                command,
                "REJECTED",
                code="SPHERO_COMMAND_REJECTED",
                message=self._last_error,
            )
        except (OSError, RuntimeError, TimeoutError) as error:
            self._last_error = str(error)[:500]
            try:
                await self.handler.safe_stop()
            finally:
                await client.publish_lifecycle(
                    command,
                    "FAILED",
                    code="SPHERO_OPERATION_FAILED",
                    message=self._last_error,
                )

    async def _tick(self, client: FabricAdapterClient) -> None:
        next_sensor_publish_at = 0.0
        while True:
            await asyncio.sleep(0.05)
            try:
                await self.handler.deadman_tick()
            except (OSError, RuntimeError, TimeoutError) as error:
                self._last_error = str(error)[:500]
            now = time.monotonic()
            if now < next_sensor_publish_at or not self.configuration.activation_file.is_file():
                continue
            next_sensor_publish_at = now + 0.1
            try:
                snapshot = await self.transport.read_sensor()
                await client.publish_event(
                    topic=SENSOR_STATE_CAPABILITY,
                    source_node_id=self.configuration.node_id,
                    payload={
                        "model": "sphero-bolt",
                        "values": dict(snapshot.values),
                        "sensorSequence": snapshot.sequence,
                    },
                )
                self._last_error = None
            except (OSError, RuntimeError, TimeoutError, ValueError) as error:
                self._last_error = str(error)[:500]

    async def _heartbeat(self, client: FabricAdapterClient) -> None:
        while True:
            await asyncio.sleep(5)
            healthy = self.transport.connected and self._last_error is None
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
                                "watchdogMilliseconds": SPHERO_DEADMAN_MILLISECONDS,
                                "lessonActive": self.configuration.activation_file.is_file(),
                                "rawSensorStreamPublished": False,
                            },
                        }
                    )
                ]
            )
