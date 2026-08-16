"""Shared fixtures for the Milestone 1 runtime and fault suites."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from cit_device_simulator import (
    FakeDeviceAdapter,
    create_fake_leap_adapter,
    create_fake_lego_adapter,
    create_fake_quest_adapter,
    create_fake_s1_adapter,
)
from cit_protocol import DeviceCommandIntent
from cit_runtime import ManualClock, Runtime, SafetyPolicy
from cit_runtime.supervisor import MotionBounds, WatchdogKind


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock(start=datetime(2026, 1, 1, tzinfo=UTC))


@pytest.fixture
def physical_policy() -> SafetyPolicy:
    return SafetyPolicy(
        policy_id="classroom-physical",
        bounds=MotionBounds(max_speed=0.5, max_duration_seconds=2.0, min_input_confidence=0.6),
        arm_ttl=timedelta(minutes=5),
        require_deadman=True,
    )


@pytest.fixture
def physical_stand_in_fleet() -> tuple[FakeDeviceAdapter, ...]:
    """The default fakes, but declaring themselves physical.

    No hardware is contacted. The flag exists so the arm, dead-man, bound, and
    watchdog gates -- which only apply to physical devices -- can be exercised
    at all before M2/M4/M5 bring real adapters.
    """

    fleet = (
        create_fake_s1_adapter(),
        create_fake_lego_adapter(),
        create_fake_leap_adapter(),
        create_fake_quest_adapter(),
    )
    for adapter in fleet:
        adapter.physical = True
    return fleet


@pytest.fixture
def runtime(
    clock: ManualClock,
    physical_policy: SafetyPolicy,
    physical_stand_in_fleet: tuple[FakeDeviceAdapter, ...],
) -> Runtime:
    return Runtime(
        clock=clock,
        adapters=physical_stand_in_fleet,
        policies=(physical_policy,),
        physical_enabled=True,
    )


def hold_deadman(runtime: Runtime, device_id: str) -> None:
    """ADR-028. Stand in for a student holding the dead-man control.

    Arming deliberately does not do this. An instructor saying a robot may move
    is not the same event as somebody holding the control that lets it, and
    collapsing the two would put the bypass back.
    """

    runtime.heartbeat(device_id=device_id, kind=WatchdogKind.QUEST_DEADMAN_HEARTBEAT)


def make_command(
    *,
    session_id: str,
    device_id: str,
    capability: str = "drive.velocity",
    action: str = "set",
    arguments: dict[str, Any] | None = None,
    source: str = "student_blocks",
    policy_id: str = "simulation-only",
    armed: bool = False,
    deadman_active: bool = True,
    input_confidence: float | None = None,
    now: datetime | None = None,
    ttl_seconds: float = 5.0,
    idempotency_key: str | None = None,
) -> DeviceCommandIntent:
    """Build a valid intent. Tests vary exactly one field at a time."""

    issued = now or datetime(2026, 1, 1, tzinfo=UTC)
    safety: dict[str, Any] = {
        "policyId": policy_id,
        "armed": armed,
        "deadmanActive": deadman_active,
    }
    if input_confidence is not None:
        safety["inputConfidence"] = input_confidence
    return DeviceCommandIntent.model_validate(
        {
            "commandId": str(uuid4()),
            "sessionId": session_id,
            "deviceId": device_id,
            "capability": capability,
            "action": action,
            "arguments": arguments if arguments is not None else {"speed": 0.2},
            "source": source,
            "issuedAt": issued,
            "expiresAt": issued + timedelta(seconds=ttl_seconds),
            "idempotencyKey": idempotency_key or str(uuid4()),
            "safetyContext": safety,
        }
    )
