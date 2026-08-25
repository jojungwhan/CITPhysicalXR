"""RoboMaster-only command validation and duplicate suppression."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from cit_integration_sdk import CommandReplayCache
from cit_integration_sdk.bounded_demo import BoundedGroundDemonstration
from cit_protocol import FabricResolvedCommand

from .backend import RobotBackend, validate_velocity_parameters
from .contract import (
    ROBOT_DEMONSTRATION_CAPABILITY,
    ROBOT_LIGHT_CAPABILITY,
    ROBOT_NUDGE_CAPABILITY,
    ROBOT_STOP_CAPABILITY,
    ROBOT_VELOCITY_CAPABILITY,
)


@dataclass(frozen=True, slots=True)
class CommandExecution:
    duplicate: bool
    details: Mapping[str, object]


class RobotCommandHandler:
    """Fail-closed adapter-level validation and duplicate suppression."""

    def __init__(self, backend: RobotBackend, *, robot_node_id: str) -> None:
        self._backend = backend
        self._robot_node_id = robot_node_id
        self._executions = CommandReplayCache[Mapping[str, object]]()
        self._demo_key = ""
        self._demonstration = BoundedGroundDemonstration(
            drive=self._demo_drive,
            stop=self._demo_stop,
        )

    def has_seen(self, command_id: str) -> bool:
        return self._executions.contains(command_id)

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
        if command.action == ROBOT_NUDGE_CAPABILITY:
            self._nudge_velocity(parameters)
            return
        if command.action == ROBOT_DEMONSTRATION_CAPABILITY:
            self._demonstration_distance(parameters)
            return
        if command.action == ROBOT_LIGHT_CAPABILITY:
            self._light_color(parameters)
            return
        raise ValueError(f"Unsupported RoboMaster action {command.action!r}")

    async def execute(self, command: FabricResolvedCommand) -> CommandExecution:
        command_id = str(command.commandId)
        if self._executions.contains(command_id):
            return CommandExecution(
                duplicate=True,
                details={**dict(self._executions.get(command_id)), "duplicatePrevented": True},
            )
        self.validate(command)
        parameters = command.parameters.model_dump(mode="json")
        if command.action == ROBOT_DEMONSTRATION_CAPABILITY:
            distance = self._demonstration_distance(parameters)
            self._demo_key = command.idempotencyKey
            await self._demonstration.start(distance_meters=distance)
            details: Mapping[str, object] = {
                "started": True,
                "distanceMetersEachWay": distance,
                "preemptibleBy": ROBOT_STOP_CAPABILITY,
            }
            self._executions.remember(command_id, dict(details))
            return CommandExecution(duplicate=False, details=details)
        if command.action in {
            ROBOT_STOP_CAPABILITY,
            ROBOT_VELOCITY_CAPABILITY,
            ROBOT_NUDGE_CAPABILITY,
        }:
            await self._demonstration.cancel(reason="superseded_by_command")
        if command.action == ROBOT_STOP_CAPABILITY:
            await self._backend.stop(reason="fabric_command")
            details = {"stopped": True}
        elif command.action == ROBOT_LIGHT_CAPABILITY:
            red, green, blue = self._light_color(parameters)
            details = await self._backend.set_light(
                red=red,
                green=green,
                blue=blue,
                idempotency_key=command.idempotencyKey,
            )
        elif command.action == ROBOT_VELOCITY_CAPABILITY:
            forward, right, clockwise = validate_velocity_parameters(parameters)
            details = await self._backend.set_velocity(
                forward=forward,
                right=right,
                clockwise=clockwise,
                idempotency_key=command.idempotencyKey,
            )
        else:
            forward, right, clockwise = self._nudge_velocity(parameters)
            if parameters.get("direction") == "stop":
                await self._backend.stop(reason="fabric_nudge_stop")
                details = {"stopped": True, "direction": "stop"}
            else:
                details = await self._backend.set_velocity(
                    forward=forward,
                    right=right,
                    clockwise=clockwise,
                    idempotency_key=command.idempotencyKey,
                )
        self._executions.remember(command_id, dict(details))
        return CommandExecution(duplicate=False, details=details)

    async def safe_stop(self, *, reason: str) -> None:
        await self._demonstration.cancel(reason=reason, force_stop=True)

    async def _demo_drive(self, direction: str, pulse: int) -> None:
        forward = 0.12 if direction == "forward" else -0.12
        await self._backend.set_velocity(
            forward=forward,
            right=0.0,
            clockwise=0.0,
            idempotency_key=f"{self._demo_key}:{direction}:{pulse}",
        )

    async def _demo_stop(self, reason: str) -> None:
        await self._backend.stop(reason=reason)

    @staticmethod
    def _demonstration_distance(parameters: Mapping[str, object]) -> float:
        if set(parameters) != {"distanceMeters"}:
            raise ValueError("Ground demonstration requires exactly distanceMeters")
        value = parameters.get("distanceMeters")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Ground demonstration distance is invalid")
        distance = float(value)
        if not 0.05 <= distance <= 0.1:
            raise ValueError("Ground demonstration distance must be from 0.05 through 0.1 metres")
        return distance

    @staticmethod
    def _light_color(parameters: Mapping[str, object]) -> tuple[int, int, int]:
        if set(parameters) != {"red", "green", "blue"}:
            raise ValueError("RoboMaster light requires exactly red, green, and blue")
        channels: list[int] = []
        for name in ("red", "green", "blue"):
            value = parameters.get(name)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
                raise ValueError(f"RoboMaster light {name} must be an integer from 0 through 255")
            channels.append(value)
        return (channels[0], channels[1], channels[2])

    @staticmethod
    def _nudge_velocity(parameters: Mapping[str, object]) -> tuple[float, float, float]:
        if set(parameters) != {"direction"}:
            raise ValueError("Ground nudge requires exactly one direction")
        direction = parameters.get("direction")
        if not isinstance(direction, str):
            raise ValueError("Ground nudge direction is invalid")
        if direction == "stop":
            return (0.0, 0.0, 0.0)
        try:
            return {
                "forward": (0.12, 0.0, 0.0),
                "backward": (-0.12, 0.0, 0.0),
                "left": (0.0, -0.12, 0.0),
                "right": (0.0, 0.12, 0.0),
            }[direction]
        except KeyError as error:
            raise ValueError("Ground nudge direction is invalid") from error
