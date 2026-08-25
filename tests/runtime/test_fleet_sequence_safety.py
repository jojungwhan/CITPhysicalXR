from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cit_brain2devices_demo.fleet_contract import (
    ARM_CAPABILITY,
    START_CAPABILITY,
)
from cit_brain2devices_demo.fleet_contract import (
    build_manifest as build_fleet_manifest,
)
from cit_brain2devices_demo.fleet_contract import (
    build_node as build_fleet_node,
)
from cit_integration_sdk import capability_descriptor
from cit_protocol import (
    CreateInteractionSessionRequest,
    FabricCommandRequest,
    FabricEventEnvelope,
    FabricResolvedCommand,
    FabricSessionMode,
    IntegrationNode,
    PluginManifest,
)
from cit_runtime.fabric import FabricDispatchOutcome, InteractionFabric
from cit_runtime.fabric_course import device_monitoring_course_pack
from cit_runtime.fabric_repository import SQLiteFabricRepository

NOW = datetime(2026, 8, 23, 7, 0, 0, tzinfo=UTC)
INTENT_CAPABILITY = "interaction.intent.flight_sequence_start"


def test_shared_monitoring_session_accepts_only_the_dormant_fleet_flow() -> None:
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW)
        pack = device_monitoring_course_pack()
        fabric.install_course_pack(pack, actor_id="system.test")

        session, reused = fabric.ensure_monitoring_session(
            pack,
            site_id="local-site",
            room_id="local-room",
            mode=FabricSessionMode.simulation,
            actor_id="instructor-a",
        )

    assert reused is False
    assert session.coursePackId == "device-monitoring"
    assert session.armed is False


def test_shared_monitoring_session_rejects_a_flow_without_the_arm_guard() -> None:
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW)
        pack = device_monitoring_course_pack()
        flow = pack.flows[0]
        unsafe = pack.model_copy(
            update={
                "flows": [
                    flow.model_copy(
                        update={
                            "guards": [
                                guard for guard in flow.guards if guard.value != "target_is_armed"
                            ]
                        }
                    )
                ]
            }
        )

        with pytest.raises(ValueError, match="unarmed-safety guard"):
            fabric.ensure_monitoring_session(
                unsafe,
                site_id="local-site",
                room_id="local-room",
                mode=FabricSessionMode.physical,
                actor_id="instructor-a",
            )


def input_plugin_and_node(kind: str) -> tuple[PluginManifest, IntegrationNode]:
    plugin_id = f"cit.test-{kind}"
    capability = capability_descriptor("flight_sequence_intent", "publish")
    manifest = PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": plugin_id,
            "pluginVersion": "1.0.0",
            "runtimeVersion": "test",
            "displayName": kind,
            "adapterMode": "out_of_process",
            "configurationSchema": {},
            "publishedCapabilities": [capability],
            "consumedCapabilities": [],
            "requiredPermissions": [],
            "safetyClassification": "informational",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "included",
        }
    )
    node = IntegrationNode.model_validate(
        {
            "schemaVersion": "1.0",
            "nodeId": f"{kind}-a",
            "pluginId": plugin_id,
            "pluginVersion": "1.0.0",
            "runtimeVersion": "test",
            "hostId": "host-a",
            "siteId": "local-site",
            "roomId": "local-room",
            "displayName": kind,
            "connectionState": "connected",
            "healthState": "healthy",
            "physical": True,
            "simulated": False,
            "publishedCapabilities": [capability],
            "consumedCapabilities": [],
            "configurationSchema": {},
            "safetyClassification": "informational",
            "dataClassifications": ["operational"],
            "simulatorAvailable": True,
            "requiredPermissions": [],
            "lastSeenAt": NOW,
            "metadata": {"kind": kind},
        }
    )
    return manifest, node


