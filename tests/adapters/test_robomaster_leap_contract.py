from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from cit_protocol import (
    CreateInteractionSessionRequest,
    FabricEventEnvelope,
    FabricResolvedCommand,
    IntegrationNode,
)
from cit_robomaster_leap import (
    FLIGHT_SEQUENCE_INTENT_CAPABILITY,
    GESTURE_CAPABILITY,
    LEAP_PLUGIN_ID,
    PLUGIN_ID,
    ROBOMASTER_PLUGIN_ID,
    ROBOT_LIGHT_CAPABILITY,
    ROBOT_NUDGE_CAPABILITY,
    ROBOT_VELOCITY_CAPABILITY,
    UPSTREAM_REVISION,
    build_leap_manifest,
    build_leap_node,
    build_manifest,
    build_nodes,
    build_robot_manifest,
    build_robot_node,
    gesture_ground_robot_course_pack,
)
from cit_robomaster_leap.backend import GestureSignal
from cit_robomaster_leap.bridge import BridgeConfiguration, FabricRobotLeapBridge
from cit_robomaster_leap.independent_bridges import LeapFlightSequenceIntentProjector
from cit_robomaster_leap.robot_commands import RobotCommandHandler
from cit_runtime.fabric import FabricDispatchOutcome, InteractionFabric
from cit_runtime.fabric_course import (
    gesture_ground_robot_course_pack as runtime_course_pack,
)
from cit_runtime.fabric_repository import SQLiteFabricRepository

NOW = datetime(2026, 8, 21, 3, 0, 0, tzinfo=UTC)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_upstream_characterization_fixture_pins_the_wrapped_public_boundaries() -> None:
    fixture = json.loads(
        (
            REPOSITORY_ROOT / "adapters" / "robomaster-leap" / "fixtures" / "upstream-contract.json"
        ).read_text(encoding="utf-8")
    )

    assert fixture["revision"] == UPSTREAM_REVISION
    assert fixture["modules"]["gesture"].endswith("GestureController")
    assert fixture["modules"]["leap"].endswith("LeapSource")
    assert fixture["safety"] == {
        "maximumTranslationMetersPerSecond": 0.35,
        "maximumYawDegreesPerSecond": 35.0,
        "staleAfterMilliseconds": 200,
        "movingKeepaliveMilliseconds": 150,
        "robotTimeoutMilliseconds": 350,
    }


def test_manifest_exposes_independent_input_and_robot_nodes() -> None:
    manifest = build_manifest()
    leap, robot = build_nodes(
        at=NOW,
        host_id="edge-host-a",
        site_id="local-site",
        room_id="local-room",
        leap_node_id="leap-a",
        robot_node_id="s1-a",
        leap_simulated=False,
        robot_simulated=False,
        robot_mode="sdk",
        preferred_hand="right",
    )

    assert manifest.pluginId == PLUGIN_ID
    assert leap.publishedCapabilities[0].name == GESTURE_CAPABILITY
    assert leap.consumedCapabilities == []
    assert {item.name for item in robot.consumedCapabilities} == {
        ROBOT_NUDGE_CAPABILITY,
        "mobility.ground.demonstration.start",
        ROBOT_VELOCITY_CAPABILITY,
        "mobility.ground.stop",
        ROBOT_LIGHT_CAPABILITY,
    }
    assert robot.publishedCapabilities[0].name == "telemetry.motion.commanded"

    app_robot = build_robot_node(
        at=NOW,
        host_id="edge-host-a",
        site_id="local-site",
        room_id="local-room",
        node_id="s1-app-a",
        simulated=False,
        robot_mode="s1-app",
    )
    assert ROBOT_LIGHT_CAPABILITY not in {
        capability.name for capability in app_robot.consumedCapabilities
    }
    assert leap.nodeId != robot.nodeId
    leap_metadata = leap.metadata.model_dump(mode="json")
    robot_metadata = robot.metadata.model_dump(mode="json")
    assert leap_metadata["upstreamRevision"] == UPSTREAM_REVISION
    assert leap_metadata["semanticEventsOnly"] is True
    assert robot_metadata["staleWatchdogMilliseconds"] == 200


