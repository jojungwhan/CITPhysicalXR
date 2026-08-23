"""RoboMaster-only command validation and duplicate suppression."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from cit_integration_sdk import CommandReplayCache
from cit_protocol import FabricResolvedCommand

from .backend import RobotBackend, validate_velocity_parameters
from .contract import ROBOT_STOP_CAPABILITY, ROBOT_VELOCITY_CAPABILITY


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
        if command.action == ROBOT_STOP_CAPABILITY:
            await self._backend.stop(reason="fabric_command")
            details: Mapping[str, object] = {"stopped": True}
        else:
            forward, right, clockwise = validate_velocity_parameters(parameters)
            details = await self._backend.set_velocity(
                forward=forward,
                right=right,
                clockwise=clockwise,
                idempotency_key=command.idempotencyKey,
            )
        self._executions.remember(command_id, dict(details))
        return CommandExecution(duplicate=False, details=details)
