"""FR-066, FR-070, FR-071, FR-072, FR-074. The supervisor answers alone."""

from __future__ import annotations

from datetime import timedelta

import pytest
from cit_runtime import (
    ArmingError,
    CommandPriority,
    ManualClock,
    SafetyPolicy,
    SafetySupervisor,
    WatchdogAction,
    WatchdogKind,
    classify_priority,
)
from cit_runtime.supervisor import DEFAULT_WATCHDOG_TIMEOUTS, MotionBounds
from conftest import make_command

DEVICES = ("fake-s1-main",)


@pytest.fixture
def supervisor(clock: ManualClock, physical_policy: SafetyPolicy) -> SafetySupervisor:
    return SafetySupervisor(clock=clock, policies=(physical_policy,))


def arm(supervisor: SafetySupervisor, *, session_id: str = "session-1") -> None:
    supervisor.arm(
        device_id="fake-s1-main",
        session_id=session_id,
        instructor_id="instructor-1",
        policy_id="classroom-physical",
        program_validated=True,
    )


# --------------------------------------------------------------------- arming


def test_arming_requires_an_instructor(supervisor: SafetySupervisor) -> None:
    with pytest.raises(ArmingError, match="instructor"):
        supervisor.arm(
            device_id="fake-s1-main",
            session_id="session-1",
            instructor_id="",
            policy_id="classroom-physical",
            program_validated=True,
        )


def test_arming_requires_a_validated_program(supervisor: SafetySupervisor) -> None:
    with pytest.raises(ArmingError, match="validate"):
        supervisor.arm(
            device_id="fake-s1-main",
            session_id="session-1",
            instructor_id="instructor-1",
            policy_id="classroom-physical",
            program_validated=False,
        )


def test_arm_expires_by_itself(supervisor: SafetySupervisor, clock: ManualClock) -> None:
    arm(supervisor)
    assert supervisor.is_armed("fake-s1-main")
    clock.advance(timedelta(minutes=5, seconds=1).total_seconds())
    assert not supervisor.is_armed("fake-s1-main")


def test_movement_after_arm_expiry_is_denied(
    supervisor: SafetySupervisor, clock: ManualClock
) -> None:
    arm(supervisor)
    clock.advance(timedelta(minutes=6).total_seconds())
    verdict = supervisor.evaluate(
        make_command(
            session_id="session-1",
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            armed=True,
        ),
        session_device_ids=DEVICES,
        physical=True,
    )
    assert not verdict.allowed
    assert verdict.code == "DEVICE_NOT_ARMED"


def test_another_sessions_arm_does_not_authorize_this_one(
    supervisor: SafetySupervisor,
) -> None:
    arm(supervisor, session_id="session-other")
    verdict = supervisor.evaluate(
        make_command(
            session_id="session-1",
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            armed=True,
        ),
        session_device_ids=DEVICES,
        physical=True,
    )
    assert not verdict.allowed
    assert verdict.code == "DEVICE_LEASE_CONFLICT"


# ------------------------------------------------------------------ AI policy


def test_agent_mesh_may_not_initiate_movement(supervisor: SafetySupervisor) -> None:
    """FR-074. Armed, dead-man held, confident -- still denied."""

    arm(supervisor)
    verdict = supervisor.evaluate(
        make_command(
            session_id="session-1",
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            source="agent_mesh",
            armed=True,
            input_confidence=1.0,
        ),
        session_device_ids=DEVICES,
        physical=True,
    )
    assert not verdict.allowed
    assert verdict.code == "SAFETY_POLICY_DENIED"
    assert verdict.priority is CommandPriority.AI_OR_WEARABLE_PROPOSAL


def test_agent_mesh_may_still_stop_a_device(supervisor: SafetySupervisor) -> None:
    verdict = supervisor.evaluate(
        make_command(
            session_id="session-1",
            device_id="fake-s1-main",
            capability="drive.stop",
            action="stop",
            source="agent_mesh",
        ),
        session_device_ids=DEVICES,
        physical=True,
    )
    assert verdict.allowed


