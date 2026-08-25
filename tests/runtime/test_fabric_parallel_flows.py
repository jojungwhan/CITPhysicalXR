from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cit_protocol import (
    CoursePack,
    CreateInteractionSessionRequest,
    FabricEventEnvelope,
    FabricResolvedCommand,
    IntegrationNode,
    PluginManifest,
)
from cit_runtime.fabric import FabricDispatchOutcome, InteractionFabric
from cit_runtime.fabric_course import load_builtin_course_pack, validate_course_pack
from cit_runtime.fabric_repository import SQLiteFabricRepository

NOW = datetime(2026, 8, 23, 8, 0, 0, tzinfo=UTC)
TRIGGER = "interaction.intent.simultaneous_cue"
DISPLAY = "display.text.render"


def capability(name: str, direction: str) -> dict[str, object]:
    return {
        "name": name,
        "version": "1.0",
        "direction": direction,
        "maximumRateHz": 10,
        "latencyClass": "interactive",
        "safetyClassification": "informational",
        "dataClassification": "operational",
        "constraints": {},
    }


def plugin_and_nodes() -> tuple[PluginManifest, IntegrationNode, IntegrationNode, IntegrationNode]:
    published = capability(TRIGGER, "publish")
    consumed = capability(DISPLAY, "consume")
    manifest = PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": "cit.parallel-flow-test",
            "pluginVersion": "1.0.0",
            "runtimeVersion": "python-3.11",
            "displayName": "Parallel flow test nodes",
            "adapterMode": "out_of_process",
            "configurationSchema": {},
            "publishedCapabilities": [published],
            "consumedCapabilities": [consumed],
            "requiredPermissions": [],
            "safetyClassification": "informational",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "included",
        }
    )

    def node(
        node_id: str,
        *,
        publishes: list[dict[str, object]],
        consumes: list[dict[str, object]],
    ) -> IntegrationNode:
        return IntegrationNode.model_validate(
            {
                "schemaVersion": "1.0",
                "nodeId": node_id,
                "pluginId": manifest.pluginId,
                "pluginVersion": manifest.pluginVersion,
                "runtimeVersion": manifest.runtimeVersion,
                "hostId": "test-host",
                "siteId": "local-site",
                "roomId": "local-room",
                "displayName": node_id,
                "physical": False,
                "simulated": True,
                "connectionState": "connected",
                "healthState": "healthy",
                "publishedCapabilities": publishes,
                "consumedCapabilities": consumes,
                "configurationSchema": {},
                "safetyClassification": "informational",
                "dataClassifications": ["operational"],
                "simulatorAvailable": True,
                "requiredPermissions": [],
                "lastSeenAt": NOW,
                "metadata": {},
            }
        )

    return (
        manifest,
        node("cue-input", publishes=[published], consumes=[]),
        node("display-a", publishes=[], consumes=[consumed]),
        node("display-b", publishes=[], consumes=[consumed]),
    )


def parallel_course(*, invalid_second_output: bool = False) -> CoursePack:
    def flow(flow_id: str, role: str, text: str) -> dict[str, object]:
        return {
            "flowId": flow_id,
            "version": 1,
            "trigger": {"event": TRIGGER, "debounceMs": 100},
            "command": {
                "action": DISPLAY,
                "fixedParameters": {"text": text},
                "parameterBindings": [],
            },
            "target": {"role": role},
            "guards": [
                "session_is_active",
                "role_is_assigned",
                "target_is_connected",
                "instructor_override_is_clear",
            ],
            "safetyProfile": "parallel-test",
            "outputRoles": [role],
            "parallelGroup": "classroom-cue",
            "enabled": True,
        }

    return CoursePack.model_validate(
        {
            "schemaVersion": "1.0",
            "coursePackId": "parallel-flow-test",
            "version": "1.0.0",
            "displayName": "Parallel flow test",
            "roles": [
                {
                    "role": "cue_input",
                    "oneOfCapabilities": [TRIGGER],
                    "optional": False,
                },
                {
                    "role": "display_a",
                    "oneOfCapabilities": [DISPLAY],
                    "optional": False,
                },
                {
                    "role": "display_b",
                    "oneOfCapabilities": [DISPLAY],
                    "optional": False,
                },
            ],
            "flows": [
                flow("display-a", "display_a", "Cue A"),
                flow("display-b", "display_b", "" if invalid_second_output else "Cue B"),
            ],
            "safetyProfile": "parallel-test",
            "simulatorRequired": True,
            "assessmentEvents": [TRIGGER],
            "fallbackBehavior": "Report each output independently.",
        }
    )


