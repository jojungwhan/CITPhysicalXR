"""Projects on disk, recordings, retention, and the replay prohibition.

FR-001, FR-002, FR-064, FR-084, NFR 12.4, NFR 12.6.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from cit_protocol import DeviceEvent
from cit_runtime import ManualClock, Runtime
from cit_runtime.projects import ProjectStore, ProjectStoreError
from cit_runtime.recorder import RecordedEvent, Recording, Replayer
from cit_runtime.retention import RecordingStore, RetentionPolicy, replay_package

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def a_project(name: str = "My program") -> dict[str, Any]:
    """The smallest document the Studio's own schema accepts."""

    return {
        "schemaVersion": 1,
        "projectId": str(uuid4()),
        "name": name,
        "authoringMode": "blocks",
        "blocksState": {"blocks": []},
        "generatedPython": "",
        "pythonSource": "",
        "targetProfile": "simulation",
        "deviceBindings": [],
        "questScene": {},
        "safetyPreset": "simulation-only",
        "assets": [],
        "createdAt": NOW.isoformat(),
        "updatedAt": NOW.isoformat(),
    }


def an_event(device_id: str = "fake-s1-main", *, at: datetime = NOW) -> DeviceEvent:
    return DeviceEvent.model_validate(
        {
            "eventId": str(uuid4()),
            "deviceId": device_id,
            "category": "telemetry",
            "name": "telemetry.battery",
            "values": {"percent": 80},
            "receivedAt": at,
        }
    )


# --------------------------------------------------------------- project store


