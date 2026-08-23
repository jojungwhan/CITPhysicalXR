from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cit_brain2devices_demo.contract import ARM_CAPABILITY, build_manifest, build_node
from cit_protocol import (
    CreateInteractionSessionRequest,
    FabricCommandRequest,
    FabricResolvedCommand,
    IntegrationNode,
)
from cit_runtime.fabric import FabricDispatchOutcome, InteractionFabric
from cit_runtime.fabric_course import device_monitoring_course_pack
from cit_runtime.fabric_repository import SQLiteFabricRepository

NOW = datetime(2026, 8, 23, 4, 0, 0, tzinfo=UTC)


def request(session_id: str, **updates: object) -> FabricCommandRequest:
    parameters: dict[str, object] = {
        "attentionEnabled": True,
        "attentionThreshold": 50,
        "meditationEnabled": False,
        "meditationThreshold": 50,
        "blinkEnabled": False,
        "blinkThreshold": 50,
        "dwellSeconds": 2,
        "instructorPresent": True,
        "flightAreaClear": True,
        "emergencyPlanReady": True,
    }
    parameter_updates = updates.pop("parameters", None)
    if isinstance(parameter_updates, dict):
        parameters.update(parameter_updates)
    return FabricCommandRequest.model_validate(
        {
            "messageId": str(uuid4()),
            "schemaVersion": "1.0",
            "messageType": "command.requested",
            "action": ARM_CAPABILITY,
            "target": {"role": "brain_flight_demo"},
            "sessionId": session_id,
            "parameters": parameters,
            "priority": "instructor_override",
            "idempotencyKey": str(uuid4()),
            "requestedAt": NOW,
            "ttlMs": 2_000,
            "safetyProfile": "classroom-drone-monitoring",
            "correlationId": str(uuid4()),
            **updates,
        }
    )


async def setup() -> tuple[
    InteractionFabric,
    SQLiteFabricRepository,
    str,
    list[FabricResolvedCommand],
]:
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
    node = build_node(
        at=NOW,
        host_id="host-a",
        site_id="local-site",
        room_id="local-room",
        node_id="brain-demo-a",
        simulated=False,
    )
    fabric.register_plugin_and_nodes(build_manifest(), (node,))
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
    session = fabric.assign_role(
        session.sessionId,
        "brain_flight_demo",
        node.nodeId,
        actor_id="instructor-a",
    )
    fabric.transition_session(session.sessionId, "arm", actor_id="instructor-a")
    fabric.transition_session(session.sessionId, "start", actor_id="instructor-a")
    return fabric, repository, session.sessionId, dispatched


@pytest.mark.asyncio
async def test_physical_brain_demo_requires_all_confirmations_and_instructor_priority() -> None:
    fabric, repository, session_id, dispatched = await setup()
    try:
        missing_confirmation = await fabric.submit_command(
            request(session_id, parameters={"flightAreaClear": False})
        )
        agent_priority = await fabric.submit_command(
            request(session_id, priority="autonomous_agent")
        )
        allowed = await fabric.submit_command(request(session_id))
    finally:
        repository.close()

    assert missing_confirmation[-1].code == "SAFETY_PROFILE_NOT_IMPLEMENTED"
    assert agent_priority[-1].code == "AGENT_PHYSICAL_CONTROL_DENIED"
    assert allowed[-1].stage.value == "DISPATCHED"
    assert len(dispatched) == 1
