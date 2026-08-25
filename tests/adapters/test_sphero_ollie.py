from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from cit_protocol import FabricResolvedCommand
from cit_sphero_ollie.discovery import (
    candidate_id,
    candidates_from_advertisements,
    is_ollie_name,
)
from cit_sphero_ollie.fabric_bridge import OllieCommandHandler
from cit_sphero_ollie.fabric_contract import build_manifest, build_node
from cit_sphero_ollie.models import SpheroAdvertisement
from cit_sphero_ollie.policy import (
    OLLIE_DEADMAN_MILLISECONDS,
    OLLIE_MAX_SPEED_VALUE,
    vector_to_roll,
)
from cit_sphero_ollie.transport import FakeOllieTransport, Spherov2OllieTransport


def _command(
    action: str,
    parameters: dict[str, object],
    *,
    idempotency_key: str | None = None,
) -> FabricResolvedCommand:
    now = datetime.now(UTC)
    return FabricResolvedCommand.model_validate(
        {
            "commandId": str(uuid4()),
            "requestMessageId": str(uuid4()),
            "schemaVersion": "1.0",
            "sessionId": "monitoring-a",
            "targetNodeId": "sphero-ollie-aabbccddeeff",
            "action": action,
            "parameters": parameters,
            "priority": "instructor_override",
            "idempotencyKey": idempotency_key or str(uuid4()),
            "requestedAt": now,
            "expiresAt": now + timedelta(seconds=2),
            "safetyProfile": "classroom-ground-robot",
            "correlationId": str(uuid4()),
        }
    )


def test_discovery_accepts_only_exact_ollie_names_and_hides_addresses() -> None:
    advertisements = [
        SpheroAdvertisement(name="2B-A1F9", address="AA:BB:CC:DD:EE:01", rssi=-55),
        SpheroAdvertisement(name="2b-a1f9", address="AA:BB:CC:DD:EE:01", rssi=-80),
        SpheroAdvertisement(name="Ollie", address="AA:BB:CC:DD:EE:02"),
        SpheroAdvertisement(name="2B-12345", address="AA:BB:CC:DD:EE:03"),
    ]

    robots = candidates_from_advertisements(advertisements)

    assert is_ollie_name("2B-A1F9") is True
    assert is_ollie_name("Ollie") is False
    assert len(robots) == 1
    assert robots[0].display_name == "2B-A1F9"
    assert robots[0].signal_percent == 90
    assert robots[0].candidate_id == candidate_id("AA:BB:CC:DD:EE:01")
    assert robots[0].candidate_id.startswith("sphero-ollie-")
    assert "address" not in robots[0].public_dict()


def test_ollie_vector_mapping_is_conservative_and_bounded() -> None:
    assert vector_to_roll(0.05, 0, 0).heading_degrees == 0
    assert vector_to_roll(0, 0.05, 0).heading_degrees == 90
    assert vector_to_roll(-0.05, 0, 0).heading_degrees == 180
    assert vector_to_roll(0, -0.05, 0).heading_degrees == 270
    assert vector_to_roll(0.10, 0, 0).speed_value == OLLIE_MAX_SPEED_VALUE
    with pytest.raises(ValueError, match=r"0\.10"):
        vector_to_roll(0.10, 0.10, 0)
    with pytest.raises(ValueError, match="angular velocity"):
        vector_to_roll(0.05, 0, 0.1)


def test_ollie_deadman_is_local_and_bounded() -> None:
    assert OLLIE_DEADMAN_MILLISECONDS == 750


@pytest.mark.asyncio
async def test_ollie_hardware_color_uses_main_led_only() -> None:
    calls: list[tuple[int, int, int]] = []

    class RecordingApi:
        def set_main_led(self, color: Any) -> None:
            calls.append((color.r, color.g, color.b))

    transport = Spherov2OllieTransport(
        "sphero-ollie-aabbccddeeff",
        color_factory=lambda red, green, blue: SimpleNamespace(r=red, g=green, b=blue),
    )
    transport._connected = True
    transport._api = RecordingApi()

    await transport.set_color(10, 20, 30)

    assert calls == [(10, 20, 30)]


def test_manifest_and_node_expose_independent_bounded_ollie_capabilities() -> None:
    node = build_node(
        node_id="sphero-ollie-aabbccddeeff",
        display_name="2B-A1F9",
        at=datetime.now(UTC),
        host_id="host-a",
        site_id="site-a",
        room_id="room-a",
        simulated=True,
    )

    assert build_manifest().pluginId == "cit.sphero-ollie"
    assert node.metadata.model_dump(mode="json")["model"] == "sphero-ollie"
    assert {capability.name for capability in node.consumedCapabilities} == {
        "mobility.ground.set_velocity",
        "mobility.ground.nudge",
        "mobility.ground.demonstration.start",
        "mobility.ground.stop",
        "robot.light.set",
        "sphero.aim.reset",
    }
    assert node.metadata.model_dump(mode="json")["watchdogMilliseconds"] == 750


@pytest.mark.asyncio
async def test_command_replay_does_not_repeat_ollie_physical_action() -> None:
    transport = FakeOllieTransport()
    await transport.connect()
    handler = OllieCommandHandler(
        node_id="sphero-ollie-aabbccddeeff",
        transport=transport,
    )
    command = _command("robot.light.set", {"red": 10, "green": 20, "blue": 30})

    _, first_replayed = await handler.execute(command)
    _, second_replayed = await handler.execute(command)

    assert first_replayed is False
    assert second_replayed is True
    assert transport.commands == [("color", (10, 20, 30))]


@pytest.mark.asyncio
async def test_ollie_deadman_and_aim_reset_force_a_stop() -> None:
    transport = FakeOllieTransport()
    await transport.connect()
    handler = OllieCommandHandler(
        node_id="sphero-ollie-aabbccddeeff",
        transport=transport,
    )
    await handler.execute(
        _command(
            "mobility.ground.set_velocity",
            {
                "forwardMetersPerSecond": 0,
                "rightMetersPerSecond": 0.05,
                "clockwiseRadiansPerSecond": 0,
            },
        )
    )

    assert await handler.deadman_tick(now=float("inf")) is True
    details, replayed = await handler.execute(_command("sphero.aim.reset", {}))

    assert replayed is False
    assert details["safeState"] == "stopped"
    assert [command[0] for command in transport.commands] == [
        "velocity",
        "stop",
        "stop",
        "reset_aim",
    ]
