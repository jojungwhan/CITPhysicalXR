from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cit_integration_sdk import capability_descriptor
from cit_protocol import (
    CreateInteractionSessionRequest,
    FabricEventEnvelope,
    FabricResolvedCommand,
    IntegrationNode,
    PluginManifest,
)
from cit_runtime.fabric import FabricDispatchOutcome, InteractionFabric
from cit_runtime.fabric_course import load_builtin_course_pack
from cit_runtime.fabric_repository import SQLiteFabricRepository

NOW = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)
CONTROL_CAPABILITY = "interaction.intent.device_control"
NUDGE_CAPABILITY = "mobility.ground.nudge"
DEMONSTRATION_CAPABILITY = "mobility.ground.demonstration.start"
LIGHT_CAPABILITY = "robot.light.set"
FLEET_START_CAPABILITY = "mobility.flight.fleet_sequence.start"
FLEET_STOP_CAPABILITY = "mobility.flight.fleet_sequence.stop"
POWER_SET_CAPABILITY = "power.switch.set"


def _plugin_and_nodes(
    *, physical: bool = False
) -> tuple[PluginManifest, tuple[IntegrationNode, ...]]:
    control = capability_descriptor("device_control_intent", "publish")
    nudge = capability_descriptor("ground_nudge", "consume")
    demonstration = capability_descriptor("ground_demonstration_start", "consume")
    light = capability_descriptor("robot_light_set", "consume")
    fleet_start = capability_descriptor("flight_fleet_sequence_start", "consume")
    fleet_stop = capability_descriptor("flight_fleet_sequence_stop", "consume")
    power_set = capability_descriptor("power_switch_set", "consume")
    manifest = PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": "cit.test-glasses-control",
            "pluginVersion": "1.0.0",
            "runtimeVersion": "test",
            "displayName": "Glasses control test",
            "adapterMode": "out_of_process",
            "configurationSchema": {},
            "publishedCapabilities": [control],
            "consumedCapabilities": [
                nudge,
                demonstration,
                light,
                fleet_start,
                fleet_stop,
                power_set,
            ],
            "requiredPermissions": [],
            "safetyClassification": "bounded_physical",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "included",
        }
    )

    def node(
        node_id: str,
        *,
        published: list[object],
        consumed: list[object],
        safety: str | None = None,
    ) -> IntegrationNode:
        return IntegrationNode.model_validate(
            {
                "schemaVersion": "1.0",
                "nodeId": node_id,
                "pluginId": manifest.pluginId,
                "pluginVersion": manifest.pluginVersion,
                "runtimeVersion": "test",
                "hostId": "host-a",
                "siteId": "local-site",
                "roomId": "local-room",
                "displayName": node_id,
                "connectionState": "connected",
                "healthState": "healthy",
                "physical": physical,
                "simulated": not physical,
                "publishedCapabilities": published,
                "consumedCapabilities": consumed,
                "configurationSchema": {},
                "safetyClassification": safety
                or ("informational" if published else "bounded_physical"),
                "dataClassifications": ["operational"],
                "simulatorAvailable": True,
                "requiredPermissions": [],
                "lastSeenAt": NOW,
                "metadata": {},
            }
        )

    return manifest, (
        node("g2-a", published=[control], consumed=[]),
        node("sphero-a", published=[], consumed=[nudge, demonstration, light]),
        node("lego-a", published=[], consumed=[nudge, demonstration]),
        node(
            "tello-fleet-a",
            published=[],
            consumed=[fleet_start, fleet_stop],
            safety="flight",
        ),
        node(
            "matter-plug-a",
            published=[],
            consumed=[power_set],
            safety="electrical",
        ),
        node(
            "matter-plug-b",
            published=[],
            consumed=[power_set],
            safety="electrical",
        ),
    )


