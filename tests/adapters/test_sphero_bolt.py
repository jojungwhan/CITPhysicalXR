from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from cit_protocol import FabricResolvedCommand
from cit_sphero_bolt.discovery import (
    candidate_id,
    candidates_from_advertisements,
    is_bolt_name,
)
from cit_sphero_bolt.fabric_bridge import SpheroCommandHandler
from cit_sphero_bolt.fabric_contract import build_manifest, build_node
from cit_sphero_bolt.models import SpheroAdvertisement
from cit_sphero_bolt.policy import (
    SPHERO_DEADMAN_MILLISECONDS,
    SPHERO_MAX_SPEED_VALUE,
    vector_to_roll,
)
from cit_sphero_bolt.transport import (
    FakeSpheroTransport,
    Spherov2BleakTransport,
    _with_response_validation,
)


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
            "targetNodeId": "sphero-bolt-aabbccddeeff",
            "action": action,
            "parameters": parameters,
            "priority": "instructor_override",
            "idempotencyKey": idempotency_key or str(uuid4()),
            "requestedAt": now,
            "expiresAt": now + timedelta(seconds=2),
            "safetyProfile": "classroom-drone-monitoring",
            "correlationId": str(uuid4()),
        }
    )


def test_discovery_accepts_only_exact_bolt_names_and_hides_addresses() -> None:
    advertisements = [
        SpheroAdvertisement(name="SB-G1Q9", address="AA:BB:CC:DD:EE:01", rssi=-55),
        SpheroAdvertisement(name="sb-g1q9", address="AA:BB:CC:DD:EE:01", rssi=-80),
        SpheroAdvertisement(name="Sphero BOLT", address="AA:BB:CC:DD:EE:02"),
        SpheroAdvertisement(name="SB-12345", address="AA:BB:CC:DD:EE:03"),
    ]

    robots = candidates_from_advertisements(advertisements)

    assert is_bolt_name("SB-G1Q9") is True
    assert is_bolt_name("Sphero BOLT") is False
    assert len(robots) == 1
    assert robots[0].display_name == "SB-G1Q9"
    assert robots[0].signal_percent == 90
    assert robots[0].candidate_id == candidate_id("AA:BB:CC:DD:EE:01")
    assert "address" not in robots[0].public_dict()


def test_vector_mapping_is_omnidirectional_and_bounded() -> None:
    assert vector_to_roll(0.1, 0, 0).heading_degrees == 0
    assert vector_to_roll(0, 0.1, 0).heading_degrees == 90
    assert vector_to_roll(-0.1, 0, 0).heading_degrees == 180
    assert vector_to_roll(0, -0.1, 0).heading_degrees == 270
    assert vector_to_roll(0.2, 0, 0).speed_value == SPHERO_MAX_SPEED_VALUE
    with pytest.raises(ValueError, match=r"0\.20"):
        vector_to_roll(0.2, 0.2, 0)
    with pytest.raises(ValueError, match="angular velocity"):
        vector_to_roll(0.1, 0, 0.1)


def test_bolt_nudge_has_a_visible_but_bounded_deadman_window() -> None:
    assert SPHERO_DEADMAN_MILLISECONDS == 750


def test_vendor_response_validation_propagates_a_device_rejection() -> None:
    class RejectedResponse:
        def check_error(self) -> None:
            raise RuntimeError("command_failed")

    execute = _with_response_validation(lambda _packet: RejectedResponse())

    with pytest.raises(RuntimeError, match="command_failed"):
        execute(object())


@pytest.mark.asyncio
async def test_hardware_color_bypasses_broken_bolt_capability_detection() -> None:
    calls: list[tuple[str, tuple[int, int, int]]] = []

    class RecordingApi:
        def set_front_led(self, color: Any) -> None:
            calls.append(("front", (color.r, color.g, color.b)))

        def set_back_led(self, color: Any) -> None:
            calls.append(("back", (color.r, color.g, color.b)))

    class RecordingToy:
        def set_compressed_frame_player_one_color(self, red: int, green: int, blue: int) -> None:
            calls.append(("matrix", (red, green, blue)))

    transport = Spherov2BleakTransport(
        "sphero-aabbccddeeff",
        color_factory=lambda red, green, blue: SimpleNamespace(r=red, g=green, b=blue),
    )
    transport._connected = True
    transport._api = RecordingApi()
    transport._toy = RecordingToy()

    await transport.set_color(10, 20, 30)

    assert calls == [
        ("matrix", (10, 20, 30)),
        ("front", (10, 20, 30)),
        ("back", (10, 20, 30)),
    ]