def prepare_fabric(
    repository: SQLiteFabricRepository,
    *,
    invalid_second_output: bool = False,
) -> tuple[InteractionFabric, str, IntegrationNode]:
    manifest, source, first, second = plugin_and_nodes()
    fabric = InteractionFabric(repository, clock=lambda: NOW)
    fabric.register_plugin_and_nodes(manifest, (source, first, second))
    course = parallel_course(invalid_second_output=invalid_second_output)
    fabric.install_course_pack(course, actor_id="instructor")
    session = fabric.create_session(
        CreateInteractionSessionRequest.model_validate(
            {
                "coursePackId": course.coursePackId,
                "coursePackVersion": course.version,
                "siteId": "local-site",
                "roomId": "local-room",
                "mode": "simulation",
            }
        ),
        actor_id="instructor",
    )
    for role, node in (
        ("cue_input", source),
        ("display_a", first),
        ("display_b", second),
    ):
        session = fabric.assign_role(
            session.sessionId,
            role,
            node.nodeId,
            actor_id="instructor",
        )
    fabric.transition_session(session.sessionId, "start", actor_id="instructor")
    return fabric, session.sessionId, source


def cue_event(session_id: str, source: IntegrationNode) -> FabricEventEnvelope:
    return FabricEventEnvelope.model_validate(
        {
            "messageId": str(uuid4()),
            "schemaVersion": "1.0",
            "messageType": "event",
            "topic": TRIGGER,
            "sourceNodeId": source.nodeId,
            "sourceCapability": TRIGGER,
            "siteId": source.siteId,
            "roomId": source.roomId,
            "sessionId": session_id,
            "timestamp": NOW,
            "monotonicTimestamp": 1,
            "sequence": 1,
            "ttlMs": 2_000,
            "dataClassification": "operational",
            "payload": {},
        }
    )


def test_course_validation_rejects_command_target_declared_as_input_only() -> None:
    value = parallel_course().model_dump(mode="json")
    for requirement in value["roles"]:
        if requirement["role"] == "display_a":
            requirement["ioType"] = "input"
    invalid = CoursePack.model_validate(value)

    with pytest.raises(ValueError, match="cannot target input-only role"):
        validate_course_pack(invalid)


def test_synchronized_motor_course_keeps_each_input_on_bounded_parallel_flows() -> None:
    course = load_builtin_course_pack("synchronized-motor-control")
    validate_course_pack(course)

    ground_roles = {f"ground_output_{index}" for index in range(1, 9)}
    voice = [flow for flow in course.flows if flow.parallelGroup == "synchronized-voice-ground"]
    ring = [
        flow
        for flow in course.flows
        if flow.parallelGroup
        in {
            "synchronized-ring-forward",
            "synchronized-ring-backward",
            "synchronized-ring-stop",
        }
    ]
    mindwave = [flow for flow in course.flows if flow.parallelGroup == "synchronized-mindwave-demo"]

    assert {flow.target.role for flow in voice} == ground_roles
    assert len(ring) == 24
    assert {flow.target.role for flow in mindwave} == ground_roles
    assert all(flow.command.action == "mobility.ground.nudge" for flow in voice + ring)
    assert all(flow.command.action == "mobility.ground.demonstration.start" for flow in mindwave)
    assert all("target_is_armed" in {guard.value for guard in flow.guards} for flow in course.flows)


@pytest.mark.asyncio
async def test_parallel_group_reaches_both_adapters_before_either_finishes() -> None:
    with SQLiteFabricRepository(":memory:") as repository:
        fabric, session_id, source = prepare_fabric(repository)
        both_started = asyncio.Event()
        dispatched: list[FabricResolvedCommand] = []

        async def dispatch(
            command: FabricResolvedCommand,
            _node: IntegrationNode,
        ) -> FabricDispatchOutcome:
            dispatched.append(command)
            if len(dispatched) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.5)
            return FabricDispatchOutcome(accepted=True)

        fabric.set_dispatcher(dispatch)
        result = await fabric.ingest_event(cue_event(session_id, source))

    assert {command.targetNodeId for command in dispatched} == {"display-a", "display-b"}
    assert len({command.idempotencyKey for command in dispatched}) == 2
    assert len({command.correlationId for command in dispatched}) == 1
    assert [item.stage.value for item in result.command_lifecycle].count("DISPATCHED") == 2


@pytest.mark.asyncio
async def test_parallel_output_rejection_does_not_cancel_safe_sibling() -> None:
    with SQLiteFabricRepository(":memory:") as repository:
        fabric, session_id, source = prepare_fabric(
            repository,
            invalid_second_output=True,
        )
        dispatched: list[FabricResolvedCommand] = []

        async def dispatch(
            command: FabricResolvedCommand,
            _node: IntegrationNode,
        ) -> FabricDispatchOutcome:
            dispatched.append(command)
            return FabricDispatchOutcome(accepted=True)

        fabric.set_dispatcher(dispatch)
        result = await fabric.ingest_event(cue_event(session_id, source))

    terminal_by_target = {
        lifecycle.targetNodeId: lifecycle.stage.value for lifecycle in result.command_lifecycle
    }
    assert [command.targetNodeId for command in dispatched] == ["display-a"]
    assert terminal_by_target == {
        "display-a": "DISPATCHED",
        "display-b": "REJECTED",
    }