def _event(
    session_id: str,
    *,
    action: str,
    target: str = "ground_outputs",
    confirmed: bool = True,
    sequence: int = 1,
    target_role: str | None = None,
) -> FabricEventEnvelope:
    return FabricEventEnvelope.model_validate(
        {
            "messageId": str(uuid4()),
            "schemaVersion": "1.0",
            "messageType": "event",
            "topic": CONTROL_CAPABILITY,
            "sourceNodeId": "g2-a",
            "sourceCapability": CONTROL_CAPABILITY,
            "siteId": "local-site",
            "roomId": "local-room",
            "sessionId": session_id,
            "timestamp": NOW,
            "monotonicTimestamp": sequence,
            "sequence": sequence,
            "confidence": 1,
            "ttlMs": 5_000,
            "dataClassification": "operational",
            "payload": {
                "action": action,
                "target": target,
                "confirmed": confirmed,
                "inputModality": "voice",
                "deviceKind": "even_g2",
                **({} if target_role is None else {"targetRole": target_role}),
            },
        }
    )


@pytest.mark.asyncio
async def test_one_confirmed_glasses_intent_fans_out_to_assigned_robot_simulators() -> None:
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW)
        dispatched: list[FabricResolvedCommand] = []

        async def dispatch(
            command: FabricResolvedCommand,
            _node: IntegrationNode,
        ) -> FabricDispatchOutcome:
            dispatched.append(command)
            return FabricDispatchOutcome(accepted=True)

        fabric.set_dispatcher(dispatch)
        manifest, nodes = _plugin_and_nodes()
        fabric.register_plugin_and_nodes(manifest, nodes)
        pack = load_builtin_course_pack("glasses-device-control")
        fabric.install_course_pack(pack, actor_id="instructor-a")
        session = fabric.create_session(
            CreateInteractionSessionRequest.model_validate(
                {
                    "coursePackId": pack.coursePackId,
                    "coursePackVersion": pack.version,
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "mode": "simulation",
                }
            ),
            actor_id="instructor-a",
        )
        for role, node_id in (
            ("glasses_input_1", "g2-a"),
            ("ground_output_1", "sphero-a"),
            ("ground_output_2", "lego-a"),
        ):
            fabric.assign_role(
                session.sessionId,
                role,
                node_id,
                actor_id="instructor-a",
            )
        fabric.transition_session(session.sessionId, "start", actor_id="instructor-a")

        result = await fabric.ingest_event(_event(session.sessionId, action="left"))

    assert dispatched, result.command_lifecycle
    assert [command.targetNodeId for command in dispatched] == ["sphero-a", "lego-a"]
    assert {command.action for command in dispatched} == {NUDGE_CAPABILITY}
    assert {command.parameters.model_dump(mode="json")["direction"] for command in dispatched} == {
        "left"
    }
    assert all(command.sourceNodeId == "g2-a" for command in dispatched)
    assert [item.stage.value for item in result.command_lifecycle].count("DISPATCHED") == 2


@pytest.mark.asyncio
async def test_turn_on_all_fans_out_to_every_assigned_output_kind() -> None:
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW)
        dispatched: list[FabricResolvedCommand] = []

        async def dispatch(
            command: FabricResolvedCommand,
            _node: IntegrationNode,
        ) -> FabricDispatchOutcome:
            dispatched.append(command)
            return FabricDispatchOutcome(accepted=True)

        fabric.set_dispatcher(dispatch)
        manifest, nodes = _plugin_and_nodes()
        fabric.register_plugin_and_nodes(manifest, nodes)
        pack = load_builtin_course_pack("glasses-device-control")
        fabric.install_course_pack(pack, actor_id="instructor-a")
        session = fabric.create_session(
            CreateInteractionSessionRequest.model_validate(
                {
                    "coursePackId": pack.coursePackId,
                    "coursePackVersion": pack.version,
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "mode": "simulation",
                }
            ),
            actor_id="instructor-a",
        )
        for role, node_id in (
            ("glasses_input_1", "g2-a"),
            ("ground_output_1", "sphero-a"),
            ("ground_output_2", "lego-a"),
            ("fleet_sequence_controller", "tello-fleet-a"),
            ("power_output_1", "matter-plug-a"),
            ("power_output_2", "matter-plug-b"),
        ):
            fabric.assign_role(session.sessionId, role, node_id, actor_id="instructor-a")
        fabric.transition_session(session.sessionId, "start", actor_id="instructor-a")

        result = await fabric.ingest_event(
            _event(session.sessionId, action="activate", target="all_outputs")
        )

    assert {command.targetNodeId for command in dispatched} == {
        "sphero-a",
        "lego-a",
        "tello-fleet-a",
        "matter-plug-a",
        "matter-plug-b",
    }
    assert [command.action for command in dispatched].count(DEMONSTRATION_CAPABILITY) == 2
    assert [command.action for command in dispatched].count(LIGHT_CAPABILITY) == 1
    assert [command.action for command in dispatched].count(FLEET_START_CAPABILITY) == 1
    assert [command.action for command in dispatched].count(POWER_SET_CAPABILITY) == 2
    assert all(
        command.parameters.model_dump(mode="json") == {"on": True}
        for command in dispatched
        if command.action == POWER_SET_CAPABILITY
    )
    assert [item.stage.value for item in result.command_lifecycle].count("DISPATCHED") == 6