def test_independent_process_contracts_have_independent_plugin_identities() -> None:
    leap = build_leap_node(
        at=NOW,
        host_id="edge-host-a",
        site_id="local-site",
        room_id="local-room",
        node_id="leap-a",
        simulated=True,
        preferred_hand="right",
    )
    robot = build_robot_node(
        at=NOW,
        host_id="edge-host-a",
        site_id="local-site",
        room_id="local-room",
        node_id="s1-a",
        simulated=True,
        robot_mode="dry-run",
    )

    assert build_leap_manifest().pluginId == leap.pluginId == LEAP_PLUGIN_ID
    assert build_robot_manifest().pluginId == robot.pluginId == ROBOMASTER_PLUGIN_ID
    assert leap.consumedCapabilities == []
    assert robot.publishedCapabilities[0].name == "telemetry.motion.commanded"


@pytest.mark.asyncio
async def test_robomaster_translates_structured_nudge_and_stop_inside_adapter() -> None:
    class RecordingBackend:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

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
            self.calls.append(("velocity", (forward, right, clockwise)))
            return {"accepted": True}

        async def set_light(
            self,
            *,
            red: int,
            green: int,
            blue: int,
            idempotency_key: str,
        ) -> dict[str, object]:
            self.calls.append(("light", (red, green, blue)))
            return {"accepted": True}

        async def stop(self, *, reason: str) -> None:
            self.calls.append(("stop", reason))

        async def close(self) -> None:
            return None

    def command(direction: str) -> FabricResolvedCommand:
        requested_at = datetime.now(UTC)
        return FabricResolvedCommand.model_validate(
            {
                "commandId": str(uuid4()),
                "requestMessageId": str(uuid4()),
                "schemaVersion": "1.0",
                "sessionId": "session-a",
                "targetNodeId": "s1-a",
                "action": ROBOT_NUDGE_CAPABILITY,
                "parameters": {"direction": direction},
                "priority": "lesson_automation",
                "idempotencyKey": str(uuid4()),
                "requestedAt": requested_at,
                "expiresAt": requested_at + timedelta(seconds=1),
                "safetyProfile": "classroom-ground-robot",
                "correlationId": str(uuid4()),
            }
        )

    backend = RecordingBackend()
    handler = RobotCommandHandler(backend, robot_node_id="s1-a")

    await handler.execute(command("left"))
    await handler.execute(command("stop"))

    assert backend.calls == [
        ("velocity", (0.0, -0.12, 0.0)),
        ("stop", "fabric_nudge_stop"),
    ]


def test_leap_emits_one_fleet_intent_on_each_deliberate_driving_transition() -> None:
    manifest = build_leap_manifest()
    leap = build_leap_node(
        at=NOW,
        host_id="edge-host-a",
        site_id="local-site",
        room_id="local-room",
        node_id="leap-a",
        simulated=False,
        preferred_hand="right",
    )
    projector = LeapFlightSequenceIntentProjector()
    driving = GestureSignal(
        sequence=1,
        monotonic_nanoseconds=1,
        state="DRIVING",
        reason="engaged - move hand while holding pinch",
        confidence=1.0,
        forward_meters_per_second=0,
        right_meters_per_second=0,
        clockwise_radians_per_second=0,
        tracking=True,
    )
    waiting = GestureSignal(
        sequence=2,
        monotonic_nanoseconds=2,
        state="WAITING",
        reason="pinch released - stopped",
        confidence=1.0,
        forward_meters_per_second=0,
        right_meters_per_second=0,
        clockwise_radians_per_second=0,
        tracking=True,
    )

    assert FLIGHT_SEQUENCE_INTENT_CAPABILITY in {
        item.name for item in manifest.publishedCapabilities
    }
    assert FLIGHT_SEQUENCE_INTENT_CAPABILITY in {item.name for item in leap.publishedCapabilities}
    assert projector.observe(driving) == {
        "intent": "start",
        "inputModality": "leap_pinch",
        "gestureState": "DRIVING",
        "vendorSequence": 1,
    }
    assert projector.observe(driving) is None
    assert projector.observe(waiting) is None
    assert projector.observe(driving) is not None


