from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cit_protocol import DeviceCommandIntent
from cit_safety import FoundationSafetyGate

NOW = datetime(2026, 8, 16, 4, 0, 0, tzinfo=UTC)


def command(**overrides: Any) -> DeviceCommandIntent:
    values: dict[str, Any] = {
        "commandId": "45e8743a-8c95-40ed-91f0-9285929355f4",
        "sessionId": "session-a",
        "deviceId": "fake-s1-main",
        "capability": "drive.velocity",
        "action": "set",
        "arguments": {"forward": 0.2},
        "source": "student_blocks",
        "issuedAt": "2026-08-16T04:00:00.000Z",
        "expiresAt": "2026-08-16T04:00:00.400Z",
        "idempotencyKey": "session-a:move-1",
        "safetyContext": {"policyId": "student-low-speed", "armed": False},
    }
    values.update(overrides)
    return DeviceCommandIntent.model_validate(values)


def test_unarmed_movement_is_denied() -> None:
    decision = FoundationSafetyGate().evaluate(command(), now=NOW)

    assert decision.allowed is False
    assert decision.code == "DEVICE_NOT_ARMED"


def test_agent_mesh_cannot_initiate_movement_even_when_marked_armed() -> None:
    decision = FoundationSafetyGate().evaluate(
        command(
            source="agent_mesh",
            safetyContext={"policyId": "agent-proposal", "armed": True},
        ),
        now=NOW,
    )

    assert decision.allowed is False
    assert decision.code == "SAFETY_POLICY_DENIED"


def test_stop_command_remains_available_without_arming() -> None:
    decision = FoundationSafetyGate().evaluate(
        command(
            capability="drive.stop",
            action="execute",
            source="agent_mesh",
            arguments={},
            safetyContext={"policyId": "wearable-stop", "armed": False},
        ),
        now=NOW,
    )

    assert decision.allowed is True
    assert decision.code is None