# --------------------------------------------------------------- dead-man etc.


def test_movement_without_deadman_is_denied(supervisor: SafetySupervisor) -> None:
    arm(supervisor)
    verdict = supervisor.evaluate(
        make_command(
            session_id="session-1",
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            armed=True,
            deadman_active=False,
        ),
        session_device_ids=DEVICES,
        physical=True,
    )
    assert not verdict.allowed
    assert "dead-man" in (verdict.reason or "")


def test_low_confidence_input_is_denied(supervisor: SafetySupervisor) -> None:
    arm(supervisor)
    verdict = supervisor.evaluate(
        make_command(
            session_id="session-1",
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            armed=True,
            input_confidence=0.2,
        ),
        session_device_ids=DEVICES,
        physical=True,
    )
    assert not verdict.allowed
    assert "confidence" in (verdict.reason or "")


def test_unbound_device_is_denied(supervisor: SafetySupervisor) -> None:
    verdict = supervisor.evaluate(
        make_command(session_id="session-1", device_id="fake-lego-main"),
        session_device_ids=DEVICES,
        physical=False,
    )
    assert not verdict.allowed
    assert verdict.code == "DEVICE_NOT_ASSIGNED"


def test_blaster_capability_is_denied_by_default(supervisor: SafetySupervisor) -> None:
    verdict = supervisor.evaluate(
        make_command(
            session_id="session-1",
            device_id="fake-s1-main",
            capability="weapon.blaster",
            action="fire",
            policy_id="classroom-physical",
        ),
        session_device_ids=DEVICES,
        physical=True,
    )
    assert not verdict.allowed
    assert verdict.code == "DEVICE_CAPABILITY_UNSUPPORTED"


def test_unknown_policy_fails_closed(supervisor: SafetySupervisor) -> None:
    verdict = supervisor.evaluate(
        make_command(session_id="session-1", device_id="fake-s1-main", policy_id="not-registered"),
        session_device_ids=DEVICES,
        physical=True,
    )
    assert not verdict.allowed
    assert verdict.code == "SAFETY_POLICY_DENIED"


# ---------------------------------------------------------------- FR-071 bounds


def test_speed_above_the_ceiling_is_clamped(supervisor: SafetySupervisor) -> None:
    arm(supervisor)
    verdict = supervisor.evaluate(
        make_command(
            session_id="session-1",
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            arguments={"speed": 5.0, "durationSeconds": 0.5},
            armed=True,
        ),
        session_device_ids=DEVICES,
        physical=True,
    )
    assert verdict.allowed
    assert verdict.bounded_arguments["speed"] == 0.5
    assert "speed" in verdict.clamped_fields


def test_reverse_speed_is_clamped_symmetrically(supervisor: SafetySupervisor) -> None:
    arm(supervisor)
    verdict = supervisor.evaluate(
        make_command(
            session_id="session-1",
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            arguments={"speed": -5.0, "durationSeconds": 0.5},
            armed=True,
        ),
        session_device_ids=DEVICES,
        physical=True,
    )
    assert verdict.bounded_arguments["speed"] == -0.5


def test_movement_without_a_duration_gets_one(supervisor: SafetySupervisor) -> None:
    """An unbounded movement must not be expressible."""

    arm(supervisor)
    verdict = supervisor.evaluate(
        make_command(
            session_id="session-1",
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            arguments={"speed": 0.1},
            armed=True,
        ),
        session_device_ids=DEVICES,
        physical=True,
    )
    assert verdict.bounded_arguments["durationSeconds"] == 2.0
    assert "durationSeconds" in verdict.clamped_fields


