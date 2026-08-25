from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cit_protocol import (
    CreateInteractionSessionRequest,
    FabricCommandRequest,
    FabricResolvedCommand,
    HealthReport,
    IntegrationNode,
)
from cit_runtime.fabric import FabricDispatchOutcome, InteractionFabric
from cit_runtime.fabric_course import device_monitoring_course_pack
from cit_runtime.fabric_repository import SQLiteFabricRepository
from cit_tello.contract import (
    MOVE_CAPABILITY,
    ROTATE_CAPABILITY,
    TAKEOFF_CAPABILITY,
    build_manifest,
    build_node,
)

NOW = datetime(2026, 8, 25, 1, 30, 0, tzinfo=UTC)


def test_healthy_tello_heartbeat_clears_the_previous_health_message() -> None:
    with SQLiteFabricRepository(":memory:") as repository:
        repository.register_fabric_plugin(build_manifest(), at=NOW)
        node = build_node(
            at=NOW,
            host_id="host-a",
            site_id="local-site",
            room_id="local-room",
            node_id="tello-a",
            simulated=False,
            ip_address="192.168.10.1",
            brain2devices_drone_id="primary",
        )
        repository.upsert_fabric_node(node, at=NOW, lease_ttl=timedelta(seconds=30))
        repository.update_fabric_health(
            HealthReport.model_validate(
                {
                    "schemaVersion": "1.0",
                    "nodeId": "tello-a",
                    "reportedAt": NOW,
                    "connectionState": "disconnected",
                    "healthState": "unhealthy",
                    "message": "Wi-Fi 2 disconnected",
                    "metrics": {"takeoffEnabled": False},
                }
            ),
            at=NOW,
            lease_ttl=timedelta(seconds=30),
        )

        recovered = repository.update_fabric_health(
            HealthReport.model_validate(
                {
                    "schemaVersion": "1.0",
                    "nodeId": "tello-a",
                    "reportedAt": NOW + timedelta(seconds=1),
                    "connectionState": "connected",
                    "healthState": "healthy",
                    "message": None,
                    "metrics": {"takeoffEnabled": True},
                }
            ),
            at=NOW + timedelta(seconds=1),
            lease_ttl=timedelta(seconds=30),
        )

    assert "healthMessage" not in recovered.metadata.model_dump(mode="json")


def request(
    session_id: str,
    action: str,
    parameters: dict[str, object],
    **updates: object,
) -> FabricCommandRequest:
    return FabricCommandRequest.model_validate(
        {
            "messageId": str(uuid4()),
            "schemaVersion": "1.0",
            "messageType": "command.requested",
            "action": action,
            "target": {"role": "safety_drone_1"},
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


def confirmations() -> dict[str, object]:
    return {
        "instructorPresent": True,
        "flightAreaClear": True,
        "emergencyPlanReady": True,
    }


async def setup(
    *, armed: bool = True
) -> tuple[
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
        node_id="tello-a",
        simulated=False,
        ip_address="192.168.10.1",
        brain2devices_drone_id="primary",
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
        "safety_drone_1",
        node.nodeId,
        actor_id="instructor-a",
    )
    if armed:
        fabric.transition_session(session.sessionId, "arm", actor_id="instructor-a")
    fabric.transition_session(session.sessionId, "start", actor_id="instructor-a")
    return fabric, repository, session.sessionId, dispatched


@pytest.mark.asyncio
async def test_physical_manual_tello_commands_require_exact_bounded_confirmations() -> None:
    fabric, repository, session_id, dispatched = await setup()
    try:
        missing_confirmation = await fabric.submit_command(
            request(
                session_id,
                TAKEOFF_CAPABILITY,
                {**confirmations(), "flightAreaClear": False},
            )
        )
        too_far = await fabric.submit_command(
            request(
                session_id,
                MOVE_CAPABILITY,
                {
                    **confirmations(),
                    "direction": "forward",
                    "distanceCentimeters": 51,
                },
            )
        )
        agent = await fabric.submit_command(
            request(
                session_id,
                TAKEOFF_CAPABILITY,
                confirmations(),
                priority="autonomous_agent",
            )
        )
        takeoff = await fabric.submit_command(
            request(session_id, TAKEOFF_CAPABILITY, confirmations())
        )
        move = await fabric.submit_command(
            request(
                session_id,
                MOVE_CAPABILITY,
                {
                    **confirmations(),
                    "direction": "forward",
                    "distanceCentimeters": 20,
                },
            )
        )
        rotate = await fabric.submit_command(
            request(
                session_id,
                ROTATE_CAPABILITY,
                {**confirmations(), "clockwise": True, "degrees": 30},
            )
        )
    finally:
        repository.close()

    assert missing_confirmation[-1].code == "SAFETY_PROFILE_NOT_IMPLEMENTED"
    assert too_far[-1].code == "SAFETY_PROFILE_NOT_IMPLEMENTED"
    assert agent[-1].code == "AGENT_PHYSICAL_CONTROL_DENIED"
    assert takeoff[-1].stage.value == "DISPATCHED"
    assert move[-1].stage.value == "DISPATCHED"
    assert rotate[-1].stage.value == "DISPATCHED"
    assert [command.action for command in dispatched] == [
        TAKEOFF_CAPABILITY,
        MOVE_CAPABILITY,
        ROTATE_CAPABILITY,
    ]


@pytest.mark.asyncio
async def test_physical_manual_tello_takeoff_is_denied_while_session_is_unarmed() -> None:
    fabric, repository, session_id, dispatched = await setup(armed=False)
    try:
        lifecycle = await fabric.submit_command(
            request(session_id, TAKEOFF_CAPABILITY, confirmations())
        )
    finally:
        repository.close()

    assert lifecycle[-1].code == "SESSION_NOT_ARMED"
    assert dispatched == []
