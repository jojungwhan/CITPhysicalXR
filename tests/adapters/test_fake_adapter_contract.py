from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cit_device_simulator import (
    FakeDeviceAdapter,
    create_fake_leap_adapter,
    create_fake_lego_adapter,
    create_fake_quest_adapter,
    create_fake_s1_adapter,
)
from cit_protocol import DeviceCommandIntent
from cit_test_harness import require_device_adapter

AdapterFactory = Callable[[], FakeDeviceAdapter]
FACTORIES: tuple[AdapterFactory, ...] = (
    create_fake_s1_adapter,
    create_fake_leap_adapter,
    create_fake_lego_adapter,
    create_fake_quest_adapter,
)
BATTERY_FACTORIES: tuple[AdapterFactory, ...] = (
    create_fake_s1_adapter,
    create_fake_lego_adapter,
    create_fake_quest_adapter,
)
NOW = datetime(2026, 8, 16, 4, 0, 0, tzinfo=UTC)


def command_for(adapter: FakeDeviceAdapter, **overrides: Any) -> DeviceCommandIntent:
    values: dict[str, Any] = {
        "commandId": "45e8743a-8c95-40ed-91f0-9285929355f4",
        "sessionId": "contract-session",
        "deviceId": adapter.device_id,
        "capability": adapter.capabilities[0],
        "action": "execute",
        "arguments": {},
        "source": "system",
        "issuedAt": "2026-08-16T04:00:00.000Z",
        "expiresAt": "2026-08-16T04:00:00.400Z",
        "idempotencyKey": "contract-session:command-1",
        "safetyContext": {"policyId": "simulation-only", "armed": True},
    }
    values.update(overrides)
    return DeviceCommandIntent.model_validate(values)


@pytest.mark.parametrize("factory", FACTORIES)
@pytest.mark.asyncio
async def test_fake_adapter_detects_and_describes_exact_device(
    factory: AdapterFactory,
) -> None:
    adapter = factory()

    assert require_device_adapter(adapter) is adapter
    assert await adapter.detect() is True
    descriptor = adapter.describe()

    assert descriptor.deviceId == adapter.device_id
    assert descriptor.adapterId.startswith("fake-")
    assert descriptor.physical is False
    assert tuple(capability.root for capability in descriptor.capabilities) == adapter.capabilities


@pytest.mark.parametrize("factory", FACTORIES)
@pytest.mark.asyncio
async def test_fake_adapter_connects_and_disconnects_with_events(
    factory: AdapterFactory,
) -> None:
    adapter = factory()

    await adapter.connect(at=NOW)
    await adapter.disconnect(at=NOW)

    events = adapter.drain_events()
    assert [event.name for event in events] == [
        "connection.connected",
        "connection.disconnected",
    ]
    assert [event.sequence for event in events] == [1, 2]
    assert all(event.deviceId == adapter.device_id for event in events)


@pytest.mark.parametrize("factory", FACTORIES)
@pytest.mark.asyncio
async def test_fake_adapter_executes_supported_command(factory: AdapterFactory) -> None:
    adapter = factory()
    await adapter.connect(at=NOW)

    result = await adapter.execute(command_for(adapter), now=NOW)

    assert result.deviceId == adapter.device_id
    assert result.status == "completed"
    assert result.details is not None
    assert result.details.model_dump()["capability"] == adapter.capabilities[0]


@pytest.mark.parametrize("factory", FACTORIES)
@pytest.mark.asyncio
async def test_fake_adapter_rejects_unsupported_capability(
    factory: AdapterFactory,
) -> None:
    adapter = factory()
    await adapter.connect(at=NOW)

    result = await adapter.execute(
        command_for(adapter, capability="unsupported.action"),
        now=NOW,
    )

    assert result.status == "rejected"
    assert result.details is not None
    assert result.details.model_dump()["code"] == "DEVICE_CAPABILITY_UNSUPPORTED"


@pytest.mark.parametrize("factory", FACTORIES)
@pytest.mark.asyncio
async def test_fake_adapter_never_retargets_a_command(factory: AdapterFactory) -> None:
    adapter = factory()
    await adapter.connect(at=NOW)

    result = await adapter.execute(
        command_for(adapter, deviceId="some-other-device"),
        now=NOW,
    )

    assert result.status == "rejected"
    assert result.deviceId == adapter.device_id
    assert result.details is not None
    assert result.details.model_dump()["code"] == "DEVICE_NOT_FOUND"