def test_a_boolean_is_not_treated_as_a_speed(supervisor: SafetySupervisor) -> None:
    arm(supervisor)
    verdict = supervisor.evaluate(
        make_command(
            session_id="session-1",
            device_id="fake-s1-main",
            policy_id="classroom-physical",
            arguments={"speed": True, "durationSeconds": 0.5},
            armed=True,
        ),
        session_device_ids=DEVICES,
        physical=True,
    )
    assert verdict.bounded_arguments["speed"] is True
    assert "speed" not in verdict.clamped_fields


def test_bounds_reject_nonsense_at_construction() -> None:
    with pytest.raises(ValueError, match="max_speed"):
        MotionBounds(max_speed=0)
    with pytest.raises(ValueError, match="min_input_confidence"):
        MotionBounds(min_input_confidence=1.5)


# ------------------------------------------------------------- FR-072 priority


def test_priority_order_matches_the_prd() -> None:
    assert [priority.value for priority in CommandPriority] == [1, 2, 3, 4, 5, 6, 7]


def test_instructor_stop_outranks_a_student_command() -> None:
    stop = make_command(session_id="s", device_id="d", action="stop_all", source="instructor")
    student = make_command(session_id="s", device_id="d", source="student_python")
    assert classify_priority(stop) < classify_priority(student)


def test_ai_proposal_is_the_lowest_priority() -> None:
    proposal = make_command(session_id="s", device_id="d", source="agent_mesh")
    assert classify_priority(proposal) is CommandPriority.AI_OR_WEARABLE_PROPOSAL


# ------------------------------------------------------------ FR-070 watchdogs


def test_watchdog_defaults_match_the_prd_table() -> None:
    assert DEFAULT_WATCHDOG_TIMEOUTS[WatchdogKind.S1_CONTINUOUS_MOTION] == 0.300
    assert DEFAULT_WATCHDOG_TIMEOUTS[WatchdogKind.LEGO_CONTINUOUS_MOTION] == 0.500
    assert DEFAULT_WATCHDOG_TIMEOUTS[WatchdogKind.QUEST_DEADMAN_HEARTBEAT] == 0.300
    assert DEFAULT_WATCHDOG_TIMEOUTS[WatchdogKind.LEAP_CONTINUOUS_INPUT] == 0.300
    assert DEFAULT_WATCHDOG_TIMEOUTS[WatchdogKind.ADAPTER_PROCESS_HEARTBEAT] == 1.000


@pytest.mark.parametrize(
    ("kind", "timeout", "action"),
    [
        (WatchdogKind.S1_CONTINUOUS_MOTION, 0.300, WatchdogAction.STOP),
        (WatchdogKind.LEGO_CONTINUOUS_MOTION, 0.500, WatchdogAction.STOP),
        (WatchdogKind.QUEST_DEADMAN_HEARTBEAT, 0.300, WatchdogAction.DISARM),
        (WatchdogKind.LEAP_CONTINUOUS_INPUT, 0.300, WatchdogAction.STOP),
        (WatchdogKind.ADAPTER_PROCESS_HEARTBEAT, 1.000, WatchdogAction.STOP),
    ],
)
def test_each_watchdog_fires_after_its_own_timeout(
    supervisor: SafetySupervisor,
    clock: ManualClock,
    kind: WatchdogKind,
    timeout: float,
    action: WatchdogAction,
) -> None:
    supervisor.heartbeat(device_id="fake-s1-main", kind=kind)

    clock.advance(timeout * 0.9)
    assert supervisor.expired_watchdogs() == ()

    clock.advance(timeout * 0.3)
    expiries = supervisor.expired_watchdogs()
    assert [expiry.kind for expiry in expiries] == [kind]
    assert expiries[0].action is action


def test_a_refreshed_heartbeat_keeps_the_watchdog_quiet(
    supervisor: SafetySupervisor, clock: ManualClock
) -> None:
    for _ in range(10):
        supervisor.heartbeat(device_id="fake-s1-main", kind=WatchdogKind.S1_CONTINUOUS_MOTION)
        clock.advance(0.2)
        assert supervisor.expired_watchdogs() == ()