def arm_request(
    session_id: str,
    *,
    parameter_updates: dict[str, object] | None = None,
) -> FabricCommandRequest:
    parameters: dict[str, object] = {
        "droneIds": ["primary", "drone-2"],
        "allowedSourceNodeIds": ["leap-a"],
        "launchIntervalSeconds": 2,
        "minimumBatteryPercent": 30,
        "instructorPresent": True,
        "flightAreaClear": True,
        "emergencyPlanReady": True,
        "independentRoutesConfirmed": True,
    }
    parameters.update(parameter_updates or {})
    return FabricCommandRequest.model_validate(
        {
            "messageId": str(uuid4()),
            "schemaVersion": "1.0",
            "messageType": "command.requested",
            "action": ARM_CAPABILITY,
            "target": {"role": "fleet_sequence_controller"},
            "sessionId": session_id,
            "parameters": parameters,
            "priority": "instructor_override",
            "idempotencyKey": str(uuid4()),
            "requestedAt": NOW,
            "ttlMs": 2_000,
            "safetyProfile": "classroom-drone-monitoring",
            "correlationId": str(uuid4()),
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "parameter_updates",
    [
        {"droneIds": []},
        {"droneIds": ["primary", "primary"]},
        {"allowedSourceNodeIds": ["bad source"]},
        {"launchIntervalSeconds": 0},
        {"minimumBatteryPercent": 101},
    ],
)
async def test_core_rejects_invalid_fleet_bounds_before_adapter_dispatch(
    parameter_updates: dict[str, object],
) -> None:
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
        controller = build_fleet_node(
            at=NOW,
            host_id="host-a",
            site_id="local-site",
            room_id="local-room",
            node_id="fleet-sequence-a",
            simulated=False,
        )
        fabric.register_plugin_and_nodes(build_fleet_manifest(), (controller,))
        fabric.install_course_pack(device_monitoring_course_pack(), actor_id="instructor-a")
        session = fabric.create_session(
            CreateInteractionSessionRequest.model_validate(
                {
                    "coursePackId": "device-monitoring",
                    "coursePackVersion": "1.0.0",
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "mode": "physical",
                }
            ),
            actor_id="instructor-a",
        )
        fabric.assign_role(
            session.sessionId,
            "fleet_sequence_controller",
            controller.nodeId,
            actor_id="instructor-a",
        )
        fabric.transition_session(session.sessionId, "arm", actor_id="instructor-a")
        fabric.transition_session(session.sessionId, "start", actor_id="instructor-a")

        lifecycle = await fabric.submit_command(
            arm_request(session.sessionId, parameter_updates=parameter_updates)
        )

    assert lifecycle[-1].stage.value == "REJECTED"
    assert dispatched == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["leap", "g2", "meta"])
async def test_assigned_inputs_route_only_to_the_bounded_fleet_start(kind: str) -> None:
    repository = SQLiteFabricRepository(":memory:")
    fabric = InteractionFabric(repository, clock=lambda: NOW, allow_physical=True)
    dispatched: list[FabricResolvedCommand] = []

    async def dispatch(
        command: FabricResolvedCommand,
        _node: IntegrationNode,
    ) -> FabricDispatchOutcome:
        dispatched.append(command)
        return FabricDispatchOutcome(accepted=True)

    fabric.set_dispatcher(dispatch)
    controller = build_fleet_node(
        at=NOW,
        host_id="host-a",
        site_id="local-site",
        room_id="local-room",
        node_id="fleet-sequence-a",
        simulated=False,
    )
    source_manifest, source = input_plugin_and_node(kind)
    try:
        fabric.register_plugin_and_nodes(build_fleet_manifest(), (controller,))
        fabric.register_plugin_and_nodes(source_manifest, (source,))
        fabric.install_course_pack(device_monitoring_course_pack(), actor_id="instructor-a")
        session = fabric.create_session(
            CreateInteractionSessionRequest.model_validate(
                {
                    "coursePackId": "device-monitoring",
                    "coursePackVersion": "1.0.0",
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "mode": "physical",
                }
            ),
            actor_id="instructor-a",
        )
        fabric.assign_role(
            session.sessionId,
            "fleet_sequence_controller",
            controller.nodeId,
            actor_id="instructor-a",
        )
        fabric.assign_role(
            session.sessionId,
            "fleet_sequence_input_1",
            source.nodeId,
            actor_id="instructor-a",
        )
        fabric.transition_session(session.sessionId, "arm", actor_id="instructor-a")
        fabric.transition_session(session.sessionId, "start", actor_id="instructor-a")
        arm_lifecycle = await fabric.submit_command(arm_request(session.sessionId))
        result = await fabric.ingest_event(
            FabricEventEnvelope.model_validate(
                {
                    "messageId": str(uuid4()),
                    "schemaVersion": "1.0",
                    "messageType": "event",
                    "topic": INTENT_CAPABILITY,
                    "sourceNodeId": source.nodeId,
                    "sourceCapability": INTENT_CAPABILITY,
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "sessionId": session.sessionId,
                    "timestamp": NOW,
                    "monotonicTimestamp": 1,
                    "sequence": 1,
                    "confidence": 1,
                    "ttlMs": 2_000,
                    "dataClassification": "operational",
                    "payload": {"intent": "start"},
                }
            )
        )
    finally:
        repository.close()

    assert arm_lifecycle[-1].stage.value == "DISPATCHED"
    assert result.command_lifecycle[-1].stage.value == "DISPATCHED"
    assert [command.action for command in dispatched] == [
        ARM_CAPABILITY,
        START_CAPABILITY,
    ]
    assert dispatched[-1].priority.value == "lesson_automation"
    assert dispatched[-1].sourceNodeId == source.nodeId
