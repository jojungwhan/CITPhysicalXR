from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cit_protocol import (
    CreateInteractionSessionRequest,
    FabricEventEnvelope,
    FabricResolvedCommand,
    IntegrationNode,
)
from cit_robomaster_leap import (
    GESTURE_CAPABILITY,
    PLUGIN_ID,
    ROBOT_VELOCITY_CAPABILITY,
    UPSTREAM_REVISION,
    build_manifest,
    build_nodes,
    gesture_ground_robot_course_pack,
)
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
        ROBOT_VELOCITY_CAPABILITY,
        "mobility.ground.stop",
    }
    assert robot.publishedCapabilities[0].name == "telemetry.motion.commanded"
    assert leap.nodeId != robot.nodeId
    leap_metadata = leap.metadata.model_dump(mode="json")
    robot_metadata = robot.metadata.model_dump(mode="json")
    assert leap_metadata["upstreamRevision"] == UPSTREAM_REVISION
    assert leap_metadata["semanticEventsOnly"] is True
    assert robot_metadata["staleWatchdogMilliseconds"] == 200


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
