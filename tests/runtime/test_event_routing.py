"""FR-059, FR-060, FR-064, FR-081, FR-082, FR-083."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cit_protocol import DeviceEvent
from cit_runtime import (
    AuditAction,
    AuditLog,
    EventRouter,
    Recorder,
    Recording,
    Replayer,
    merge_recordings,
    redact,
)

AT = datetime(2026, 1, 1, tzinfo=UTC)


def make_event(
    *,
    device_id: str = "fake-s1-main",
    name: str = "telemetry.battery",
    category: str = "telemetry",
    event_id: str | None = None,
    sequence: int = 1,
    at: datetime = AT,
) -> DeviceEvent:
    return DeviceEvent.model_validate(
        {
            "eventId": event_id or str(uuid4()),
            "deviceId": device_id,
            "sequence": sequence,
            "category": category,
            "name": name,
            "values": {"percent": 88},
            "receivedAt": at,
        }
    )


# ------------------------------------------------------------------ FR-059 fan-out


def test_one_event_reaches_every_matching_subscriber() -> None:
    router = EventRouter()
    seen: dict[str, list[str]] = {"a": [], "b": [], "c": []}
    router.subscribe("a", lambda event: seen["a"].append(event.name))
    router.subscribe("b", lambda event: seen["b"].append(event.name))
    router.subscribe("c", lambda event: seen["c"].append(event.name), device_ids=["other"])

    delivered = router.publish(make_event())

    assert delivered == 2
    assert seen["a"] == seen["b"] == ["telemetry.battery"]
    assert seen["c"] == []


def test_category_filter_is_respected() -> None:
    router = EventRouter()
    safety: list[str] = []
    router.subscribe("safety", lambda event: safety.append(event.name), categories=["safety"])

    router.publish(make_event(category="telemetry"))
    router.publish(make_event(category="safety", name="safety.stopped"))

    assert safety == ["safety.stopped"]


# --------------------------------------------------------------- FR-059 dedupe


def test_the_same_event_is_never_delivered_twice() -> None:
    router = EventRouter()
    seen: list[str] = []
    router.subscribe("only", lambda event: seen.append(event.name))
    event = make_event(event_id="11111111-1111-4111-8111-111111111111")

    assert router.publish(event) == 1
    assert router.publish(event) == 0
    assert seen == ["telemetry.battery"]
    assert router.dropped_duplicates == 1


def test_dedupe_window_is_bounded() -> None:
    """The window is memory, not a permanent ledger: old ids fall out of it.

    That is the deliberate trade. Dedupe protects against an adapter retrying
    within a burst; it is not a lifetime replay guard. Expiry (FR-071) and the
    command ledger are what stop stale motion.
    """

    router = EventRouter(dedupe_window=2)
    seen: list[str] = []
    router.subscribe("only", lambda event: seen.append(str(event.eventId)))
    first = make_event(event_id="11111111-1111-4111-8111-111111111111")

    assert router.publish(first) == 1
    assert router.publish(first) == 0  # still inside the window

    router.publish(make_event())
    router.publish(make_event())  # evicts the first id

    assert router.publish(first) == 1
    assert seen.count("11111111-1111-4111-8111-111111111111") == 2


def test_sequences_are_per_device() -> None:
    router = EventRouter()
    assert router.next_sequence("a") == 1
    assert router.next_sequence("b") == 1
    assert router.next_sequence("a") == 2


def test_unsubscribe_stops_delivery() -> None:
    router = EventRouter()
    seen: list[str] = []
    router.subscribe("x", lambda event: seen.append(event.name))
    router.unsubscribe("x")
    assert router.publish(make_event()) == 0
    assert seen == []


# ------------------------------------------------------------ FR-064 replay


def test_replay_marks_every_event_historical() -> None:
    recorder = Recorder(recording_id="rec-1", session_id="session-1", started_at=AT)
    recorder.capture(make_event())
    recording = recorder.finish()

    replayed = Replayer(recording).events()

    assert len(replayed) == 1
    assert replayed[0].historical is True


def test_replayer_has_no_way_to_reach_a_device() -> None:
    """FR-064's prohibition, asserted structurally rather than by convention."""

    recorder = Recorder(recording_id="rec-1", session_id="session-1", started_at=AT)
    recorder.capture(make_event())
    replayer = Replayer(recorder.finish())

    surface = {name for name in dir(replayer) if not name.startswith("_")}
    assert surface == {"events", "recording", "replay_to", "slice"}
    forbidden = {"registry", "adapter", "pipeline", "runtime", "submit", "execute"}
    assert not surface & forbidden


def test_replay_round_trips_through_json() -> None:
    recorder = Recorder(recording_id="rec-1", session_id="session-1", started_at=AT)
    recorder.capture(make_event(name="motion.started", category="motion"))
    recording = recorder.finish()

    restored = Recording.from_json(recording.to_json())

    assert restored.recording_id == "rec-1"
    assert [item.event.name for item in restored.events] == ["motion.started"]


def test_recorder_attaches_to_a_router_and_captures_live_events() -> None:
    router = EventRouter()
    recorder = Recorder(recording_id="rec-1", session_id="session-1", started_at=AT)
    recorder.attach(router)

    router.publish(make_event(name="sensor.distance", category="sensor"))

    assert [item.event.name for item in recorder.finish().events] == ["sensor.distance"]


def test_slice_returns_only_the_requested_window() -> None:
    recorder = Recorder(recording_id="rec-1", session_id="session-1", started_at=AT)
    recorder.capture(make_event(name="a.one", at=AT))
    recorder.capture(
        make_event(name="a.two", at=AT.replace(second=5)),
    )
    replayer = Replayer(recorder.finish())

    assert [event.name for event in replayer.slice(start=0, end=1)] == ["a.one"]
    with pytest.raises(ValueError, match="start"):
        replayer.slice(start=5, end=1)


def test_merging_recordings_orders_one_timeline() -> None:
    first = Recorder(recording_id="r1", session_id="s", started_at=AT)
    first.capture(make_event(name="a.one", at=AT.replace(second=2)))
    second = Recorder(recording_id="r2", session_id="s", started_at=AT.replace(second=1))
    second.capture(make_event(name="b.one", at=AT.replace(second=1)))

    merged = merge_recordings([first.finish(), second.finish()], recording_id="merged")

    assert [item.event.name for item in merged.events] == ["b.one", "a.one"]


# ------------------------------------------------- FR-081 / FR-082 redaction


def test_redaction_drops_unknown_keys() -> None:
    assert redact({"deviceId": "d", "whateverElse": "x"}) == {"deviceId": "d"}


@pytest.mark.parametrize(
    "key",
    [
        "videoFrame",
        "audioClip",
        "handMesh",
        "biometricHash",
        "apiToken",
        "userPassword",
        "pairingSecret",
        "credentialBlob",
    ],
)
def test_sensitive_material_is_replaced_not_stored(key: str) -> None:
    assert redact({key: "sensitive"})[key] == "[redacted]"


def test_audit_is_append_only_and_redacted() -> None:
    log = AuditLog()
    log.record(
        AuditAction.DEVICE_ARMED,
        actor_id="instructor-1",
        at=AT,
        context={"deviceId": "fake-s1-main", "videoFrame": "raw", "unknown": "x"},
    )

    entry = log.entries()[0]
    assert entry.sequence == 1
    assert entry.context == {"deviceId": "fake-s1-main", "videoFrame": "[redacted]"}
    assert not hasattr(log, "delete")
    assert not hasattr(log, "update")
