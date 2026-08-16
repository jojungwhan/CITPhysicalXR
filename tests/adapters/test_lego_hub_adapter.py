"""The LEGO adapter against a simulated hub (FR-047, FR-051, FR-052, FR-053).

No radio and no hub are involved. What is under test is everything between a
command arriving and a frame leaving, plus what the adapter does when the hub
misbehaves: refuses, goes quiet, drops the link, or has its button pressed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from cit_lego_pybricks import (
    SPIKE_ESSENTIAL,
    SPIKE_PRIME,
    FakeHubTransport,
    HubOwnership,
    HubSafetyLimits,
    HubTransportError,
    Operation,
    PortKind,
    PybricksHubAdapter,
)
from cit_lego_pybricks.diagnostics import bluetooth_unavailable
from cit_protocol import DeviceCommandIntent
from cit_test_harness import require_device_adapter

NOW = datetime(2026, 8, 16, 9, 0, 0, tzinfo=UTC)

DRIVING_BASE: dict[str, PortKind] = {
    "A": PortKind.MOTOR,
    "B": PortKind.MOTOR,
    "C": PortKind.DISTANCE,
    "D": PortKind.EMPTY,
    "E": PortKind.EMPTY,
    "F": PortKind.EMPTY,
}


def build_pair(
    *,
    ports: dict[str, PortKind] | None = None,
    limits: HubSafetyLimits | None = None,
    model: Any = SPIKE_PRIME,
) -> tuple[PybricksHubAdapter, FakeHubTransport]:
    port_map = dict(ports if ports is not None else DRIVING_BASE)
    transport = FakeHubTransport(hub_name="cit-hub-1", model=model, ports=port_map)
    adapter = PybricksHubAdapter(
        device_id="lego-spike-01",
        display_name="Class hub 1",
        transport=transport,
        model=model,
        ports=port_map,
        limits=limits,
    )
    return adapter, transport


def command_for(
    adapter: PybricksHubAdapter,
    *,
    capability: str = "motor.run",
    action: str = "set",
    arguments: dict[str, Any] | None = None,
    device_id: str | None = None,
    ttl_seconds: float = 5.0,
    idempotency_key: str | None = None,
) -> DeviceCommandIntent:
    return DeviceCommandIntent.model_validate(
        {
            "commandId": str(uuid4()),
            "sessionId": "lego-session",
            "deviceId": device_id or adapter.device_id,
            "capability": capability,
            "action": action,
            "arguments": arguments if arguments is not None else {"port": "A", "speed": 0.3},
            "source": "student_blocks",
            "issuedAt": NOW,
            "expiresAt": NOW + timedelta(seconds=ttl_seconds),
            "idempotencyKey": idempotency_key or str(uuid4()),
            "safetyContext": {"policyId": "lego-student", "armed": True, "deadmanActive": True},
        }
    )


def sent(transport: FakeHubTransport, operation: Operation) -> list[tuple[str, ...]]:
    return [frame.arguments for frame in transport.received if frame.operation is operation]


# --------------------------------------------------------------- the contract


@pytest.mark.asyncio
async def test_the_adapter_satisfies_the_shared_device_contract() -> None:
    adapter, _ = build_pair()

    assert require_device_adapter(adapter) is adapter
    assert await adapter.detect() is True


@pytest.mark.asyncio
async def test_a_hub_describes_itself_as_physical_with_derived_capabilities() -> None:
    adapter, _ = build_pair()

    descriptor = adapter.describe()
    capabilities = {capability.root for capability in descriptor.capabilities}

    assert descriptor.physical is True
    assert descriptor.adapterId == "lego-pybricks"
    assert descriptor.model == "spike-prime"
    assert {"motor.run", "drive.straight", "sensor.distance", "hub.battery"} <= capabilities
    # Nothing was plugged into a colour or force port, so those capabilities do
    # not exist and their blocks cannot appear (FR-051, FR-010).
    assert "sensor.color" not in capabilities
    assert "sensor.force" not in capabilities


# ------------------------------------------------------------------ handshake


@pytest.mark.asyncio
async def test_connecting_completes_a_handshake_and_reads_the_real_ports() -> None:
    adapter, transport = build_pair()
    transport.ports = {**DRIVING_BASE, "D": PortKind.FORCE}

    await adapter.connect(at=NOW)

    assert adapter.connected is True
    assert adapter.battery_percent == 87
    assert adapter.ports["D"] is PortKind.FORCE
    # The hub's own report wins over what the configuration guessed.
    assert "sensor.force" in adapter.capabilities
    event = adapter.drain_events()[0]
    assert event.name == "connection.connected"
    assert event.values.model_dump()["hubModel"] == "spike-prime"


@pytest.mark.asyncio
async def test_a_hub_of_the_wrong_model_is_refused_with_a_readable_reason() -> None:
    adapter, transport = build_pair()
    transport.reported_model_id = "spike-essential"

    with pytest.raises(HubTransportError) as error:
        await adapter.connect(at=NOW)

    assert error.value.diagnostic.code == "HUB_MODEL_MISMATCH"
    assert "spike-essential" in error.value.diagnostic.detail
    assert adapter.connected is False
    assert transport.connected is False


@pytest.mark.asyncio
async def test_a_hub_that_never_answers_produces_the_bring_up_diagnostic() -> None:
    adapter, transport = build_pair(limits=HubSafetyLimits(handshake_timeout_seconds=0.02))
    transport.silent = True

    with pytest.raises(HubTransportError) as error:
        await adapter.connect(at=NOW)

    diagnostic = error.value.diagnostic
    assert diagnostic.code == "HUB_HANDSHAKE_TIMEOUT"
    assert "hub agent" in diagnostic.recovery
    assert await adapter.detect() is False


@pytest.mark.asyncio
async def test_a_bluetooth_failure_keeps_its_own_diagnostic() -> None:
    adapter, transport = build_pair()
    transport.fail_connect = bluetooth_unavailable("no adapter found")

    with pytest.raises(HubTransportError) as error:
        await adapter.connect(at=NOW)

    assert error.value.diagnostic.code == "BLUETOOTH_UNAVAILABLE"
    assert "no adapter found" in str(error.value)


# ------------------------------------------------------------------- commands


@pytest.mark.asyncio
async def test_a_motor_command_becomes_one_bounded_frame() -> None:
    adapter, transport = build_pair()
    await adapter.connect(at=NOW)

    result = await adapter.execute(
        command_for(adapter, arguments={"port": "A", "speed": 0.3, "durationSeconds": 1.0}),
        now=NOW,
    )

    assert result.status == "completed"
    assert sent(transport, Operation.MOTOR_RUN) == [("A", "30", "1000")]


@pytest.mark.asyncio
async def test_motor_power_and_duration_are_capped_in_hub_units() -> None:
    adapter, transport = build_pair(
        limits=HubSafetyLimits(max_motor_percent=40, max_command_milliseconds=1500)
    )
    await adapter.connect(at=NOW)

    await adapter.execute(
        command_for(adapter, arguments={"port": "A", "speed": 5.0, "durationSeconds": 30}),
        now=NOW,
    )

    assert sent(transport, Operation.MOTOR_RUN) == [("A", "40", "1500")]


@pytest.mark.asyncio
async def test_a_movement_without_a_duration_still_gets_one() -> None:
    adapter, transport = build_pair()
    await adapter.connect(at=NOW)

    await adapter.execute(command_for(adapter, arguments={"port": "A", "speed": 0.2}), now=NOW)

    assert sent(transport, Operation.MOTOR_RUN)[0][2] == "2000"


@pytest.mark.asyncio
async def test_a_port_with_no_motor_in_it_is_refused_before_anything_is_sent() -> None:
    adapter, transport = build_pair()
    await adapter.connect(at=NOW)

    result = await adapter.execute(
        command_for(adapter, arguments={"port": "C", "speed": 0.2}), now=NOW
    )

    assert result.status == "rejected"
    assert result.message is not None
    assert "Port C has no motor" in result.message
    assert sent(transport, Operation.MOTOR_RUN) == []


@pytest.mark.asyncio
async def test_a_port_the_hub_does_not_have_names_the_ports_it_does() -> None:
    adapter, _ = build_pair(ports={"A": PortKind.MOTOR, "B": PortKind.MOTOR}, model=SPIKE_ESSENTIAL)
    await adapter.connect(at=NOW)

    result = await adapter.execute(
        command_for(adapter, arguments={"port": "F", "speed": 0.2}), now=NOW
    )

    assert result.status == "rejected"
    assert result.message is not None
    assert "has no port F" in result.message
    assert "A, B" in result.message


@pytest.mark.asyncio
async def test_an_unsupported_capability_is_refused() -> None:
    adapter, _ = build_pair()
    await adapter.connect(at=NOW)

    result = await adapter.execute(command_for(adapter, capability="gimbal.pitch_yaw"), now=NOW)

    assert result.status == "rejected"
    assert result.details is not None
    assert result.details.model_dump()["code"] == "DEVICE_CAPABILITY_UNSUPPORTED"


@pytest.mark.asyncio
async def test_a_command_for_another_device_is_never_retargeted() -> None:
    adapter, transport = build_pair()
    await adapter.connect(at=NOW)

    result = await adapter.execute(command_for(adapter, device_id="lego-spike-02"), now=NOW)

    assert result.status == "rejected"
    assert result.deviceId == "lego-spike-01"
    assert result.details is not None
    assert result.details.model_dump()["code"] == "DEVICE_NOT_FOUND"
    # Nothing but the handshake ever left: the command did not become a frame.
    assert [frame.operation for frame in transport.received] == [Operation.HELLO]


@pytest.mark.asyncio
async def test_a_command_to_a_disconnected_hub_is_refused() -> None:
    adapter, _ = build_pair()

    result = await adapter.execute(command_for(adapter), now=NOW)

    assert result.status == "rejected"
    assert result.details is not None
    assert result.details.model_dump()["code"] == "DEVICE_OFFLINE"


@pytest.mark.asyncio
async def test_expired_and_duplicate_commands_never_reach_the_hub() -> None:
    adapter, transport = build_pair()
    await adapter.connect(at=NOW)
    command = command_for(adapter, idempotency_key="lego-session:1")

    first = await adapter.execute(command, now=NOW)
    duplicate = await adapter.execute(command, now=NOW)
    expired = await adapter.execute(
        command_for(adapter, ttl_seconds=1), now=NOW + timedelta(seconds=2)
    )

    assert first.status == "completed"
    assert duplicate.status == "duplicate"
    assert expired.status == "expired"
    assert len(sent(transport, Operation.MOTOR_RUN)) == 1


@pytest.mark.asyncio
async def test_a_hub_refusal_comes_back_as_a_refusal_not_a_success() -> None:
    adapter, transport = build_pair()
    await adapter.connect(at=NOW)
    # The hub disagrees with the runtime about what is plugged in.
    transport.ports = {**DRIVING_BASE, "A": PortKind.EMPTY}

    result = await adapter.execute(command_for(adapter), now=NOW)

    assert result.status == "rejected"
    assert result.message is not None
    assert "BAD_PORT" in result.message


@pytest.mark.asyncio
async def test_a_hub_that_stops_acknowledging_is_treated_as_gone() -> None:
    adapter, transport = build_pair(limits=HubSafetyLimits(ack_timeout_seconds=0.02))
    await adapter.connect(at=NOW)
    adapter.drain_events()
    transport.silent = True

    result = await adapter.execute(command_for(adapter), now=NOW)

    assert result.status == "rejected"
    assert result.details is not None
    assert result.details.model_dump()["code"] == "DEVICE_OFFLINE"
    assert adapter.connected is False
    assert [event.name for event in adapter.drain_events()] == ["connection.failed"]


@pytest.mark.asyncio
async def test_a_sensor_read_arrives_as_a_sensor_event() -> None:
    adapter, transport = build_pair()
    await adapter.connect(at=NOW)
    adapter.drain_events()
    transport.set_sensor("distance", 275)

    result = await adapter.execute(command_for(adapter, capability="sensor.distance"), now=NOW)
    events = adapter.drain_events()

    assert result.status == "completed"
    assert sent(transport, Operation.SENSOR_READ) == [("C", "distance")]
    assert [event.name for event in events] == ["sensor.distance"]
    assert events[0].values.model_dump() == {"value": 275}


@pytest.mark.asyncio
async def test_a_sensor_with_no_port_says_so_instead_of_reading_nothing() -> None:
    adapter, _ = build_pair()
    await adapter.connect(at=NOW)
    adapter.capabilities = (*adapter.capabilities, "sensor.color")

    result = await adapter.execute(command_for(adapter, capability="sensor.color"), now=NOW)

    assert result.status == "rejected"
    assert result.message is not None
    assert "No port on this hub reports" in result.message


@pytest.mark.asyncio
async def test_display_text_is_filtered_rather_than_rejected() -> None:
    adapter, transport = build_pair()
    await adapter.connect(at=NOW)

    result = await adapter.execute(
        command_for(adapter, capability="hub.display", arguments={"text": "가자! go"}),
        now=NOW,
    )

    assert result.status == "completed"
    assert sent(transport, Operation.DISPLAY) == [("go",)]


# --------------------------------------------------------------------- safety


@pytest.mark.asyncio
async def test_disconnecting_stops_the_hub_first() -> None:
    adapter, transport = build_pair()
    await adapter.connect(at=NOW)
    await adapter.execute(command_for(adapter), now=NOW)

    await adapter.disconnect(at=NOW)

    assert transport.stops[-1] == "disconnect"
    assert transport.motors_running is False
    assert transport.connected is False


@pytest.mark.asyncio
async def test_stop_never_raises_even_when_the_link_is_already_gone() -> None:
    adapter, transport = build_pair()
    await adapter.connect(at=NOW)
    transport.simulate_link_loss()

    await adapter.stop(reason="instructor stop-all", at=NOW)

    assert [event.name for event in adapter.drain_events()][-1] == "safety.stopped"


@pytest.mark.asyncio
async def test_a_lost_link_is_noticed_by_the_ordinary_tick() -> None:
    adapter, transport = build_pair()
    await adapter.connect(at=NOW)
    adapter.drain_events()
    transport.simulate_link_loss("out of range")

    events = await adapter.tick(at=NOW + timedelta(seconds=1))

    assert adapter.connected is False
    assert [event.name for event in events] == ["connection.failed"]
    assert events[0].values.model_dump()["code"] == "HUB_LINK_LOST"


@pytest.mark.asyncio
async def test_the_tick_feeds_the_hub_watchdog_on_its_own_interval() -> None:
    adapter, transport = build_pair(limits=HubSafetyLimits(heartbeat_interval_seconds=0.2))
    await adapter.connect(at=NOW)

    await adapter.tick(at=NOW + timedelta(seconds=0.1))
    assert sent(transport, Operation.HEARTBEAT) == []

    await adapter.tick(at=NOW + timedelta(seconds=0.25))
    assert sent(transport, Operation.HEARTBEAT) == [("200",)]


@pytest.mark.asyncio
async def test_a_heartbeat_faster_than_the_hub_watchdog_is_required() -> None:
    with pytest.raises(ValueError, match="500 ms LEGO watchdog"):
        HubSafetyLimits(heartbeat_interval_seconds=0.6)


@pytest.mark.asyncio
async def test_the_button_on_the_hub_is_a_safety_event() -> None:
    adapter, transport = build_pair()
    await adapter.connect(at=NOW)
    adapter.drain_events()
    transport.simulate_button_press()

    events = await adapter.tick(at=NOW + timedelta(seconds=1))

    assert [event.name for event in events] == ["safety.hub_button"]
    assert events[0].category == "safety"
    assert transport.motors_running is False


@pytest.mark.asyncio
async def test_reconnecting_re_reads_capabilities_rather_than_trusting_memory() -> None:
    adapter, transport = build_pair()
    await adapter.connect(at=NOW)
    assert "sensor.color" not in adapter.capabilities

    transport.ports = {**DRIVING_BASE, "D": PortKind.COLOR}
    descriptor = await adapter.reconcile(at=NOW)

    assert "sensor.color" in adapter.capabilities
    assert "sensor.color" in {capability.root for capability in descriptor.capabilities}


# ------------------------------------------------------------------- autonomy


@pytest.mark.asyncio
async def test_running_a_lesson_never_downloads_a_program() -> None:
    """FR-046: firmware and program installation are never a side effect."""

    adapter, transport = build_pair()
    await adapter.connect(at=NOW)
    await adapter.execute(command_for(adapter), now=NOW)
    await adapter.tick(at=NOW + timedelta(seconds=1))

    assert transport.downloaded == []


@pytest.mark.asyncio
async def test_a_program_cannot_be_installed_while_the_host_owns_the_hub() -> None:
    adapter, transport = build_pair()
    await adapter.connect(at=NOW)
    with pytest.raises(PermissionError):
        await adapter.install_program("print('x')", name="lesson", at=NOW)

    assert transport.downloaded == []


@pytest.mark.asyncio
async def test_autonomous_ownership_is_instructor_only_and_excludes_host_commands() -> None:
    adapter, transport = build_pair()
    await adapter.connect(at=NOW)

    with pytest.raises(PermissionError):
        adapter.take_autonomous_ownership(instructor_id="")

    adapter.take_autonomous_ownership(instructor_id="teacher-1")
    refused = await adapter.execute(command_for(adapter), now=NOW)
    await adapter.install_program("print('x')", name="line-follower", at=NOW)

    assert adapter.ownership is HubOwnership.AUTONOMOUS
    assert refused.status == "rejected"
    assert refused.message is not None
    assert "host mode" in refused.message
    assert transport.downloaded == [("line-follower", "print('x')")]
    # Installing a program stops whatever was already turning.
    assert transport.stops[-1] == "program-install"

    adapter.take_host_ownership()
    assert (await adapter.execute(command_for(adapter), now=NOW)).status == "completed"
