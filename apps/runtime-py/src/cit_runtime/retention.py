"""Recordings on disk, and the rules for how long they stay there.

FR-084 asks for configurable local retention, redacted exports, and a replay
package. FR-064 says a recording exists for debugging, reflection, hardware-free
lessons, regression tests, and demos -- all of which need it to outlive the tab
that made it. NFR 12.6 says a person can delete and export their own data.

Retention is enforced on write rather than on a timer. A timer that only runs
while the runtime is up would quietly keep a term's worth of a classroom's
recordings on a machine that gets switched off at four o'clock every day.

A recording holds normalized device events, which the protocol schema already
prevents from carrying video, audio, or biometric frames. The export applies the
audit redaction allowlist to the accompanying audit slice as well, so a package
handed to a student's parents is redacted by the same rule as the log.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .audit import AuditEntry
from .recorder import Recording

DEFAULT_MAX_RECORDINGS = 50
DEFAULT_RETENTION_DAYS = 30


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """How much classroom history this machine keeps (FR-084)."""

    max_recordings: int = DEFAULT_MAX_RECORDINGS
    retention_days: int = DEFAULT_RETENTION_DAYS

    def __post_init__(self) -> None:
        if self.max_recordings <= 0:
            raise ValueError("max_recordings must be positive")
        if self.retention_days <= 0:
            raise ValueError("retention_days must be positive")

    @property
    def max_age(self) -> timedelta:
        return timedelta(days=self.retention_days)


@dataclass(frozen=True, slots=True)
class StoredRecording:
    recording_id: str
    session_id: str
    started_at: datetime
    event_count: int
    duration_seconds: float


class RecordingStore:
    """A directory of recordings, pruned to the retention policy on every write."""

    def __init__(self, root: Path, *, policy: RetentionPolicy | None = None) -> None:
        self._root = root
        self._policy = policy or RetentionPolicy()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def policy(self) -> RetentionPolicy:
        return self._policy

    def set_policy(self, policy: RetentionPolicy) -> None:
        self._policy = policy

    def _path(self, recording_id: str) -> Path:
        if "/" in recording_id or "\\" in recording_id or recording_id.startswith("."):
            raise ValueError(f"{recording_id!r} is not a recording id")
        return self._root / f"{recording_id}.json"

    def save(self, recording: Recording, *, now: datetime) -> StoredRecording:
        self._root.mkdir(parents=True, exist_ok=True)
        self._path(recording.recording_id).write_text(recording.to_json(), encoding="utf-8")
        self.prune(now=now)
        return _summarize(recording)

    def get(self, recording_id: str) -> Recording:
        path = self._path(recording_id)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise KeyError(f"Unknown recording {recording_id!r}") from error
        return Recording.from_json(raw)

    def list(self) -> tuple[StoredRecording, ...]:
        stored: list[StoredRecording] = []
        if not self._root.is_dir():
            return ()
        for path in sorted(self._root.glob("*.json")):
            try:
                stored.append(_summarize(Recording.from_json(path.read_text(encoding="utf-8"))))
            except (ValueError, KeyError):
                continue
        stored.sort(key=lambda item: item.started_at, reverse=True)
        return tuple(stored)

    def delete(self, recording_id: str) -> bool:
        path = self._path(recording_id)
        existed = path.exists()
        path.unlink(missing_ok=True)
        return existed

    def prune(self, *, now: datetime) -> tuple[str, ...]:
        """Drop anything past the age limit, then anything past the count limit."""

        stored = self.list()
        cutoff = now - self._policy.max_age
        removed: list[str] = []
        survivors: list[StoredRecording] = []
        for item in stored:
            if item.started_at < cutoff:
                self.delete(item.recording_id)
                removed.append(item.recording_id)
            else:
                survivors.append(item)
        for item in survivors[self._policy.max_recordings :]:
            self.delete(item.recording_id)
            removed.append(item.recording_id)
        return tuple(removed)


def _summarize(recording: Recording) -> StoredRecording:
    return StoredRecording(
        recording_id=recording.recording_id,
        session_id=recording.session_id,
        started_at=recording.started_at,
        event_count=len(recording.events),
        duration_seconds=recording.duration_seconds,
    )


def replay_package(
    recording: Recording,
    *,
    audit_entries: Iterable[AuditEntry],
    exported_at: datetime,
) -> str:
    """FR-084. One JSON document: the recording plus its redacted audit slice.

    ``physicalOutput`` is stated rather than implied. Anything that reads this
    package is being told, in the document itself, that replaying it does not
    move a robot (FR-064).
    """

    session_id = recording.session_id
    # Entries with no session of their own -- stop-all, a watchdog firing -- are
    # kept: they are the context in which this session's events happened.
    relevant = [
        entry for entry in audit_entries if entry.context.get("sessionId") in (None, session_id)
    ]
    return json.dumps(
        {
            "packageVersion": 1,
            "exportedAt": exported_at.isoformat(),
            "physicalOutput": False,
            "recording": json.loads(recording.to_json()),
            "audit": [json.loads(entry.to_json()) for entry in relevant],
        },
        indent=2,
        sort_keys=True,
    )
