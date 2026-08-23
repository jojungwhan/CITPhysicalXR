from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cit_brain2devices_demo.backend import SimulatedBrainDemoBackend
from cit_brain2devices_demo.bridge import BrainDemoCommandHandler
from cit_brain2devices_demo.contract import (
    ARM_CAPABILITY,
    BRAIN2DEVICES_REVISION,
    STOP_CAPABILITY,
    build_manifest,
    build_node,
)
from cit_protocol import FabricResolvedCommand


def command(
    action: str,
    *,
    parameters: dict[str, object] | None = None,
    priority: str = "instructor_override",
) -> FabricResolvedCommand:
    now = datetime.now(UTC)
    return FabricResolvedCommand.model_validate(
        {
            "commandId": str(uuid4()),
            "requestMessageId": str(uuid4()),
            "schemaVersion": "1.0",
            "sessionId": "session-a",
            "targetNodeId": "brain-demo-a",
            "action": action,
            "parameters": parameters or {},
            "priority": priority,
            "idempotencyKey": str(uuid4()),
            "requestedAt": now,
            "expiresAt": now + timedelta(seconds=2),
            "safetyProfile": "classroom-drone-monitoring",
            "correlationId": str(uuid4()),
        }
    )


def settings(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
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
    value.update(updates)
    return value


def test_demo_contract_is_a_separate_one_shot_controller() -> None:
    manifest = build_manifest()
    node = build_node(
        at=datetime.now(UTC),
        host_id="host-a",
        site_id="site-a",
        room_id="room-a",
        node_id="brain-demo-a",
        simulated=False,
    )

    assert manifest.pluginId == "cit.brain2devices-demo"
    assert [item.name for item in manifest.consumedCapabilities] == [
        ARM_CAPABILITY,
        STOP_CAPABILITY,
    ]
    assert all(
        word not in item.name
        for item in manifest.consumedCapabilities
        for word in ("takeoff", ".move", ".rotate")
    )
    metadata = node.metadata.model_dump()
    assert metadata["brain2devicesRevision"] == BRAIN2DEVICES_REVISION
    assert metadata["oneShot"] is True
    assert metadata["rawEegPublished"] is False


@pytest.mark.parametrize(
    ("updates", "priority"),
    [
        ({"flightAreaClear": False}, "instructor_override"),
        ({"attentionEnabled": False}, "instructor_override"),
        ({"attentionThreshold": 101}, "instructor_override"),
        ({}, "autonomous_agent"),
    ],
)
def test_demo_arm_fails_closed(updates: dict[str, object], priority: str) -> None:
    handler = BrainDemoCommandHandler(SimulatedBrainDemoBackend(), node_id="brain-demo-a")
    parameters = settings(**updates)
    if updates == {"attentionEnabled": False}:
        parameters["meditationEnabled"] = False
        parameters["blinkEnabled"] = False

    with pytest.raises(ValueError):
        handler.validate(command(ARM_CAPABILITY, parameters=parameters, priority=priority))


@pytest.mark.asyncio
async def test_simulated_demo_is_one_shot_and_deduplicated() -> None:
    backend = SimulatedBrainDemoBackend()
    handler = BrainDemoCommandHandler(backend, node_id="brain-demo-a")
    request = command(ARM_CAPABILITY, parameters=settings(dwellSeconds=0))

    first = await handler.execute(request)
    duplicate = await handler.execute(request)

    assert first["armed"] is True
    assert first["simulated"] is True
    assert duplicate == {"duplicatePrevented": True}


@pytest.mark.asyncio
async def test_demo_stop_is_always_bounded_and_parameterless() -> None:
    backend = SimulatedBrainDemoBackend()
    handler = BrainDemoCommandHandler(backend, node_id="brain-demo-a")
    await backend.arm(settings())

    result = await handler.execute(command(STOP_CAPABILITY))

    assert result["armed"] is False
    assert result["active"] is False
