from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from cit_protocol import FabricResolvedCommand
from cit_robomaster_leap.backend import validate_velocity_parameters
from cit_robomaster_leap.bridge import RobotCommandHandler


class RecordingRobot:
    def __init__(self) -> None:
        self.velocities: list[dict[str, object]] = []
        self.lights: list[dict[str, object]] = []
        self.stops: list[str] = []

    async def start(self) -> None:
        return None

    async def set_velocity(
        self,
        *,
        forward: float,
        right: float,
        clockwise: float,
        idempotency_key: str,
    ) -> dict[str, object]:
        values: dict[str, object] = {
            "forward": forward,
            "right": right,
            "clockwise": clockwise,
            "idempotencyKey": idempotency_key,
        }
        self.velocities.append(values)
        return values

    async def set_light(
        self,
        *,
        red: int,
        green: int,
        blue: int,
        idempotency_key: str,
    ) -> dict[str, object]:
        values: dict[str, object] = {
            "red": red,
            "green": green,
            "blue": blue,
            "idempotencyKey": idempotency_key,
        }
        self.lights.append(values)
        return values

    async def stop(self, *, reason: str) -> None:
        self.stops.append(reason)

    async def close(self) -> None:
        return None


def command(*, action: str, parameters: dict[str, Any]) -> FabricResolvedCommand:
    now = datetime.now(UTC)
    return FabricResolvedCommand.model_validate(
        {
            "commandId": str(uuid4()),
            "requestMessageId": str(uuid4()),
            "schemaVersion": "1.0",
            "sessionId": "session-a",
            "targetNodeId": "s1-a",
            "action": action,
            "parameters": parameters,
            "priority": "lesson_automation",
            "idempotencyKey": str(uuid4()),
            "requestedAt": now,
            "expiresAt": now + timedelta(seconds=1),
            "safetyProfile": "classroom-ground-robot",
            "correlationId": "gesture-a",
        }
    )


@pytest.mark.asyncio
async def test_adapter_executes_only_the_canonical_bounded_velocity_shape() -> None:
    robot = RecordingRobot()
    handler = RobotCommandHandler(robot, robot_node_id="s1-a")
    resolved = command(
        action="mobility.ground.set_velocity",
        parameters={
            "forwardMetersPerSecond": 0.2,
            "rightMetersPerSecond": -0.1,
            "clockwiseRadiansPerSecond": 0.3,
        },
    )

    first = await handler.execute(resolved)
    second = await handler.execute(resolved)

    assert first.duplicate is False
    assert second.duplicate is True
    assert robot.velocities == [
        {
            "forward": 0.2,
            "right": -0.1,
            "clockwise": 0.3,
            "idempotencyKey": resolved.idempotencyKey,
        }
    ]


@pytest.mark.parametrize(
    "parameters",
    [
        {
            "forwardMetersPerSecond": 0.351,
            "rightMetersPerSecond": 0.0,
            "clockwiseRadiansPerSecond": 0.0,
        },
        {
            "forwardMetersPerSecond": 0.0,
            "rightMetersPerSecond": 0.0,
            "clockwiseRadiansPerSecond": float("nan"),
        },
        {"forwardMetersPerSecond": 0.0},
    ],
)
def test_adapter_rejects_values_outside_its_device_level_bounds(
    parameters: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        validate_velocity_parameters(parameters)


@pytest.mark.asyncio
async def test_stop_is_parameterless_and_never_requires_a_velocity_command() -> None:
    robot = RecordingRobot()
    handler = RobotCommandHandler(robot, robot_node_id="s1-a")

    await handler.execute(command(action="mobility.ground.stop", parameters={}))

    assert robot.stops == ["fabric_command"]
    assert robot.velocities == []


@pytest.mark.asyncio
async def test_adapter_validates_and_deduplicates_native_led_commands() -> None:
    robot = RecordingRobot()
    handler = RobotCommandHandler(robot, robot_node_id="s1-a")
    resolved = command(
        action="robot.light.set",
        parameters={"red": 0, "green": 180, "blue": 255},
    )

    first = await handler.execute(resolved)
    second = await handler.execute(resolved)

    assert first.duplicate is False
    assert second.duplicate is True
    assert robot.lights == [
        {
            "red": 0,
            "green": 180,
            "blue": 255,
            "idempotencyKey": resolved.idempotencyKey,
        }
    ]


@pytest.mark.parametrize(
    "parameters",
    [
        {"red": -1, "green": 0, "blue": 0},
        {"red": 0, "green": 0, "blue": 256},
        {"red": 0.5, "green": 0, "blue": 0},
        {"red": True, "green": 0, "blue": 0},
        {"red": 0, "green": 0},
    ],
)
def test_adapter_rejects_invalid_led_channels(parameters: dict[str, object]) -> None:
    robot = RecordingRobot()
    handler = RobotCommandHandler(robot, robot_node_id="s1-a")

    with pytest.raises(ValueError):
        handler.validate(command(action="robot.light.set", parameters=parameters))
