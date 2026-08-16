from __future__ import annotations

from datetime import UTC, datetime

from cit_protocol import DeviceCommandIntent
from cit_safety import CommandDisposition, InMemoryCommandLedger

NOW = datetime(2026, 8, 16, 4, 0, 0, tzinfo=UTC)


def command() -> DeviceCommandIntent:
    return DeviceCommandIntent.model_validate(
        {
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
    )


def test_fresh_command_is_claimed_once_within_its_expiry_window() -> None:
    ledger = InMemoryCommandLedger()
    intent = command()

    first = ledger.claim(intent, now=NOW)
    second = ledger.claim(intent, now=NOW)

    assert (first, second) == (CommandDisposition.ACCEPTED, CommandDisposition.DUPLICATE)


def test_expired_command_is_never_claimed_for_execution() -> None:
    ledger = InMemoryCommandLedger()
    intent = command()
    expiry = datetime(2026, 8, 16, 4, 0, 0, 400_000, tzinfo=UTC)

    assert ledger.claim(intent, now=expiry) is CommandDisposition.EXPIRED
