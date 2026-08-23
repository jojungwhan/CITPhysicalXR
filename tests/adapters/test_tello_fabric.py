from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cit_protocol import FabricResolvedCommand
from cit_tello.backend import SimulatedTelloBackend
from cit_tello.bridge import TelloCommandHandler
from cit_tello.contract import (
    BRAIN2DEVICES_REVISION,
    EMERGENCY_STOP_CAPABILITY,
    LAND_CAPABILITY,
    build_manifest,
    build_node,
)


def _command(action: str, *, parameters: dict[str, object] | None = None) -> FabricResolvedCommand:
    now = datetime.now(UTC)
    return FabricResolvedCommand.model_validate(
        {
            "commandId": str(uuid4()),
            "requestMessageId": str(uuid4()),
            "schemaVersion": "1.0",
            "sessionId": "session-a",
            "targetNodeId": "tello-a",
            "action": action,
            "parameters": parameters or {},
            "priority": "instructor_override",
            "idempotencyKey": str(uuid4()),
            "requestedAt": now,
            "expiresAt": now + timedelta(seconds=1),
            "safetyProfile": "classroom-drone-monitoring",
            "correlationId": str(uuid4()),
        }
    )


def test_tello_contract_exposes_only_safe_flight_commands() -> None:
    manifest = build_manifest()
    node = build_node(
        at=datetime.now(UTC),
        host_id="host-a",
        site_id="site-a",
        room_id="room-a",
        node_id="tello-a",
        simulated=False,
        ip_address=None,
    )

    assert [item.name for item in manifest.consumedCapabilities] == [
        LAND_CAPABILITY,
        EMERGENCY_STOP_CAPABILITY,
    ]
    assert all("takeoff" not in item.name for item in manifest.consumedCapabilities)
    assert node.metadata.model_dump()["brain2devicesRevision"] == BRAIN2DEVICES_REVISION
    assert node.metadata.model_dump()["takeoffEnabled"] is False


@pytest.mark.asyncio
async def test_tello_duplicate_safe_state_command_executes_once() -> None:
    backend = SimulatedTelloBackend()
    await backend.start()
    handler = TelloCommandHandler(backend, node_id="tello-a")
    command = _command(LAND_CAPABILITY)

    first = await handler.execute(command)
    second = await handler.execute(command)

    assert first["duplicatePrevented"] is False
    assert second == {"duplicatePrevented": True}
    assert backend.command_log.count("land:fabric_command") == 1


@pytest.mark.parametrize(
    ("action", "parameters"),
    [
        ("mobility.flight.takeoff", {}),
        ("mobility.flight.move", {}),
        (LAND_CAPABILITY, {"height": 1}),
    ],
)
def test_tello_rejects_takeoff_movement_and_parameters(
    action: str,
    parameters: dict[str, object],
) -> None:
    handler = TelloCommandHandler(SimulatedTelloBackend(), node_id="tello-a")
    with pytest.raises(ValueError):
        handler.validate(_command(action, parameters=parameters))
