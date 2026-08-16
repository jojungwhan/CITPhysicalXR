"""Normalized recording and hardware-free replay.

FR-064 allows replay for debugging, student reflection, hardware-free lessons,
regression tests, and demos -- and forbids it from ever sending a physical
command unless it is explicitly converted into a newly armed live session.

That prohibition is structural here. ``Replayer`` holds no adapter, no registry,
and no pipeline: it can publish events to subscribers and nothing else. There is
no code path from a recording to a device, so "replay moved the robot" is not a
bug that can be written in this module.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from cit_protocol import DeviceEvent

from .events import EventRouter


@dataclass(frozen=True, slots=True)
class RecordedEvent:
    """One normalized event with its offset from the recording start."""

    offset_seconds: float
    event: DeviceEvent


@dataclass(frozen=True, slots=True)
class Recording:
    recording_id: str
    session_id: str
    started_at: datetime
    events: tuple[RecordedEvent, ...]

    @property
    def duration_seconds(self) -> float:
        return self.events[-1].offset_seconds if self.events else 0.0

    def to_json(self) -> str:
        return json.dumps(
            {
                "recordingId": self.recording_id,
                "sessionId": self.session_id,
                "startedAt": self.started_at.isoformat(),
                "physicalOutput": False,
                "events": [
                    {
                        "offsetSeconds": recorded.offset_seconds,
                        "event": json.loads(recorded.event.model_dump_json(exclude_none=True)),
                    }
                    for recorded in self.events
                ],
            },
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, raw: str) -> Recording:
        payload: Any = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("A recording must be a JSON object")
        events = tuple(
            RecordedEvent(
                offset_seconds=float(item["offsetSeconds"]),
                event=DeviceEvent.model_validate(item["event"]),
            )
            for item in payload["events"]
        )
        return cls(
            recording_id=str(payload["recordingId"]),
            session_id=str(payload["sessionId"]),
            started_at=datetime.fromisoformat(str(payload["startedAt"])),
            events=events,
        )


class Recorder:
    """Subscribes to the router and normalizes what it sees."""

    def __init__(self, *, recording_id: str, session_id: str, started_at: datetime) -> None:
        self._recording_id = recording_id
        self._session_id = session_id
        self._started_at = started_at
        self._events: list[RecordedEvent] = []

    def capture(self, event: DeviceEvent) -> None:
        offset = (event.receivedAt - self._started_at).total_seconds()
        self._events.append(RecordedEvent(offset_seconds=max(offset, 0.0), event=event))

    def attach(self, router: EventRouter, *, subscriber_id: str = "recorder") -> None:
        router.subscribe(subscriber_id, self.capture)

    def finish(self) -> Recording:
        return Recording(
            recording_id=self._recording_id,
            session_id=self._session_id,
            started_at=self._started_at,
            events=tuple(self._events),
        )


class Replayer:
    """Replays a recording to subscribers. Cannot reach a device by design."""

    def __init__(self, recording: Recording) -> None:
        self._recording = recording

    @property
    def recording(self) -> Recording:
        return self._recording

    def events(self) -> tuple[DeviceEvent, ...]:
        """Every event marked historical, so no consumer mistakes it for live."""

        return tuple(
            event.event.model_copy(update={"historical": True}) for event in self._recording.events
        )

    def replay_to(self, router: EventRouter) -> int:
        """Publish historical events. Returns total subscriber deliveries."""

        return router.publish_all(self.events())

    def slice(self, *, start: float, end: float) -> tuple[DeviceEvent, ...]:
        if start > end:
            raise ValueError("Replay slice start must not exceed its end")
        return tuple(
            recorded.event.model_copy(update={"historical": True})
            for recorded in self._recording.events
            if start <= recorded.offset_seconds <= end
        )


def merge_recordings(recordings: Sequence[Recording], *, recording_id: str) -> Recording:
    """Combine per-device recordings into one timeline for classroom review."""

    if not recordings:
        raise ValueError("Cannot merge an empty recording set")
    started_at = min(recording.started_at for recording in recordings)
    merged: list[RecordedEvent] = []
    for recording in recordings:
        shift = (recording.started_at - started_at).total_seconds()
        merged.extend(
            RecordedEvent(offset_seconds=item.offset_seconds + shift, event=item.event)
            for item in recording.events
        )
    merged.sort(key=lambda item: item.offset_seconds)
    return Recording(
        recording_id=recording_id,
        session_id=recordings[0].session_id,
        started_at=started_at,
        events=tuple(merged),
    )


def event_names(events: Iterable[DeviceEvent]) -> tuple[str, ...]:
    return tuple(event.name for event in events)