def test_a_saved_project_can_be_read_back(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    document = a_project()

    store.save(document, owner_id="student-1", at=NOW)

    assert store.get(document["projectId"])["name"] == "My program"
    assert store.owner_of(document["projectId"]) == "student-1"


def test_ownership_is_claimed_once_and_does_not_transfer(tmp_path: Path) -> None:
    """Opening someone else's project and saving it does not take it."""

    store = ProjectStore(tmp_path)
    document = a_project()
    store.save(document, owner_id="student-1", at=NOW)

    store.save(document, owner_id="student-2", at=NOW + timedelta(minutes=1))

    assert store.owner_of(document["projectId"]) == "student-1"


def test_the_previous_version_is_kept_beside_the_project(tmp_path: Path) -> None:
    """NFR 12.4. A bug above this layer must not be the end of the work."""

    store = ProjectStore(tmp_path)
    document = a_project("first")
    store.save(document, owner_id="student-1", at=NOW)
    store.save({**document, "name": "second"}, owner_id="student-1", at=NOW)

    backup = tmp_path / f"{document['projectId']}.bak.json"
    assert json.loads(backup.read_text(encoding="utf-8"))["name"] == "first"
    assert store.get(document["projectId"])["name"] == "second"


def test_a_write_leaves_no_partial_file_behind(tmp_path: Path) -> None:
    """The temporary file is in the same directory and is renamed, not copied."""

    store = ProjectStore(tmp_path)
    store.save(a_project(), owner_id="student-1", at=NOW)

    assert not list(tmp_path.glob("*.tmp"))


def test_an_invalid_project_is_refused_with_a_reason(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    broken = a_project()
    del broken["blocksState"]

    with pytest.raises(ProjectStoreError) as error:
        store.save(broken, owner_id="student-1", at=NOW)

    assert "blocksState" in str(error.value)
    assert error.value.recovery


def test_a_corrupt_file_is_reported_and_does_not_break_the_list(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    good = a_project("good one")
    store.save(good, owner_id="student-1", at=NOW)
    (tmp_path / f"{uuid4()}.json").write_text("{ not json", encoding="utf-8")

    listed = store.list()

    assert [item.name for item in listed] == ["good one"]


def test_a_project_id_that_is_not_a_uuid_never_becomes_a_path(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)

    with pytest.raises(ProjectStoreError):
        store.get("../../etc/passwd")


def test_listing_can_be_scoped_to_one_owner(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    store.save(a_project("mine"), owner_id="student-1", at=NOW)
    store.save(a_project("theirs"), owner_id="student-2", at=NOW)

    assert [item.name for item in store.list(owner_id="student-1")] == ["mine"]


# ------------------------------------------------------------------ retention


def a_recording(recording_id: str, *, started_at: datetime) -> Recording:
    return Recording(
        recording_id=recording_id,
        session_id="session-1",
        started_at=started_at,
        events=(RecordedEvent(offset_seconds=0.0, event=an_event(at=started_at)),),
    )


def test_a_recording_survives_the_tab_that_made_it(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path)
    store.save(a_recording("rec-1", started_at=NOW), now=NOW)

    assert RecordingStore(tmp_path).get("rec-1").session_id == "session-1"


def test_retention_drops_recordings_past_the_age_limit(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path, policy=RetentionPolicy(retention_days=7))
    store.save(a_recording("old", started_at=NOW - timedelta(days=30)), now=NOW)
    store.save(a_recording("new", started_at=NOW), now=NOW)

    assert {item.recording_id for item in store.list()} == {"new"}


def test_retention_drops_the_oldest_past_the_count_limit(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path, policy=RetentionPolicy(max_recordings=2))
    for index in range(4):
        store.save(
            a_recording(f"rec-{index}", started_at=NOW + timedelta(minutes=index)),
            now=NOW + timedelta(hours=1),
        )

    assert {item.recording_id for item in store.list()} == {"rec-3", "rec-2"}


def test_a_recording_can_be_deleted(tmp_path: Path) -> None:
    """NFR 12.6. Deletion is something a person can actually do."""

    store = RecordingStore(tmp_path)
    store.save(a_recording("rec-1", started_at=NOW), now=NOW)

    assert store.delete("rec-1") is True
    assert store.list() == ()


def test_the_replay_package_states_that_it_moves_nothing(tmp_path: Path) -> None:
    recording = a_recording("rec-1", started_at=NOW)

    package = json.loads(replay_package(recording, audit_entries=(), exported_at=NOW))

    assert package["physicalOutput"] is False
    assert package["recording"]["recordingId"] == "rec-1"


# ------------------------------------------------------- replay in the runtime


@pytest.mark.asyncio
async def test_replay_publishes_history_and_reaches_no_adapter(
    clock: ManualClock, tmp_path: Path
) -> None:
    """FR-064. There is no code path from a recording to a device."""

    runtime = Runtime(clock=clock, data_dir=tmp_path)
    await runtime.start()
    session = runtime.create_session(project_id="p", user_id="student-1")
    recording_id = runtime.start_recording(session.session_id)

    adapter = runtime.registry.adapter("fake-s1-main")
    await adapter.emit_telemetry("telemetry.battery", {"percent": 55}, at=clock.now())
    runtime.router.publish_all(adapter.drain_events())
    runtime.stop_recording(recording_id)

    seen: list[DeviceEvent] = []
    runtime.router.subscribe("test-watcher", seen.append)
    runtime.replay(recording_id, actor_id="teacher-1")

    assert [event.historical for event in seen] == [True]
    # Replay talks to subscribers. The adapter did nothing and said nothing.
    assert adapter.drain_events() == ()
    # Structural, not incidental: a replayer holds nothing it could dispatch to.
    replayer = Replayer(runtime.recording(recording_id))
    assert not any(
        hasattr(replayer, name) for name in ("registry", "pipeline", "adapter", "runtime")
    )


@pytest.mark.asyncio
async def test_a_replayed_event_does_not_repaint_the_instructor_console(
    clock: ManualClock, tmp_path: Path
) -> None:
    """A recording of a full battery must not make a flat hub look healthy."""

    runtime = Runtime(clock=clock, data_dir=tmp_path)
    await runtime.start()
    adapter = runtime.registry.adapter("fake-s1-main")

    await adapter.emit_telemetry("telemetry.battery", {"percent": 90}, at=clock.now())
    runtime.router.publish_all(adapter.drain_events())
    recording = Recording(
        recording_id="rec-1",
        session_id="session-1",
        started_at=clock.now(),
        events=(RecordedEvent(offset_seconds=0.0, event=an_event(at=clock.now())),),
    )
    runtime.router.publish_all(
        event.model_copy(update={"historical": True}) for event in (recording.events[0].event,)
    )

    assert runtime.status.get("fake-s1-main").battery_percent == 90