@pytest.mark.asyncio
async def test_exact_g2_menu_role_routes_led_and_bounded_demo_only_to_that_robot() -> None:
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW)
        dispatched: list[FabricResolvedCommand] = []

        async def dispatch(
            command: FabricResolvedCommand,
            _node: IntegrationNode,
        ) -> FabricDispatchOutcome:
            dispatched.append(command)
            return FabricDispatchOutcome(accepted=True)

        fabric.set_dispatcher(dispatch)
        manifest, nodes = _plugin_and_nodes()
        fabric.register_plugin_and_nodes(manifest, nodes)
        pack = load_builtin_course_pack("glasses-device-control")
        fabric.install_course_pack(pack, actor_id="instructor-a")
        session = fabric.create_session(
            CreateInteractionSessionRequest.model_validate(
                {
                    "coursePackId": pack.coursePackId,
                    "coursePackVersion": pack.version,
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "mode": "simulation",
                }
            ),
            actor_id="instructor-a",
        )
        for role, node_id in (
            ("glasses_input_1", "g2-a"),
            ("ground_output_1", "sphero-a"),
            ("ground_output_2", "lego-a"),
        ):
            fabric.assign_role(session.sessionId, role, node_id, actor_id="instructor-a")
        fabric.transition_session(session.sessionId, "start", actor_id="instructor-a")

        await fabric.ingest_event(
            _event(
                session.sessionId,
                action="light",
                target="assigned_output",
                target_role="ground_output_1",
                sequence=1,
            )
        )
        await fabric.ingest_event(
            _event(
                session.sessionId,
                action="demo",
                target="assigned_output",
                target_role="ground_output_1",
                sequence=2,
            )
        )

    assert [command.targetNodeId for command in dispatched] == ["sphero-a", "sphero-a"]
    assert [command.action for command in dispatched] == [
        LIGHT_CAPABILITY,
        DEMONSTRATION_CAPABILITY,
    ]
    assert [command.parameters.model_dump(mode="json") for command in dispatched] == [
        {"red": 0, "green": 180, "blue": 255},
        {"distanceMeters": 0.1},
    ]


