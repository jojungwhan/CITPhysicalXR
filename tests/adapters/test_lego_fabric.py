from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cit_lego_pybricks import build_adapter
from cit_lego_pybricks.adapter import PybricksHubAdapter
from cit_lego_pybricks.fabric_bridge import LegoCommandHandler, LegoTelemetryPoller
from cit_lego_pybricks.fabric_contract import build_manifest, build_node
from cit_lego_pybricks.fakes import FakeHubTransport
from cit_lego_pybricks.hubs import PortKind, hub_model
from cit_lego_pybricks.protocol import Operation
from cit_protocol import FabricResolvedCommand


def _adapter() -> PybricksHubAdapter:
    model = hub_model("spike-prime")
    ports = {"A": PortKind.MOTOR, "B": PortKind.MOTOR, "C": PortKind.DISTANCE}
    return build_adapter(
        device_id="lego-a",
        display_name="Classroom LEGO",
        transport=FakeHubTransport(hub_name="CIT LEGO A", model=model, ports=ports),
        model_id=model.model_id,
        ports=ports,
    )


def _sensor_adapter() -> tuple[PybricksHubAdapter, FakeHubTransport]:
    model = hub_model("spike-essential")
    ports = {"A": PortKind.DISTANCE, "B": PortKind.EMPTY}
    transport = FakeHubTransport(hub_name="CIT Sensor Hub", model=model, ports=ports)
    return (
        build_adapter(
            device_id="lego-sensor-a",
            display_name="CIT Sensor Hub",
            transport=transport,
            model_id=model.model_id,
            ports=ports,
        ),
        transport,
    )


def _command(parameters: dict[str, object]) -> FabricResolvedCommand:
    now = datetime.now(UTC)
    return FabricResolvedCommand.model_validate(
        {
            "commandId": str(uuid4()),
            "requestMessageId": str(uuid4()),
            "schemaVersion": "1.0",
            "sessionId": "session-a",
            "targetNodeId": "lego-a",
            "action": "mobility.ground.set_velocity",
            "parameters": parameters,
            "priority": "student_interaction",
            "idempotencyKey": str(uuid4()),
            "requestedAt": now,
            "expiresAt": now + timedelta(seconds=1),
            "safetyProfile": "classroom-ground-robot",
            "correlationId": str(uuid4()),
        }
    )


def test_lego_node_advertises_canonical_capabilities_from_actual_ports() -> None:
    adapter = _adapter()
    manifest = build_manifest()
    node = build_node(
        adapter,
        at=datetime.now(UTC),
        host_id="host-a",
        site_id="site-a",
        room_id="room-a",
        simulated=True,
    )

    assert manifest.pluginId == "cit.lego-pybricks"
    assert {item.name for item in node.consumedCapabilities} == {
        "mobility.ground.set_velocity",
        "mobility.ground.stop",
    }
    assert node.metadata.model_dump()["ports"] == {
        "A": "motor",
        "B": "motor",
        "C": "distance",
    }


def test_lego_translation_rejects_strafe_for_differential_drive() -> None:
    handler = LegoCommandHandler(_adapter())
    with pytest.raises(ValueError, match="cannot strafe"):
        handler.translate(
            _command(
                {
                    "forwardMetersPerSecond": 0.1,
                    "rightMetersPerSecond": 0.1,
                    "clockwiseRadiansPerSecond": 0.0,
                }
            )
        )


@pytest.mark.asyncio
async def test_sensor_only_monitoring_polls_without_a_motor_operation() -> None:
    adapter, transport = _sensor_adapter()
    now = datetime.now(UTC)
    await adapter.connect(at=now)
    adapter.drain_events()
    poller = LegoTelemetryPoller(adapter, session_id="monitoring-session")

    await poller.poll_if_due(at=now)
    events = adapter.drain_events()

    assert [event.name for event in events] == ["telemetry.battery"]
    assert events[0].values.model_dump(mode="json") == {"value": 87}
    assert Operation.SENSOR_READ in {frame.operation for frame in transport.received}
    assert not (
        {Operation.MOTOR_RUN, Operation.DRIVE} & {frame.operation for frame in transport.received}
    )
