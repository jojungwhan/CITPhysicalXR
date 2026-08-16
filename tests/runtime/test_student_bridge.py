"""The runtime end of the student bridge: what a student program can reach."""

from __future__ import annotations

import pytest
from cit_runtime import ExecutionMode, Runtime
from cit_runtime.student_bridge import StudentBridge, StudentBridgeError

pytestmark = pytest.mark.asyncio


async def prepared(
    runtime: Runtime,
    *,
    execution_mode: ExecutionMode = ExecutionMode.SIMULATION,
) -> StudentBridge:
    await runtime.start()
    session = runtime.create_session(
        project_id="lesson-1",
        user_id="student-1",
        instructor_id="instructor-1",
        execution_mode=execution_mode,
        safety_policy_id="classroom-physical",
    )
    runtime.bind_devices(session.session_id, ["fake-s1-main", "fake-lego-main"])
    runtime.advance_to_ready(session.session_id)
    return StudentBridge(
        runtime,
        session_id=session.session_id,
        aliases={"s1": "fake-s1-main", "lego": "fake-lego-main"},
    )


# ------------------------------------------------------------------- the gate


async def test_only_the_five_methods_are_served(runtime: Runtime) -> None:
    bridge = await prepared(runtime)
    with pytest.raises(StudentBridgeError, match="not a permitted runtime call"):
        await bridge.call("open_file", {"path": "/etc/passwd"})


async def test_a_student_program_cannot_claim_to_be_an_instructor(
    runtime: Runtime,
) -> None:
    """FR-068. Only a person can issue an instructor command."""

    await runtime.start()
    session = runtime.create_session(project_id="p", user_id="u")
    with pytest.raises(StudentBridgeError, match="may only act as"):
        StudentBridge(runtime, session_id=session.session_id, source="instructor")


async def test_an_alias_resolves_to_exactly_one_device(runtime: Runtime) -> None:
    bridge = await prepared(runtime)
    assert bridge.resolve("s1") == "fake-s1-main"
    assert bridge.resolve("fake-lego-main") == "fake-lego-main"


async def test_an_unknown_name_names_what_is_bound(runtime: Runtime) -> None:
    """FR-019. No prefix match, no nearest device, no guessing."""

    bridge = await prepared(runtime)
    with pytest.raises(StudentBridgeError, match="no device called 'fake-s1'"):
        bridge.resolve("fake-s1")


# ---------------------------------------------------------------- commands


async def test_a_student_command_reaches_the_adapter(runtime: Runtime) -> None:
    bridge = await prepared(runtime)
    result = await bridge.call(
        "command",
        {
            "device_id": "s1",
            "capability": "drive.velocity",
            "action": "set",
            "arguments": {"speed": 0.2, "durationSeconds": 1.0},
        },
    )
    assert result["accepted"] is True
    assert result["status"] == "completed"


async def test_a_refusal_comes_back_as_data_with_a_recovery(runtime: Runtime) -> None:
    """FR-012. The student gets a reason and a next step, not a stack trace."""

    bridge = await prepared(runtime, execution_mode=ExecutionMode.PHYSICAL)
    result = await bridge.call(
        "command",
        {
            "device_id": "s1",
            "capability": "drive.velocity",
            "action": "set",
            "arguments": {"speed": 0.2},
        },
    )
    assert result["accepted"] is False
    assert result["code"] == "DEVICE_NOT_ARMED"
    assert "arm" in result["recovery"].lower()


async def test_a_student_command_is_still_clamped(runtime: Runtime) -> None:
    bridge = await prepared(runtime)
    result = await bridge.call(
        "command",
        {
            "device_id": "s1",
            "capability": "drive.velocity",
            "action": "set",
            "arguments": {"speed": 99.0},
        },
    )
    assert result["accepted"] is True
    assert "speed" in result["clampedFields"]


async def test_the_bridge_cannot_raise_its_own_speed_ceiling(runtime: Runtime) -> None:
    """FR-068. Nothing a student sends changes the policy that bounds them."""

    bridge = await prepared(runtime)
    await bridge.call(
        "command",
        {
            "device_id": "s1",
            "capability": "drive.velocity",
            "action": "set",
            "arguments": {"speed": 99.0, "max_speed": 99.0, "policyId": "wide-open"},
        },
    )
    policy = runtime.supervisor.policy("classroom-physical")
    assert policy.bounds.max_speed == 0.5


async def test_a_student_program_cannot_arm_a_device(runtime: Runtime) -> None:
    bridge = await prepared(runtime, execution_mode=ExecutionMode.PHYSICAL)
    assert not runtime.supervisor.is_armed("fake-s1-main")

    await bridge.call(
        "command",
        {
            "device_id": "s1",
            "capability": "safety.arm",
            "action": "arm",
            "arguments": {},
        },
    )

    assert not runtime.supervisor.is_armed("fake-s1-main")


# ------------------------------------------------------------------- reads


async def test_reading_a_sensor_returns_the_latest_event(runtime: Runtime) -> None:
    bridge = await prepared(runtime)
    adapter = runtime.registry.adapter("fake-lego-main")
    await adapter.emit_sensor(  # type: ignore[attr-defined]
        "sensor.distance", {"distance": 120}, at=runtime.clock.now()
    )
    runtime.router.publish_all(adapter.drain_events())

    result = await bridge.call("read_sensor", {"device_id": "lego", "sensor": "sensor.distance"})
    assert result["values"] == {"distance": 120}


async def test_reading_a_sensor_with_no_reading_yet_says_so(runtime: Runtime) -> None:
    bridge = await prepared(runtime)
    result = await bridge.call("read_sensor", {"device_id": "lego", "sensor": "sensor.color"})
    assert result["values"] == {}
    assert "No reading" in result["message"]


async def test_device_info_reports_state_without_leaking_internals(
    runtime: Runtime,
) -> None:
    bridge = await prepared(runtime)
    info = await bridge.call("device_info", {"device_id": "s1"})

    assert info["deviceId"] == "fake-s1-main"
    assert "drive.velocity" in info["capabilities"]
    for leaked in ("adapter", "transport", "token", "credential", "secret"):
        assert leaked not in {key.lower() for key in info}


async def test_log_does_not_reach_a_device(runtime: Runtime) -> None:
    bridge = await prepared(runtime)
    assert (await bridge.call("log", {"message": "hello"}))["accepted"] is True


async def test_the_sdk_capability_shape_is_accepted_by_the_protocol(
    runtime: Runtime,
) -> None:
    """Regression: the SDK once sent 'drive' as the capability, and the schema
    rejected it with a 500 rather than a student-readable refusal."""

    bridge = await prepared(runtime)
    result = await bridge.call(
        "command",
        {
            "device_id": "s1",
            # Exactly what `s1.drive.velocity(...)` produces.
            "capability": "drive.velocity",
            "action": "set",
            "arguments": {"speed": 0.2, "durationSeconds": 1},
        },
    )
    assert result["accepted"] is True


async def test_a_malformed_capability_is_a_refusal_not_a_crash(
    runtime: Runtime,
) -> None:
    bridge = await prepared(runtime)
    with pytest.raises(StudentBridgeError, match="capability"):
        await bridge.call(
            "command",
            {
                "device_id": "s1",
                "capability": "drive",
                "action": "set",
                "arguments": {},
            },
        )