@pytest.mark.asyncio
async def test_compatibility_bridge_projects_the_same_bounded_fleet_intent() -> None:
    class RecordingSocket:
        def __init__(self) -> None:
            self.frames: list[dict[str, object]] = []

        async def send(self, message: str) -> None:
            self.frames.append(json.loads(message))

        async def recv(self) -> str:
            raise AssertionError("receive is not used")

    bridge = FabricRobotLeapBridge(
        BridgeConfiguration(
            adapter_url="ws://127.0.0.1:8766/api/v1/adapters/connect",
            adapter_token="test-token",
            fabric_origin="http://127.0.0.1:8766",
            session_id="session-a",
            site_id="local-site",
            room_id="local-room",
            host_id="edge-host-a",
            leap_node_id="leap-a",
            robot_node_id="robot-a",
            activation_file=Path("active.signal"),
            input_mode="demo",
            robot_mode="dry-run",
            preferred_hand="right",
        ),
        robot=object(),  # type: ignore[arg-type]
        leap=None,
    )
    socket = RecordingSocket()

    await bridge._publish_gesture(
        socket,
        GestureSignal(
            sequence=4,
            monotonic_nanoseconds=4,
            state="DRIVING",
            reason="engaged",
            confidence=1.0,
            forward_meters_per_second=0,
            right_meters_per_second=0,
            clockwise_radians_per_second=0,
            tracking=True,
        ),
    )

    assert [frame["event"]["topic"] for frame in socket.frames] == [  # type: ignore[index]
        GESTURE_CAPABILITY,
        FLIGHT_SEQUENCE_INTENT_CAPABILITY,
    ]
    intent = socket.frames[1]["event"]
    assert intent["payload"] == {  # type: ignore[index]
        "intent": "start",
        "inputModality": "leap_pinch",
        "gestureState": "DRIVING",
        "vendorSequence": 4,
    }


def test_packaged_yaml_runtime_recipe_and_adapter_contract_do_not_drift() -> None:
    from cit_runtime.fabric_course import load_course_pack

    yaml_pack = load_course_pack(
        REPOSITORY_ROOT / "course-packs" / "gesture-ground-robot" / "course-pack.yaml"
    )

    assert yaml_pack == runtime_course_pack() == gesture_ground_robot_course_pack()


@pytest.mark.asyncio
async def test_semantic_gesture_routes_to_a_capability_selected_robot() -> None:
    dispatched: list[tuple[FabricResolvedCommand, IntegrationNode]] = []

    async def dispatch(
        command: FabricResolvedCommand,
        node: IntegrationNode,
    ) -> FabricDispatchOutcome:
        dispatched.append((command, node))
        return FabricDispatchOutcome(accepted=True)

    manifest = build_manifest()
    leap, robot = build_nodes(
        at=NOW,
        host_id="edge-host-a",
        site_id="local-site",
        room_id="local-room",
        leap_node_id="leap-sim-a",
        robot_node_id="s1-sim-a",
        leap_simulated=True,
        robot_simulated=True,
        robot_mode="dry-run",
        preferred_hand="right",
    )
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW)
        fabric.set_dispatcher(dispatch)
        fabric.register_plugin_and_nodes(manifest, (leap, robot))
        fabric.install_course_pack(runtime_course_pack(), actor_id="system.test")
        session = fabric.create_session(
            CreateInteractionSessionRequest.model_validate(
                {
                    "coursePackId": "gesture-ground-robot",
                    "coursePackVersion": "1.0.0",
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "mode": "simulation",
                }
            ),
            actor_id="instructor-a",
        )
        fabric.assign_role(
            session.sessionId,
            "gesture_input",
            leap.nodeId,
            actor_id="instructor-a",
        )
        fabric.assign_role(
            session.sessionId,
            "student_robot",
            robot.nodeId,
            actor_id="instructor-a",
        )
        fabric.transition_session(session.sessionId, "start", actor_id="instructor-a")
        result = await fabric.ingest_event(
            FabricEventEnvelope.model_validate(
                {
                    "messageId": "a745f68c-fddf-4f1d-9e80-ee38a8a7904e",
                    "schemaVersion": "1.0",
                    "messageType": "event",
                    "topic": GESTURE_CAPABILITY,
                    "sourceNodeId": leap.nodeId,
                    "sourceCapability": GESTURE_CAPABILITY,
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "sessionId": session.sessionId,
                    "timestamp": NOW,
                    "monotonicTimestamp": 123,
                    "sequence": 1,
                    "correlationId": "gesture-a",
                    "confidence": 0.99,
                    "ttlMs": 250,
                    "dataClassification": "operational",
                    "payload": {
                        "forwardMetersPerSecond": 0.2,
                        "rightMetersPerSecond": -0.1,
                        "clockwiseRadiansPerSecond": 0.3,
                    },
                }
            )
        )

    command = dispatched[0][0]
    assert command.action == ROBOT_VELOCITY_CAPABILITY
    assert command.targetNodeId == robot.nodeId
    assert command.parameters.model_dump(mode="json") == {
        "forwardMetersPerSecond": 0.2,
        "rightMetersPerSecond": -0.1,
        "clockwiseRadiansPerSecond": 0.3,
    }
    assert [item.stage.value for item in result.command_lifecycle] == [
        "PROPOSED",
        "VALIDATED",
        "AUTHORIZED",
        "DISPATCHED",
    ]