@pytest.mark.parametrize("factory", FACTORIES)
@pytest.mark.asyncio
async def test_fake_adapter_rejects_expired_command(factory: AdapterFactory) -> None:
    adapter = factory()
    await adapter.connect(at=NOW)

    result = await adapter.execute(
        command_for(adapter),
        now=NOW + timedelta(milliseconds=400),
    )

    assert result.status == "expired"
    assert result.details is not None
    assert result.details.model_dump()["code"] == "COMMAND_EXPIRED"


@pytest.mark.parametrize("factory", FACTORIES)
@pytest.mark.asyncio
async def test_fake_adapter_suppresses_duplicate_command(factory: AdapterFactory) -> None:
    adapter = factory()
    await adapter.connect(at=NOW)
    command = command_for(adapter)

    first = await adapter.execute(command, now=NOW)
    duplicate = await adapter.execute(command, now=NOW)

    assert first.status == "completed"
    assert duplicate.status == "duplicate"
    assert duplicate.details is not None
    assert duplicate.details.model_dump()["code"] == "COMMAND_DUPLICATE"


@pytest.mark.parametrize("factory", FACTORIES)
@pytest.mark.asyncio
async def test_fake_adapter_emits_normalized_telemetry(factory: AdapterFactory) -> None:
    adapter = factory()
    await adapter.connect(at=NOW)
    adapter.drain_events()

    emitted = await adapter.emit_telemetry(
        "telemetry.sample",
        {"batteryPercent": 24, "warning": True},
        at=NOW,
    )

    assert emitted.category == "telemetry"
    assert emitted.name == "telemetry.sample"
    assert emitted.values.model_dump() == {"batteryPercent": 24, "warning": True}
    assert adapter.drain_events() == (emitted,)


@pytest.mark.parametrize("factory", FACTORIES)
@pytest.mark.asyncio
async def test_fake_adapter_stop_is_observable(factory: AdapterFactory) -> None:
    adapter = factory()
    await adapter.connect(at=NOW)
    adapter.drain_events()

    await adapter.stop(reason="contract-test", at=NOW)

    events = adapter.drain_events()
    assert [event.name for event in events] == ["safety.stopped"]
    assert events[0].values.model_dump() == {"reason": "contract-test"}


@pytest.mark.parametrize("factory", FACTORIES)
@pytest.mark.asyncio
async def test_fake_adapter_rejects_command_while_disconnected(
    factory: AdapterFactory,
) -> None:
    adapter = factory()

    result = await adapter.execute(command_for(adapter), now=NOW)

    assert result.status == "rejected"
    assert result.details is not None
    assert result.details.model_dump()["code"] == "DEVICE_OFFLINE"


@pytest.mark.parametrize("factory", FACTORIES)
@pytest.mark.parametrize("failure_kind", ("network", "process"))
@pytest.mark.asyncio
async def test_fake_adapter_recovers_and_reconciles_after_failure(
    factory: AdapterFactory, failure_kind: str
) -> None:
    adapter = factory()
    await adapter.connect(at=NOW)
    adapter.drain_events()

    await adapter.inject_failure(failure_kind, at=NOW)

    assert await adapter.detect() is False
    failure_events = adapter.drain_events()
    assert [event.name for event in failure_events] == [
        "safety.stopped",
        "connection.failed",
    ]
    assert failure_events[-1].values.model_dump()["failureKind"] == failure_kind

    await adapter.recover(at=NOW)
    assert await adapter.detect() is True
    await adapter.connect(at=NOW)
    descriptor = await adapter.reconcile(at=NOW)

    assert descriptor.deviceId == adapter.device_id
    assert [event.name for event in adapter.drain_events()] == [
        "connection.recovered",
        "connection.connected",
        "diagnostic.reconciled",
    ]


@pytest.mark.parametrize("factory", BATTERY_FACTORIES)
@pytest.mark.asyncio
async def test_battery_capable_fake_can_emit_warning(factory: AdapterFactory) -> None:
    adapter = factory()

    event = await adapter.set_battery(19, at=NOW)

    assert event.name == "telemetry.battery_warning"
    assert event.values.model_dump() == {"percent": 19, "warning": True}


@pytest.mark.asyncio
async def test_lego_fake_can_emit_sensor_event() -> None:
    adapter = create_fake_lego_adapter()

    event = await adapter.emit_sensor(
        "sensor.distance",
        {"millimeters": 320},
        at=NOW,
    )

    assert event.category == "sensor"
    assert event.name == "sensor.distance"
    assert event.values.model_dump() == {"millimeters": 320}
