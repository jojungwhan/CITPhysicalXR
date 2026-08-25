from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cit_protocol import FabricResolvedCommand
from cit_wonder_workshop.discovery import (
    ROBOT_SERVICE_UUID,
    candidate_id,
    candidates_from_advertisements,
)
from cit_wonder_workshop.fabric_bridge import WonderCommandHandler
from cit_wonder_workshop.fabric_contract import build_manifest, build_node
from cit_wonder_workshop.models import WonderAdvertisement, WonderRobotModel
from cit_wonder_workshop.protocol import (
    decode_common_sensor,
    drive_packet,
    head_packets,
    stop_packet,
)
from cit_wonder_workshop.transport import FakeWonderTransport


def _command(
    action: str,
    parameters: dict[str, object],
    *,
    node_id: str = "wonder-dash-aabbccddeeff",
    idempotency_key: str | None = None,
) -> FabricResolvedCommand:
    now = datetime.now(UTC)
    return FabricResolvedCommand.model_validate(
        {
            "commandId": str(uuid4()),
            "requestMessageId": str(uuid4()),
            "schemaVersion": "1.0",
            "sessionId": "monitoring-a",
            "targetNodeId": node_id,
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


def test_discovery_classifies_named_dash_and_dot_without_exposing_addresses() -> None:
    advertisements = [
        WonderAdvertisement(
            name="Dash-CIT-A",
            address="AA:BB:CC:DD:EE:01",
            rssi=-55,
            service_uuids=(ROBOT_SERVICE_UUID.upper(),),
        ),
        WonderAdvertisement(
            name="Dot",
            address="AA:BB:CC:DD:EE:02",
            rssi=-75,
        ),
        WonderAdvertisement(name="Headphones", address="AA:BB:CC:DD:EE:03"),
    ]

    robots = candidates_from_advertisements(advertisements)

    assert [(robot.model, robot.signal_percent) for robot in robots] == [
        (WonderRobotModel.DASH, 90),
        (WonderRobotModel.DOT, 50),
    ]
    assert robots[0].candidate_id == candidate_id(WonderRobotModel.DASH, "AA:BB:CC:DD:EE:01")
    assert "address" not in robots[0].public_dict()


def test_protocol_has_explicit_stop_and_omits_raw_microphone_data() -> None:
    packet = bytearray(20)
    packet[7] = 222
    packet[8] = 0x10
    packet[11] = 0x31

    decoded = decode_common_sensor(bytes(packet))

    assert stop_packet() == bytes((0x02, 0, 0, 0))
    assert drive_packet(200, 0) == bytes((0x02, 200, 0, 0))
    assert drive_packet(-200, 0) == bytes((0x02, 200, 128, 0))
    assert drive_packet(0, -200) == bytes((0x02, 0, 200, 128))
    with pytest.raises(ValueError, match="cannot combine"):
        drive_packet(100, 100)
    assert head_packets(-35, 10) == (bytes((0x06, 221)), bytes((0x07, 10)))
    assert decoded["mainButtonPressed"] is True
    assert decoded["clapDetected"] is True
    assert "micLevel" not in decoded
    assert 222 not in decoded.values()


def test_nodes_advertise_only_model_supported_controls() -> None:
    now = datetime.now(UTC)
    dash = build_node(
        node_id="wonder-dash-a",
        display_name="Dash A",
        model=WonderRobotModel.DASH,
        at=now,
        host_id="host-a",
        site_id="site-a",
        room_id="room-a",
        simulated=True,
    )
    dot = build_node(
        node_id="wonder-dot-a",
        display_name="Dot A",
        model=WonderRobotModel.DOT,
        at=now,
        host_id="host-a",
        site_id="site-a",
        room_id="room-a",
        simulated=True,
    )

    assert build_manifest().pluginId == "cit.wonder-workshop"
    assert "mobility.ground.set_velocity" in {
        capability.name for capability in dash.consumedCapabilities
    }
    assert "mobility.ground.nudge" in {capability.name for capability in dash.consumedCapabilities}
    assert "mobility.ground.demonstration.start" in {
        capability.name for capability in dash.consumedCapabilities
    }
    dash_velocity = next(
        capability
        for capability in dash.consumedCapabilities
        if capability.name == "mobility.ground.set_velocity"
    )
    assert dash_velocity.constraints.model_dump()["simultaneousLinearAngular"] is False
    assert {capability.name for capability in dot.consumedCapabilities} == {
        "robot.light.set",
        "media.audio.cue.play",
    }


@pytest.mark.asyncio
async def test_dash_translates_structured_turn_and_stop_but_dot_does_not_advertise_it() -> None:
    transport = FakeWonderTransport(WonderRobotModel.DASH)
    await transport.connect()
    handler = WonderCommandHandler(
        node_id="wonder-dash-aabbccddeeff",
        model=WonderRobotModel.DASH,
        transport=transport,
    )

    await handler.execute(_command("mobility.ground.nudge", {"direction": "right"}))
    await handler.execute(_command("mobility.ground.nudge", {"direction": "stop"}))

    assert transport.commands == [
        ("velocity", (0.0, 0.0, 0.4)),
        ("stop", ()),
    ]


@pytest.mark.asyncio
async def test_dot_rejects_motion_and_dash_replays_without_duplicate_action() -> None:
    dot_transport = FakeWonderTransport(WonderRobotModel.DOT)
    await dot_transport.connect()
    dot_handler = WonderCommandHandler(
        node_id="wonder-dot-aabbccddeeff",
        model=WonderRobotModel.DOT,
        transport=dot_transport,
    )
    with pytest.raises(ValueError, match="Dot does not expose"):
        await dot_handler.execute(
            _command(
                "mobility.ground.set_velocity",
                {
                    "forwardMetersPerSecond": 0.1,
                    "rightMetersPerSecond": 0,
                    "clockwiseRadiansPerSecond": 0,
                },
                node_id="wonder-dot-aabbccddeeff",
            )
        )

    dash_transport = FakeWonderTransport(WonderRobotModel.DASH)
    await dash_transport.connect()
    dash_handler = WonderCommandHandler(
        node_id="wonder-dash-aabbccddeeff",
        model=WonderRobotModel.DASH,
        transport=dash_transport,
    )
    command = _command("robot.light.set", {"red": 10, "green": 20, "blue": 30})
    _, first_replayed = await dash_handler.execute(command)
    _, second_replayed = await dash_handler.execute(command)

    assert first_replayed is False
    assert second_replayed is True
    assert dash_transport.commands == [("color", (10, 20, 30))]


@pytest.mark.asyncio
async def test_dash_deadman_stops_one_expired_velocity_command() -> None:
    transport = FakeWonderTransport(WonderRobotModel.DASH)
    await transport.connect()
    handler = WonderCommandHandler(
        node_id="wonder-dash-aabbccddeeff",
        model=WonderRobotModel.DASH,
        transport=transport,
    )
    await handler.execute(
        _command(
            "mobility.ground.set_velocity",
            {
                "forwardMetersPerSecond": 0.12,
                "rightMetersPerSecond": 0,
                "clockwiseRadiansPerSecond": 0,
            },
        )
    )

    assert await handler.deadman_tick(now=float("inf")) is True
    assert await handler.deadman_tick(now=float("inf")) is False
    assert transport.commands == [
        ("velocity", (0.12, 0.0, 0.0)),
        ("stop", ()),
    ]


@pytest.mark.asyncio
async def test_dash_rejects_mixed_linear_and_angular_velocity() -> None:
    transport = FakeWonderTransport(WonderRobotModel.DASH)
    await transport.connect()
    handler = WonderCommandHandler(
        node_id="wonder-dash-aabbccddeeff",
        model=WonderRobotModel.DASH,
        transport=transport,
    )

    with pytest.raises(ValueError, match="cannot combine"):
        await handler.execute(
            _command(
                "mobility.ground.set_velocity",
                {
                    "forwardMetersPerSecond": 0.1,
                    "rightMetersPerSecond": 0,
                    "clockwiseRadiansPerSecond": 0.2,
                },
            )
        )

    assert transport.commands == []
