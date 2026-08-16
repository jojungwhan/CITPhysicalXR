"""The instructor console's data and controls.

FR-058 failure policy, FR-065 device overview, FR-067 emergency controls.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from cit_device_simulator import FakeDeviceAdapter
from cit_runtime import ManualClock, Runtime, SafetyPolicy
from cit_runtime.sessions import ExecutionMode, FailurePolicy
from cit_runtime.status import DeviceStatusProjection
from cit_runtime.supervisor import WatchdogKind
from conftest import hold_deadman, make_command


@pytest.fixture
def console_runtime(
    clock: ManualClock,
    physical_policy: SafetyPolicy,
    physical_stand_in_fleet: tuple[FakeDeviceAdapter, ...],
    tmp_path: Path,
) -> Runtime:
    return Runtime(
        clock=clock,
        adapters=physical_stand_in_fleet,
        policies=(physical_policy,),
        physical_enabled=True,
        data_dir=tmp_path,
    )


async def ready_physical_session(runtime: Runtime, *devices: str) -> str:
    await runtime.start()
    session = runtime.create_session(
        project_id="lesson",
        user_id="student-1",
        execution_mode=ExecutionMode.PHYSICAL,
        instructor_id="teacher-1",
        safety_policy_id="classroom-physical",
    )
    runtime.bind_devices(session.session_id, list(devices))
    runtime.advance_to_ready(session.session_id)
    return session.session_id


# ------------------------------------------------------------------- FR-065


@pytest.mark.asyncio
async def test_the_overview_reports_what_a_device_actually_said(
    console_runtime: Runtime, clock: ManualClock
) -> None:
    session_id = await ready_physical_session(console_runtime, "fake-s1-main")
    console_runtime.arm(session_id=session_id, device_id="fake-s1-main", instructor_id="teacher-1")
    hold_deadman(console_runtime, "fake-s1-main")
    adapter = cast(FakeDeviceAdapter, console_runtime.registry.adapter("fake-s1-main"))
    await adapter.set_battery(71, at=clock.now())
    console_runtime.router.publish_all(adapter.drain_events())
    await console_runtime.submit(
        make_command(
            session_id=session_id,
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            armed=True,
        )
    )

    card = next(
        item for item in console_runtime.device_overview() if item["deviceId"] == "fake-s1-main"
    )

    # UI 11.3, field by field.
    assert card["displayName"]
    assert card["state"] == "connected"
    assert card["batteryPercent"] == 71
    assert card["armed"] is True
    assert card["armedBy"] == "teacher-1"
    assert card["activeStudentId"] == "student-1"
    assert card["activeSessionId"] == session_id
    assert card["safetyPolicyId"] == "classroom-physical"
    assert card["leaseSessionId"] == session_id
    assert card["lastCommand"]["capability"] == "drive.velocity"
    assert card["lastCommand"]["result"] == "completed"
    assert card["lastTelemetry"]["name"] == "telemetry.battery"


@pytest.mark.asyncio
async def test_a_device_that_never_reported_a_battery_says_so(
    console_runtime: Runtime,
) -> None:
    """A confident 100% for a device that never spoke is worse than a blank."""

    await console_runtime.start()

    card = next(
        item for item in console_runtime.device_overview() if item["deviceId"] == "fake-leap-main"
    )

    assert card["batteryPercent"] is None
    assert card["firmware"] is None
    assert card["lastCommand"] is None


@pytest.mark.asyncio
async def test_a_low_battery_becomes_a_warning(
    console_runtime: Runtime, clock: ManualClock
) -> None:
    await console_runtime.start()
    adapter = cast(FakeDeviceAdapter, console_runtime.registry.adapter("fake-s1-main"))
    await adapter.set_battery(11, at=clock.now())
    console_runtime.router.publish_all(adapter.drain_events())

    card = next(
        item for item in console_runtime.device_overview() if item["deviceId"] == "fake-s1-main"
    )

    assert any("battery 11%" in warning for warning in card["warnings"])


def test_a_replayed_event_is_ignored_by_the_projection() -> None:
    """FR-064. History must not repaint the console as though it were live."""

    from cit_protocol import DeviceEvent

    projection = DeviceStatusProjection()
    event = DeviceEvent.model_validate(
        {
            "eventId": "11111111-1111-4111-8111-111111111111",
            "deviceId": "fake-s1-main",
            "category": "telemetry",
            "name": "telemetry.battery",
            "values": {"percent": 99},
            "receivedAt": "2026-01-01T00:00:00+00:00",
            "historical": True,
        }
    )

    projection.observe(event)

    assert projection.get("fake-s1-main").battery_percent is None


# ------------------------------------------------------------------- FR-067


@pytest.mark.asyncio
async def test_revoking_a_lease_stops_the_device_before_releasing_it(
    console_runtime: Runtime,
) -> None:
    session_id = await ready_physical_session(console_runtime, "fake-s1-main")
    console_runtime.arm(session_id=session_id, device_id="fake-s1-main", instructor_id="teacher-1")
    hold_deadman(console_runtime, "fake-s1-main")
    await console_runtime.submit(
        make_command(
            session_id=session_id,
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            armed=True,
        )
    )
    assert console_runtime.pipeline.lease_holder("fake-s1-main") == session_id

    await console_runtime.revoke_lease("fake-s1-main", actor_id="teacher-1")

    assert console_runtime.pipeline.lease_holder("fake-s1-main") is None
    assert console_runtime.registry.get("fake-s1-main").assigned_session_id is None
    assert console_runtime.supervisor.is_armed("fake-s1-main") is False


@pytest.mark.asyncio
async def test_disabling_an_input_source_refuses_its_commands(
    console_runtime: Runtime,
) -> None:
    """FR-067: disable Leap input, disconnect Quest control."""

    session_id = await ready_physical_session(console_runtime, "fake-s1-main")
    console_runtime.set_input_enabled("leap", enabled=False, actor_id="teacher-1")

    dispatch = await console_runtime.submit(
        make_command(
            session_id=session_id,
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            source="leap",
        )
    )

    assert dispatch.accepted is False
    assert dispatch.error is not None
    assert "disabled" in dispatch.error.message


@pytest.mark.asyncio
async def test_a_disabled_source_can_still_be_re_enabled(
    console_runtime: Runtime,
) -> None:
    console_runtime.set_input_enabled("leap", enabled=False, actor_id="teacher-1")
    console_runtime.set_input_enabled("leap", enabled=True, actor_id="teacher-1")

    assert console_runtime.supervisor.disabled_sources() == frozenset()


@pytest.mark.asyncio
async def test_clearing_a_queue_does_not_stop_anything(console_runtime: Runtime) -> None:
    session_id = await ready_physical_session(console_runtime, "fake-s1-main")
    from cit_runtime.supervisor import CommandPriority

    console_runtime.pipeline.queue.push(
        make_command(session_id=session_id, device_id="fake-s1-main"),
        priority=CommandPriority.STUDENT_COMMAND,
    )

    cleared = console_runtime.clear_queue(device_id=None, actor_id="teacher-1")

    assert cleared == 1
    assert console_runtime.registry.get("fake-s1-main").state.value == "connected"


# ------------------------------------------------------------------- FR-058


@pytest.mark.asyncio
async def test_one_device_failing_stops_the_rest_of_a_physical_group(
    console_runtime: Runtime,
) -> None:
    """The PRD's default physical policy: stop coordinated movement."""

    session_id = await ready_physical_session(console_runtime, "fake-s1-main", "fake-lego-main")
    for device_id in ("fake-s1-main", "fake-lego-main"):
        console_runtime.arm(session_id=session_id, device_id=device_id, instructor_id="teacher-1")
        hold_deadman(console_runtime, device_id)

    dispatch = await console_runtime.submit(
        make_command(
            session_id=session_id,
            device_id="fake-s1-main",
            capability="weather.forecast",
            policy_id="classroom-physical",
            armed=True,
        )
    )

    assert dispatch.accepted is False
    # The partner was stopped and disarmed; the exact failed device is named.
    assert console_runtime.supervisor.is_armed("fake-lego-main") is False
    applied = [
        entry
        for entry in console_runtime.audit.entries()
        if entry.action.value == "safety.failure_policy_applied"
    ]
    assert applied[-1].context["deviceId"] == "fake-s1-main"
    assert applied[-1].context["result"] == "fake-lego-main"


