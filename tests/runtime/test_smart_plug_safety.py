from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from cit_matter_smart_plug import build_manifest, build_node
from cit_protocol import (
    CreateInteractionSessionRequest,
    FabricCommandLifecycleEvent,
    FabricCommandRequest,
    FabricEventEnvelope,
    FabricResolvedCommand,
    IntegrationNode,
)
from cit_runtime.fabric import FabricDispatchOutcome, InteractionFabric
from cit_runtime.fabric_course import smart_plug_course_pack
from cit_runtime.fabric_repository import SQLiteFabricRepository

NOW = datetime(2026, 8, 21, 3, 0, 0, tzinfo=UTC)


def request(session_id: str, *, on: object) -> FabricCommandRequest:
    return FabricCommandRequest.model_validate(
        {
            "messageId": str(uuid4()),
            "schemaVersion": "1.0",
            "messageType": "command.requested",
            "action": "power.switch.set",
            "target": {"role": "classroom_plug"},
            "sessionId": session_id,
            "parameters": {"on": on},
            "priority": "instructor_override",
            "idempotencyKey": str(uuid4()),
            "requestedAt": NOW,
            "ttlMs": 2_000,
            "safetyProfile": "classroom-smart-plug",
            "correlationId": str(uuid4()),
        }
    )


async def setup_physical_plug(
    fabric: InteractionFabric,
    dispatched: list[FabricResolvedCommand],
) -> tuple[str, IntegrationNode]:
    async def dispatch(
        command: FabricResolvedCommand,
        node: IntegrationNode,
    ) -> FabricDispatchOutcome:
        del node
        dispatched.append(command)
        return FabricDispatchOutcome(accepted=True)

    fabric.set_dispatcher(dispatch)
    node = build_node(
        at=NOW,
        host_id="edge-a",
        site_id="local-site",
        room_id="local-room",
        node_id="plug-a",
        matter_node_id=11,
        endpoint_id=1,
        display_name="Approved classroom plug",
        vendor_name="Matter",
        product_name="approved-load-plug",
        electrical_telemetry=True,
    )
    fabric.register_plugin_and_nodes(build_manifest(), (node,))
    fabric.install_course_pack(smart_plug_course_pack(), actor_id="instructor-a")
    session = fabric.create_session(
        CreateInteractionSessionRequest.model_validate(
            {
                "coursePackId": "smart-plug-control",
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
        "classroom_plug",
        node.nodeId,
        actor_id="instructor-a",
    )
    assert session.state.value == "ready"
    return session.sessionId, node


@pytest.mark.asyncio
async def test_off_is_a_safe_state_but_on_requires_active_armed_physical_session() -> None:
    dispatched: list[FabricResolvedCommand] = []
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW, allow_physical=True)
        session_id, _ = await setup_physical_plug(fabric, dispatched)

        off_lifecycle = await fabric.submit_command(request(session_id, on=False))
        denied_on = await fabric.submit_command(request(session_id, on=True))
        fabric.transition_session(session_id, "arm", actor_id="instructor-a")
        fabric.transition_session(session_id, "start", actor_id="instructor-a")
        allowed_on = await fabric.submit_command(request(session_id, on=True))

    assert off_lifecycle[-1].stage.value == "DISPATCHED"
    assert denied_on[-1].stage.value == "REJECTED"
    assert denied_on[-1].code == "SESSION_NOT_ACTIVE"
    assert allowed_on[-1].stage.value == "DISPATCHED"
    assert [item.parameters.model_dump(mode="json") for item in dispatched] == [
        {"on": False},
        {"on": True},
    ]


@pytest.mark.asyncio
async def test_safe_off_result_is_accepted_before_the_physical_session_starts() -> None:
    dispatched: list[FabricResolvedCommand] = []
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW, allow_physical=True)
        session_id, node = await setup_physical_plug(fabric, dispatched)

        lifecycle = await fabric.submit_command(request(session_id, on=False))
        [command] = dispatched
        assert lifecycle[-1].stage.value == "DISPATCHED"
        for stage in ("ACCEPTED", "RUNNING", "SUCCEEDED"):
            fabric.accept_adapter_lifecycle(
                FabricCommandLifecycleEvent.model_validate(
                    {
                        "messageId": str(uuid4()),
                        "schemaVersion": "1.0",
                        "messageType": "command.lifecycle",
                        "commandId": command.commandId,
                        "requestMessageId": command.requestMessageId,
                        "sessionId": command.sessionId,
                        "targetNodeId": command.targetNodeId,
                        "stage": stage,
                        "occurredAt": NOW,
                        "correlationId": command.correlationId,
                        "details": {"on": False},
                    }
                )
            )

        state_result = await fabric.ingest_event(
            FabricEventEnvelope.model_validate(
                {
                    "messageId": str(uuid4()),
                    "schemaVersion": "1.0",
                    "messageType": "event",
                    "topic": "power.switch.state",
                    "sourceNodeId": node.nodeId,
                    "sourceCapability": "power.switch.state",
                    "siteId": node.siteId,
                    "roomId": node.roomId,
                    "sessionId": session_id,
                    "timestamp": NOW,
                    "monotonicTimestamp": 1,
                    "sequence": 1,
                    "correlationId": command.correlationId,
                    "causationId": str(command.commandId),
                    "ttlMs": int(timedelta(seconds=2).total_seconds() * 1_000),
                    "dataClassification": "operational",
                    "payload": {
                        "on": False,
                        "source": "command",
                        "vendorBrand": "Matter",
                        "cloudDependency": False,
                    },
                }
            )
        )
        electrical_result = await fabric.ingest_event(
            FabricEventEnvelope.model_validate(
                {
                    "messageId": str(uuid4()),
                    "schemaVersion": "1.0",
                    "messageType": "event",
                    "topic": "telemetry.power.electrical",
                    "sourceNodeId": node.nodeId,
                    "sourceCapability": "telemetry.power.electrical",
                    "siteId": node.siteId,
                    "roomId": node.roomId,
                    "sessionId": session_id,
                    "timestamp": NOW,
                    "monotonicTimestamp": 2,
                    "sequence": 2,
                    "correlationId": command.correlationId,
                    "causationId": str(command.commandId),
                    "ttlMs": int(timedelta(seconds=2).total_seconds() * 1_000),
                    "dataClassification": "operational",
                    "payload": {
                        "activePowerWatts": 0.0,
                        "source": "command",
                        "standard": "Matter 1.3",
                    },
                }
            )
        )

    assert state_result.stored_event is not None
    assert state_result.stored_event.event.payload.model_dump(mode="json")["on"] is False
    assert state_result.command_lifecycle == ()
    assert electrical_result.stored_event is not None
    assert electrical_result.stored_event.event.payload.model_dump(mode="json")[
        "activePowerWatts"
    ] == pytest.approx(0.0)
    assert electrical_result.command_lifecycle == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [1, "true", None, {"value": True}])
async def test_smart_plug_rejects_non_boolean_parameters(invalid: Any) -> None:
    dispatched: list[FabricResolvedCommand] = []
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW, allow_physical=True)
        session_id, _ = await setup_physical_plug(fabric, dispatched)
        fabric.transition_session(session_id, "arm", actor_id="instructor-a")
        fabric.transition_session(session_id, "start", actor_id="instructor-a")
        lifecycle = await fabric.submit_command(request(session_id, on=invalid))

    assert lifecycle[-1].stage.value == "REJECTED"
    assert lifecycle[-1].code == "INVALID_COMMAND_PARAMETERS"
    assert dispatched == []
