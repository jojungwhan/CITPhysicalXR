"""Append-only audit trail and the redacted structured logger.

FR-083 requires every consequential action to be recorded and never rewritten.
FR-081 requires structured logs carrying required context. FR-082 requires data
minimisation, so both paths run values through the same allowlist: a field that
is not named here does not get written, and a field that looks like a secret is
replaced rather than truncated.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

# FR-082. Only these context keys are ever persisted or logged.
ALLOWED_CONTEXT_KEYS: frozenset[str] = frozenset(
    {
        "action",
        "actorId",
        "adapterId",
        "capability",
        "clampedFields",
        "code",
        "commandId",
        "count",
        "deviceId",
        "durationMs",
        "elapsedSeconds",
        "eventId",
        "executionMode",
        "failurePolicy",
        "kind",
        "policyId",
        "priority",
        "projectId",
        "reason",
        "recordingId",
        "result",
        "role",
        "sequence",
        "sessionId",
        "source",
        "state",
        "watchdog",
    }
)

# FR-082 negative cases: never persist biometrics, video, audio, or credentials.
_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "audio",
    "biometric",
    "credential",
    "frame",
    "passcode",
    "handmesh",
    "image",
    "password",
    "secret",
    "token",
    "video",
)

REDACTED = "[redacted]"


def redact(context: Mapping[str, Any]) -> dict[str, Any]:
    """Drop unknown keys and replace anything that names sensitive material."""

    clean: dict[str, Any] = {}
    for key, value in context.items():
        lowered = key.lower()
        if any(marker in lowered for marker in _FORBIDDEN_SUBSTRINGS):
            clean[key] = REDACTED
            continue
        if key not in ALLOWED_CONTEXT_KEYS:
            continue
        clean[key] = value
    return clean


class AuditAction(StrEnum):
    SESSION_CREATED = "session.created"
    SESSION_STATE_CHANGED = "session.state_changed"
    DEVICE_ASSIGNED = "device.assigned"
    DEVICE_RELEASED = "device.released"
    DEVICE_CONNECTED = "device.connected"
    DEVICE_DISCONNECTED = "device.disconnected"
    DEVICE_ARMED = "device.armed"
    DEVICE_DISARMED = "device.disarmed"
    COMMAND_ACCEPTED = "command.accepted"
    COMMAND_DENIED = "command.denied"
    COMMAND_CLAMPED = "command.clamped"
    EMERGENCY_STOP = "safety.emergency_stop"
    STOP_ALL = "safety.stop_all"
    WATCHDOG_FIRED = "safety.watchdog_fired"
    QUEUE_CLEARED = "safety.queue_cleared"
    LEASE_REVOKED = "safety.lease_revoked"
    INPUT_SOURCE_CHANGED = "safety.input_source_changed"
    FAILURE_POLICY_APPLIED = "safety.failure_policy_applied"
    REPLAY_STARTED = "replay.started"
    RECORDING_STARTED = "recording.started"
    RECORDING_STOPPED = "recording.stopped"
    RECORDING_DELETED = "recording.deleted"
    RECORDING_EXPORTED = "recording.exported"
    RETENTION_PRUNED = "retention.pruned"
    PRINCIPAL_JOINED = "auth.joined"
    AUTHORIZATION_DENIED = "auth.denied"
    PROJECT_SAVED = "project.saved"
    PROJECT_DELETED = "project.deleted"


@dataclass(frozen=True, slots=True)
class AuditEntry:
    sequence: int
    recorded_at: datetime
    action: AuditAction
    actor_id: str
    context: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "sequence": self.sequence,
                "recordedAt": self.recorded_at.isoformat(),
                "action": self.action.value,
                "actorId": self.actor_id,
                "context": dict(self.context),
            },
            sort_keys=True,
        )


class AuditLog:
    """Append-only. There is deliberately no update or delete method."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(
        self,
        action: AuditAction,
        *,
        actor_id: str,
        at: datetime,
        context: Mapping[str, Any] | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            sequence=len(self._entries) + 1,
            recorded_at=at,
            action=action,
            actor_id=actor_id,
            context=redact(context or {}),
        )
        self._entries.append(entry)
        return entry

    def entries(self, *, action: AuditAction | None = None) -> tuple[AuditEntry, ...]:
        if action is None:
            return tuple(self._entries)
        return tuple(entry for entry in self._entries if entry.action is action)

    def __len__(self) -> int:
        return len(self._entries)


class StructuredLogger:
    """FR-081. Emits one JSON object per line through the standard logger."""

    def __init__(self, name: str = "cit_runtime") -> None:
        self._logger = logging.getLogger(name)

    def log(
        self,
        level: int,
        message: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        payload = {"message": message, **redact(context or {})}
        self._logger.log(level, json.dumps(payload, sort_keys=True, default=str))

    def info(self, message: str, **context: Any) -> None:
        self.log(logging.INFO, message, context=context)

    def warning(self, message: str, **context: Any) -> None:
        self.log(logging.WARNING, message, context=context)

    def error(self, message: str, **context: Any) -> None:
        self.log(logging.ERROR, message, context=context)


def audit_entries_to_jsonl(entries: Iterable[AuditEntry]) -> str:
    return "\n".join(entry.to_json() for entry in entries)