@pytest.mark.asyncio
async def test_the_continue_policy_leaves_the_others_alone(
    console_runtime: Runtime,
) -> None:
    session_id = await ready_physical_session(console_runtime, "fake-s1-main", "fake-lego-main")
    console_runtime.set_failure_policy(session_id, FailurePolicy.CONTINUE)
    for device_id in ("fake-s1-main", "fake-lego-main"):
        console_runtime.arm(session_id=session_id, device_id=device_id, instructor_id="teacher-1")
        hold_deadman(console_runtime, device_id)

    await console_runtime.submit(
        make_command(
            session_id=session_id,
            device_id="fake-s1-main",
            capability="weather.forecast",
            policy_id="classroom-physical",
            armed=True,
        )
    )

    assert console_runtime.supervisor.is_armed("fake-lego-main") is True


@pytest.mark.asyncio
async def test_a_simulated_failure_does_not_stop_the_other_fakes(
    clock: ManualClock, physical_policy: SafetyPolicy, tmp_path: Path
) -> None:
    """Failure is not contagious in simulation, whatever the policy says."""

    runtime = Runtime(
        clock=clock, policies=(physical_policy,), physical_enabled=True, data_dir=tmp_path
    )
    await runtime.start()
    session = runtime.create_session(
        project_id="lesson", user_id="student-1", safety_policy_id="classroom-physical"
    )
    runtime.bind_devices(session.session_id, ["fake-s1-main", "fake-lego-main"])
    runtime.advance_to_ready(session.session_id)

    await runtime.submit(
        make_command(
            session_id=session.session_id,
            device_id="fake-s1-main",
            capability="weather.forecast",
            policy_id="classroom-physical",
        )
    )

    assert not [
        entry
        for entry in runtime.audit.entries()
        if entry.action.value == "safety.failure_policy_applied"
    ]


@pytest.mark.asyncio
async def test_a_stale_heartbeat_shows_up_as_a_warning(
    console_runtime: Runtime, clock: ManualClock
) -> None:
    await console_runtime.start()
    console_runtime.supervisor.heartbeat(
        device_id="fake-s1-main", kind=WatchdogKind.ADAPTER_PROCESS_HEARTBEAT
    )
    clock.advance(3.0)

    card = next(
        item for item in console_runtime.device_overview() if item["deviceId"] == "fake-s1-main"
    )

    assert any("adapter_process_heartbeat" in warning for warning in card["warnings"])
