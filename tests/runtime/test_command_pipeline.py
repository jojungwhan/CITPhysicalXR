"""The command pipeline, gate by gate, and the M1 fault matrix (AC-34).

Every test here asserts something a robot would otherwise do wrongly: move while
disarmed, move twice from one command, replay old motion after a reconnect, or
keep moving when the thing driving it went away.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from cit_runtime import (
    AuditAction,
    CommandPriority,
    ExecutionMode,
    ManualClock,
    Runtime,
    SessionState,
    WatchdogKind,
)
from conftest import make_command

pytestmark = pytest.mark.asyncio


async def ready_session(
    runtime: Runtime,
    *,
    device_id: str = "fake-s1-main",
    execution_mode: ExecutionMode = ExecutionMode.PHYSICAL,
    policy_id: str = "classroom-physical",
) -> str:
    """Discover, connect, bind, validate. The ordinary lesson setup."""

    await runtime.start()
    session = runtime.create_session(
        project_id="lesson-1",
        user_id="student-1",
        instructor_id="instructor-1",
        execution_mode=execution_mode,
        safety_policy_id=policy_id,
    )
    runtime.bind_devices(session.session_id, [device_id])
    runtime.advance_to_ready(session.session_id)
    return session.session_id


# ------------------------------------------------------------------ happy path


async def test_simulated_command_completes(runtime: Runtime) -> None:
    session_id = await ready_session(runtime, execution_mode=ExecutionMode.SIMULATION)
    dispatch = await runtime.submit(
        make_command(
            session_id=session_id, device_id="fake-s1-main", policy_id="classroom-physical"
        )
    )
    assert dispatch.accepted
    assert dispatch.result is not None
    assert dispatch.result.status == "completed"


async def test_a_session_can_send_more_than_one_command(runtime: Runtime) -> None:
    """Regression: the per-command lease must be renewable by its holder.

    Found by driving the Studio in a browser -- the second click came back
    DEVICE_LEASE_CONFLICT against the session's own lease.
    """

    session_id = await ready_session(runtime, execution_mode=ExecutionMode.SIMULATION)
    for _ in range(5):
        dispatch = await runtime.submit(
            make_command(
                session_id=session_id,
                device_id="fake-s1-main",
                policy_id="classroom-physical",
            )
        )
        assert dispatch.accepted, dispatch.error


async def test_physical_command_needs_an_arm(runtime: Runtime) -> None:
    session_id = await ready_session(runtime)
    dispatch = await runtime.submit(
        make_command(
            session_id=session_id, device_id="fake-s1-main", policy_id="classroom-physical"
        )
    )
    assert not dispatch.accepted
    assert dispatch.error is not None
    assert dispatch.error.code == "DEVICE_NOT_ARMED"


async def test_armed_physical_command_reaches_the_adapter(runtime: Runtime) -> None:
    session_id = await ready_session(runtime)
    runtime.arm(session_id=session_id, device_id="fake-s1-main", instructor_id="instructor-1")
    dispatch = await runtime.submit(
        make_command(
            session_id=session_id,
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            armed=True,
        )
    )
    assert dispatch.accepted
    assert dispatch.priority is CommandPriority.STUDENT_COMMAND


# ----------------------------------------------------------------- fault: identity


async def test_a_duplicate_command_never_executes_twice(runtime: Runtime) -> None:
    session_id = await ready_session(runtime, execution_mode=ExecutionMode.SIMULATION)
    key = "idempotency-1"
    first = await runtime.submit(
        make_command(
            session_id=session_id,
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            idempotency_key=key,
        )
    )
    second = await runtime.submit(
        make_command(
            session_id=session_id,
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            idempotency_key=key,
        )
    )
    assert first.accepted
    assert not second.accepted
    assert second.error is not None
    assert second.error.code == "COMMAND_DUPLICATE"


async def test_an_expired_command_is_never_executed(runtime: Runtime, clock: ManualClock) -> None:
    """AC-22. A reconnect must not resurrect motion that timed out."""

    session_id = await ready_session(runtime, execution_mode=ExecutionMode.SIMULATION)
    command = make_command(
        session_id=session_id,
        device_id="fake-s1-main",
        policy_id="classroom-physical",
        now=clock.now(),
        ttl_seconds=1.0,
    )
    clock.advance(2.0)
    dispatch = await runtime.submit(command)
    assert not dispatch.accepted
    assert dispatch.error is not None
    assert dispatch.error.code == "COMMAND_EXPIRED"


async def test_unknown_device_is_refused(runtime: Runtime) -> None:
    session_id = await ready_session(runtime, execution_mode=ExecutionMode.SIMULATION)
    dispatch = await runtime.submit(make_command(session_id=session_id, device_id="no-such-device"))
    assert dispatch.error is not None
    assert dispatch.error.code == "DEVICE_NOT_FOUND"


async def test_unknown_session_is_refused(runtime: Runtime) -> None:
    await runtime.start()
    dispatch = await runtime.submit(
        make_command(session_id="never-created", device_id="fake-s1-main")
    )
    assert dispatch.error is not None
    assert dispatch.error.code == "DEVICE_NOT_ASSIGNED"


async def test_ended_session_cannot_command(runtime: Runtime) -> None:
    session_id = await ready_session(runtime, execution_mode=ExecutionMode.SIMULATION)
    runtime.transition(session_id, SessionState.STOPPING)
    runtime.transition(session_id, SessionState.STOPPED)
    dispatch = await runtime.submit(
        make_command(
            session_id=session_id, device_id="fake-s1-main", policy_id="classroom-physical"
        )
    )
    assert dispatch.error is not None
    assert dispatch.error.code == "SAFETY_POLICY_DENIED"


# ------------------------------------------------------- fault: exclusive access


async def test_two_sessions_cannot_hold_one_device(runtime: Runtime) -> None:
    first = await ready_session(runtime, execution_mode=ExecutionMode.SIMULATION)
    second = runtime.create_session(
        project_id="lesson-2", user_id="student-2", execution_mode=ExecutionMode.SIMULATION
    )
    with pytest.raises(Exception, match="already assigned"):
        runtime.bind_devices(second.session_id, ["fake-s1-main"])
    assert runtime.registry.get("fake-s1-main").assigned_session_id == first


# ------------------------------------------------------------- fault: watchdogs


async def test_motion_watchdog_stops_the_device(runtime: Runtime, clock: ManualClock) -> None:
    session_id = await ready_session(runtime)
    runtime.arm(session_id=session_id, device_id="fake-s1-main", instructor_id="instructor-1")
    runtime.heartbeat(device_id="fake-s1-main", kind=WatchdogKind.S1_CONTINUOUS_MOTION)

    clock.advance(0.4)
    fired = await runtime.tick()

    assert fired == 1
    assert not runtime.supervisor.is_armed("fake-s1-main")
    stop_entries = runtime.audit.entries(action=AuditAction.WATCHDOG_FIRED)
    assert stop_entries[-1].context["watchdog"] == WatchdogKind.S1_CONTINUOUS_MOTION.value


async def test_quest_deadman_timeout_disarms_without_stopping(
    runtime: Runtime, clock: ManualClock
) -> None:
    session_id = await ready_session(runtime, device_id="fake-quest-main")
    runtime.arm(session_id=session_id, device_id="fake-quest-main", instructor_id="instructor-1")
    runtime.heartbeat(device_id="fake-quest-main", kind=WatchdogKind.QUEST_DEADMAN_HEARTBEAT)

    clock.advance(0.5)
    await runtime.tick()

    assert not runtime.supervisor.is_armed("fake-quest-main")


async def test_a_fired_watchdog_does_not_fire_forever(runtime: Runtime, clock: ManualClock) -> None:
    await ready_session(runtime)
    runtime.heartbeat(device_id="fake-s1-main", kind=WatchdogKind.S1_CONTINUOUS_MOTION)
    clock.advance(0.4)
    assert await runtime.tick() == 1
    clock.advance(10.0)
    assert await runtime.tick() == 0


# ------------------------------------------------ fault: disconnect and recovery


async def test_disconnect_disarms_and_marks_the_session(runtime: Runtime) -> None:
    session_id = await ready_session(runtime)
    runtime.arm(session_id=session_id, device_id="fake-s1-main", instructor_id="instructor-1")

    await runtime.pipeline.handle_disconnect("fake-s1-main", reason="ble link lost")

    assert not runtime.supervisor.is_armed("fake-s1-main")
    assert runtime.sessions.get(session_id).state is SessionState.DISCONNECTED
    assert runtime.registry.get("fake-s1-main").failure_reason == "ble link lost"


async def test_commands_after_disconnect_are_refused(runtime: Runtime) -> None:
    session_id = await ready_session(runtime)
    runtime.arm(session_id=session_id, device_id="fake-s1-main", instructor_id="instructor-1")
    await runtime.pipeline.handle_disconnect("fake-s1-main", reason="adapter crash")

    dispatch = await runtime.submit(
        make_command(
            session_id=session_id,
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            armed=True,
        )
    )
    assert not dispatch.accepted


async def test_adapter_failure_injection_stops_the_device(runtime: Runtime) -> None:
    await ready_session(runtime)
    adapter = runtime.registry.adapter("fake-s1-main")
    await adapter.inject_failure("process", at=runtime.clock.now())  # type: ignore[attr-defined]
    events = adapter.drain_events()
    names = {event.name for event in events}
    assert "safety.stopped" in names
    assert "connection.failed" in names


# -------------------------------------------------------- FR-067 stop and clear


async def test_stop_all_stops_every_device_and_disarms(runtime: Runtime) -> None:
    session_id = await ready_session(runtime)
    runtime.arm(session_id=session_id, device_id="fake-s1-main", instructor_id="instructor-1")

    stopped = await runtime.stop_all(actor_id="instructor-1")

    assert set(stopped) == {
        "fake-s1-main",
        "fake-lego-main",
        "fake-leap-main",
        "fake-quest-main",
    }
    assert not runtime.supervisor.is_armed("fake-s1-main")
    assert runtime.audit.entries(action=AuditAction.STOP_ALL)


async def test_stop_device_clears_only_that_devices_queue(runtime: Runtime) -> None:
    session_id = await ready_session(runtime, execution_mode=ExecutionMode.SIMULATION)
    queue = runtime.pipeline.queue
    for device_id in ("fake-s1-main", "fake-lego-main", "fake-s1-main"):
        queue.push(
            make_command(session_id=session_id, device_id=device_id),
            priority=CommandPriority.STUDENT_COMMAND,
        )

    cleared = await runtime.pipeline.stop_device(
        "fake-s1-main", reason="manual", actor_id="instructor-1"
    )

    assert cleared == 2
    assert queue.peek_device_ids() == ("fake-lego-main",)


# ------------------------------------------------------------------- FR-071 bounds


async def test_speed_is_clamped_before_the_adapter_sees_it(runtime: Runtime) -> None:
    session_id = await ready_session(runtime)
    runtime.arm(session_id=session_id, device_id="fake-s1-main", instructor_id="instructor-1")

    dispatch = await runtime.submit(
        make_command(
            session_id=session_id,
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            arguments={"speed": 9.9, "durationSeconds": 1.0},
            armed=True,
        )
    )

    assert dispatch.accepted
    assert "speed" in dispatch.clamped_fields
    clamped = runtime.audit.entries(action=AuditAction.COMMAND_CLAMPED)
    assert clamped[-1].context["clampedFields"] == ["speed"]


# -------------------------------------------------------------------- FR-083 audit


async def test_every_denial_is_audited(runtime: Runtime) -> None:
    session_id = await ready_session(runtime)
    await runtime.submit(
        make_command(
            session_id=session_id, device_id="fake-s1-main", policy_id="classroom-physical"
        )
    )
    denials = runtime.audit.entries(action=AuditAction.COMMAND_DENIED)
    assert len(denials) == 1
    assert denials[0].context["code"] == "DEVICE_NOT_ARMED"


async def test_arm_ttl_override_is_respected(runtime: Runtime, clock: ManualClock) -> None:
    session_id = await ready_session(runtime)
    runtime.arm(
        session_id=session_id,
        device_id="fake-s1-main",
        instructor_id="instructor-1",
        ttl=timedelta(seconds=30),
    )
    clock.advance(31)
    assert not runtime.supervisor.is_armed("fake-s1-main")


async def test_arming_before_validation_is_refused(runtime: Runtime) -> None:
    await runtime.start()
    session = runtime.create_session(
        project_id="lesson-1",
        user_id="student-1",
        instructor_id="instructor-1",
        execution_mode=ExecutionMode.PHYSICAL,
        safety_policy_id="classroom-physical",
    )
    runtime.bind_devices(session.session_id, ["fake-s1-main"])
    with pytest.raises(PermissionError, match="validate"):
        runtime.arm(
            session_id=session.session_id,
            device_id="fake-s1-main",
            instructor_id="instructor-1",
        )


async def test_simulation_runtime_refuses_a_physical_session() -> None:
    """FR-062. Physical mode is opt-in at the runtime, not per request."""

    simulation_only = Runtime(physical_enabled=False)
    with pytest.raises(PermissionError, match="simulation only"):
        simulation_only.create_session(
            project_id="p", user_id="u", execution_mode=ExecutionMode.PHYSICAL
        )


async def test_a_finished_session_hands_its_devices_back(runtime: Runtime) -> None:
    """Otherwise the first lesson of the day holds every robot until restart."""

    first = await ready_session(runtime, execution_mode=ExecutionMode.SIMULATION)
    runtime.arm(session_id=first, device_id="fake-s1-main", instructor_id="instructor-1")
    assert runtime.registry.get("fake-s1-main").assigned_session_id == first

    runtime.transition(first, SessionState.STOPPING)
    runtime.transition(first, SessionState.COMPLETED)

    assert runtime.registry.get("fake-s1-main").assigned_session_id is None
    assert not runtime.supervisor.is_armed("fake-s1-main")

    # The next class can now bind the same robot.
    second = runtime.create_session(
        project_id="lesson-2", user_id="student-2", execution_mode=ExecutionMode.SIMULATION
    )
    bound = runtime.bind_devices(second.session_id, ["fake-s1-main"])
    assert bound.device_bindings == ("fake-s1-main",)


async def test_an_emergency_stopped_session_also_releases(runtime: Runtime) -> None:
    session_id = await ready_session(runtime, execution_mode=ExecutionMode.SIMULATION)
    runtime.transition(session_id, SessionState.EMERGENCY_STOPPED, reason="e-stop")
    assert runtime.registry.get("fake-s1-main").assigned_session_id is None