def test_manifest_and_node_expose_only_bounded_bolt_capabilities() -> None:
    node = build_node(
        node_id="sphero-bolt-aabbccddeeff",
        display_name="SB-G1Q9",
        at=datetime.now(UTC),
        host_id="host-a",
        site_id="site-a",
        room_id="room-a",
        simulated=True,
    )

    assert build_manifest().pluginId == "cit.sphero-bolt"
    assert {capability.name for capability in node.consumedCapabilities} == {
        "mobility.ground.set_velocity",
        "mobility.ground.nudge",
        "mobility.ground.demonstration.start",
        "mobility.ground.stop",
        "robot.light.set",
        "sphero.aim.reset",
    }
    velocity = next(
        capability
        for capability in node.consumedCapabilities
        if capability.name == "mobility.ground.set_velocity"
    )
    constraints = velocity.constraints.model_dump(mode="json")
    assert constraints["arguments"]["clockwiseRadiansPerSecond"] == {
        "minimum": 0,
        "maximum": 0,
    }
    assert node.metadata.model_dump(mode="json")["watchdogMilliseconds"] == 750


@pytest.mark.asyncio
async def test_structured_nudge_maps_left_and_stop_without_vendor_data() -> None:
    transport = FakeSpheroTransport()
    await transport.connect()
    handler = SpheroCommandHandler(
        node_id="sphero-bolt-aabbccddeeff",
        transport=transport,
    )

    details, _ = await handler.execute(_command("mobility.ground.nudge", {"direction": "left"}))
    stopped, _ = await handler.execute(_command("mobility.ground.nudge", {"direction": "stop"}))

    assert details["direction"] == "left"
    assert stopped == {"direction": "stop", "safeState": "stopped"}
    assert transport.commands[0][0] == "velocity"
    assert transport.commands[0][1][:3] == (0.0, -0.12, 0.0)
    assert transport.commands[1] == ("stop", ())


@pytest.mark.asyncio
async def test_command_replay_does_not_repeat_physical_action() -> None:
    transport = FakeSpheroTransport()
    await transport.connect()
    handler = SpheroCommandHandler(
        node_id="sphero-bolt-aabbccddeeff",
        transport=transport,
    )
    command = _command("robot.light.set", {"red": 10, "green": 20, "blue": 30})

    _, first_replayed = await handler.execute(command)
    _, second_replayed = await handler.execute(command)

    assert first_replayed is False
    assert second_replayed is True
    assert transport.commands == [("color", (10, 20, 30))]


@pytest.mark.asyncio
async def test_deadman_and_aim_reset_both_force_a_stop() -> None:
    transport = FakeSpheroTransport()
    await transport.connect()
    handler = SpheroCommandHandler(
        node_id="sphero-bolt-aabbccddeeff",
        transport=transport,
    )
    await handler.execute(
        _command(
            "mobility.ground.set_velocity",
            {
                "forwardMetersPerSecond": 0,
                "rightMetersPerSecond": 0.1,
                "clockwiseRadiansPerSecond": 0,
            },
        )
    )

    assert await handler.deadman_tick(now=float("inf")) is True
    assert await handler.deadman_tick(now=float("inf")) is False
    details, replayed = await handler.execute(_command("sphero.aim.reset", {}))

    assert replayed is False
    assert details["safeState"] == "stopped"
    assert [command[0] for command in transport.commands] == [
        "velocity",
        "stop",
        "stop",
        "reset_aim",
    ]


@pytest.mark.asyncio
async def test_adapter_rejects_rotation_and_oversized_translation() -> None:
    transport = FakeSpheroTransport()
    await transport.connect()
    handler = SpheroCommandHandler(
        node_id="sphero-bolt-aabbccddeeff",
        transport=transport,
    )

    with pytest.raises(ValueError, match="angular velocity"):
        await handler.execute(
            _command(
                "mobility.ground.set_velocity",
                {
                    "forwardMetersPerSecond": 0.1,
                    "rightMetersPerSecond": 0,
                    "clockwiseRadiansPerSecond": 0.1,
                },
            )
        )
    with pytest.raises(ValueError, match=r"0\.20"):
        await handler.execute(
            _command(
                "mobility.ground.set_velocity",
                {
                    "forwardMetersPerSecond": 0.2,
                    "rightMetersPerSecond": 0.2,
                    "clockwiseRadiansPerSecond": 0,
                },
            )
        )

    assert transport.commands == []