@pytest.mark.asyncio
async def test_unconfirmed_glasses_intent_is_recorded_but_cannot_route() -> None:
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW)
        dispatched: list[FabricResolvedCommand] = []

        async def dispatch(
            command: FabricResolvedCommand,
            _node: IntegrationNode,
        ) -> FabricDispatchOutcome:
            dispatched.append(command)
            return FabricDispatchOutcome(accepted=True)

        fabric.set_dispatcher(dispatch)
        manifest, nodes = _plugin_and_nodes()
        fabric.register_plugin_and_nodes(manifest, nodes)
        pack = load_builtin_course_pack("glasses-device-control")
        fabric.install_course_pack(pack, actor_id="instructor-a")
        session = fabric.create_session(
            CreateInteractionSessionRequest.model_validate(
                {
                    "coursePackId": pack.coursePackId,
                    "coursePackVersion": pack.version,
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "mode": "simulation",
                }
            ),
            actor_id="instructor-a",
        )
        fabric.assign_role(
            session.sessionId,
            "glasses_input_1",
            "g2-a",
            actor_id="instructor-a",
        )
        fabric.assign_role(
            session.sessionId,
            "ground_output_1",
            "sphero-a",
            actor_id="instructor-a",
        )
        fabric.transition_session(session.sessionId, "start", actor_id="instructor-a")

        result = await fabric.ingest_event(
            _event(session.sessionId, action="forward", confirmed=False)
        )

    assert result.stored_event is not None
    assert result.command_lifecycle == ()
    assert dispatched == []


@pytest.mark.asyncio
async def test_confirmed_glasses_takeoff_and_land_use_the_bounded_fleet_controller() -> None:
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW, allow_physical=True)
        dispatched: list[FabricResolvedCommand] = []

        async def dispatch(
            command: FabricResolvedCommand,
            _node: IntegrationNode,
        ) -> FabricDispatchOutcome:
            dispatched.append(command)
            return FabricDispatchOutcome(accepted=True)

        fabric.set_dispatcher(dispatch)
        manifest, nodes = _plugin_and_nodes(physical=True)
        fabric.register_plugin_and_nodes(manifest, nodes)
        pack = load_builtin_course_pack("glasses-device-control")
        fabric.install_course_pack(pack, actor_id="instructor-a")
        session = fabric.create_session(
            CreateInteractionSessionRequest.model_validate(
                {
                    "coursePackId": pack.coursePackId,
                    "coursePackVersion": pack.version,
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "mode": "physical",
                }
            ),
            actor_id="instructor-a",
        )
        fabric.assign_role(
            session.sessionId,
            "glasses_input_1",
            "g2-a",
            actor_id="instructor-a",
        )
        fabric.assign_role(
            session.sessionId,
            "fleet_sequence_controller",
            "tello-fleet-a",
            actor_id="instructor-a",
        )
        fabric.transition_session(session.sessionId, "arm", actor_id="instructor-a")
        fabric.transition_session(session.sessionId, "start", actor_id="instructor-a")

        takeoff = await fabric.ingest_event(
            _event(
                session.sessionId,
                action="takeoff",
                target="tello_fleet",
                sequence=1,
            )
        )
        land = await fabric.ingest_event(
            _event(
                session.sessionId,
                action="land",
                target="tello_fleet",
                sequence=2,
            )
        )
        exact_takeoff = await fabric.ingest_event(
            _event(
                session.sessionId,
                action="takeoff",
                target="assigned_output",
                target_role="fleet_sequence_controller",
                sequence=3,
            )
        )
        exact_land = await fabric.ingest_event(
            _event(
                session.sessionId,
                action="land",
                target="assigned_output",
                target_role="fleet_sequence_controller",
                sequence=4,
            )
        )

    assert [command.targetNodeId for command in dispatched] == [
        "tello-fleet-a",
        "tello-fleet-a",
        "tello-fleet-a",
        "tello-fleet-a",
    ]
    assert [command.action for command in dispatched] == [
        FLEET_START_CAPABILITY,
        FLEET_STOP_CAPABILITY,
        FLEET_START_CAPABILITY,
        FLEET_STOP_CAPABILITY,
    ]
    assert all(command.sourceNodeId == "g2-a" for command in dispatched)
    assert [item.stage.value for item in takeoff.command_lifecycle].count("DISPATCHED") == 1
    assert [item.stage.value for item in land.command_lifecycle].count("DISPATCHED") == 1
    assert [item.stage.value for item in exact_takeoff.command_lifecycle].count("DISPATCHED") == 1
    assert [item.stage.value for item in exact_land.command_lifecycle].count("DISPATCHED") == 1


@pytest.mark.asyncio
async def test_g2_menu_routes_explicit_on_and_off_to_one_assigned_smart_plug() -> None:
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW)
        dispatched: list[FabricResolvedCommand] = []

        async def dispatch(
            command: FabricResolvedCommand,
            _node: IntegrationNode,
        ) -> FabricDispatchOutcome:
            dispatched.append(command)
            return FabricDispatchOutcome(accepted=True)

        fabric.set_dispatcher(dispatch)
        manifest, nodes = _plugin_and_nodes()
        fabric.register_plugin_and_nodes(manifest, nodes)
        pack = load_builtin_course_pack("glasses-device-control")
        fabric.install_course_pack(pack, actor_id="instructor-a")
        session = fabric.create_session(
            CreateInteractionSessionRequest.model_validate(
                {
                    "coursePackId": pack.coursePackId,
                    "coursePackVersion": pack.version,
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "mode": "simulation",
                }
            ),
            actor_id="instructor-a",
        )
        for role, node_id in (
            ("glasses_input_1", "g2-a"),
            ("power_output_1", "matter-plug-a"),
        ):
            fabric.assign_role(session.sessionId, role, node_id, actor_id="instructor-a")
        fabric.transition_session(session.sessionId, "start", actor_id="instructor-a")

        power_on = await fabric.ingest_event(
            _event(
                session.sessionId,
                action="power_on",
                target="assigned_output",
                target_role="power_output_1",
                sequence=1,
            )
        )
        power_off = await fabric.ingest_event(
            _event(
                session.sessionId,
                action="power_off",
                target="assigned_output",
                target_role="power_output_1",
                sequence=2,
            )
        )

    assert [command.targetNodeId for command in dispatched] == [
        "matter-plug-a",
        "matter-plug-a",
    ]
    assert [command.action for command in dispatched] == [
        POWER_SET_CAPABILITY,
        POWER_SET_CAPABILITY,
    ]
    assert [command.parameters.model_dump(mode="json") for command in dispatched] == [
        {"on": True},
        {"on": False},
    ]
    assert [item.stage.value for item in power_on.command_lifecycle].count("DISPATCHED") == 1
    assert [item.stage.value for item in power_off.command_lifecycle].count("DISPATCHED") == 1


@pytest.mark.asyncio
async def test_meta_or_g2_all_plugs_intent_fans_out_to_each_assigned_plug() -> None:
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW)
        dispatched: list[FabricResolvedCommand] = []

        async def dispatch(
            command: FabricResolvedCommand,
            _node: IntegrationNode,
        ) -> FabricDispatchOutcome:
            dispatched.append(command)
            return FabricDispatchOutcome(accepted=True)

        fabric.set_dispatcher(dispatch)
        manifest, nodes = _plugin_and_nodes()
        fabric.register_plugin_and_nodes(manifest, nodes)
        pack = load_builtin_course_pack("glasses-device-control")
        fabric.install_course_pack(pack, actor_id="instructor-a")
        session = fabric.create_session(
            CreateInteractionSessionRequest.model_validate(
                {
                    "coursePackId": pack.coursePackId,
                    "coursePackVersion": pack.version,
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "mode": "simulation",
                }
            ),
            actor_id="instructor-a",
        )
        for role, node_id in (
            ("glasses_input_1", "g2-a"),
            ("power_output_1", "matter-plug-a"),
            ("power_output_2", "matter-plug-b"),
        ):
            fabric.assign_role(session.sessionId, role, node_id, actor_id="instructor-a")
        fabric.transition_session(session.sessionId, "start", actor_id="instructor-a")

        result = await fabric.ingest_event(
            _event(
                session.sessionId,
                action="power_on",
                target="power_outputs",
                sequence=1,
            )
        )

    assert [command.targetNodeId for command in dispatched] == [
        "matter-plug-a",
        "matter-plug-b",
    ]
    assert all(command.action == POWER_SET_CAPABILITY for command in dispatched)
    assert all(command.parameters.model_dump(mode="json") == {"on": True} for command in dispatched)
    assert [item.stage.value for item in result.command_lifecycle].count("DISPATCHED") == 2
