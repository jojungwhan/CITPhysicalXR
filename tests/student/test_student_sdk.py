"""The student API (FR-013, FR-014, FR-015, FR-057) and its sandbox limits."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest
from citxr import (
    Bridge,
    CancelledError,
    CommandRejected,
    TransportError,
    active_bridge,
    device,
    every,
    log,
    parallel,
    program,
    run_interval,
    set_bridge,
    sleep,
    when,
)
from citxr.api import _reset_devices

pytestmark = pytest.mark.asyncio


class RecordingTransport:
    """An in-memory transport. The SDK never opens a connection itself."""

    def __init__(self, *, reject: Mapping[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []
        self._reject = reject

    async def call(self, method: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((method, dict(payload)))
        if self._reject is not None and method == "command":
            return self._reject
        if method == "read_sensor":
            return {"accepted": True, "values": {"distance": 42}}
        return {"accepted": True, "status": "completed"}

    def methods(self) -> list[str]:
        return [method for method, _ in self.calls]


@pytest.fixture(autouse=True)
def fresh_program() -> None:
    program().clear()
    _reset_devices()


@pytest.fixture
def transport() -> RecordingTransport:
    recording = RecordingTransport()
    set_bridge(Bridge(recording))
    return recording


# ------------------------------------------------------------- FR-013 sandbox


async def test_the_bridge_permits_only_the_named_calls(transport: RecordingTransport) -> None:
    with pytest.raises(TransportError, match="not a permitted runtime call"):
        await active_bridge().call("open_file", path="/etc/passwd")
    assert transport.calls == []


async def test_a_program_without_a_bridge_fails_closed() -> None:
    from citxr import bridge as bridge_module

    bridge_module._ACTIVE.clear()
    with pytest.raises(TransportError, match="No runtime bridge"):
        await device("fake-s1-main").stop()


# ---------------------------------------------------------- FR-014 shared API


async def test_a_device_call_becomes_one_command(transport: RecordingTransport) -> None:
    s1 = device("fake-s1-main")
    await s1.drive.velocity(speed=0.2, durationSeconds=1.0)

    assert transport.methods() == ["command"]
    _, payload = transport.calls[0]
    assert payload["device_id"] == "fake-s1-main"
    # The chain spells the capability a manifest advertises (FR-007), not a
    # capability plus an action. "drive" alone is not a capability.
    assert payload["capability"] == "drive.velocity"
    assert payload["action"] == "set"
    assert payload["arguments"] == {"speed": 0.2, "durationSeconds": 1.0}


async def test_the_generated_shape_and_a_handwritten_one_agree(
    transport: RecordingTransport,
) -> None:
    """AC-9. What the generator emits is what a student would write by hand."""

    s1 = device("fake-s1-main")
    await s1.drive.velocity(speed=0.2, durationSeconds=1)
    generated = list(transport.calls)

    transport.calls.clear()
    await device("fake-s1-main").send(
        capability="drive.velocity", action="set", speed=0.2, durationSeconds=1
    )
    assert transport.calls == generated


async def test_stop_is_always_available(transport: RecordingTransport) -> None:
    await device("fake-s1-main").stop()
    _, payload = transport.calls[0]
    assert payload["capability"] == "drive.stop"
    assert payload["action"] == "stop"


async def test_the_same_id_returns_the_same_handle(transport: RecordingTransport) -> None:
    assert device("fake-s1-main") is device("fake-s1-main")
    assert device("fake-s1-main") is not device("fake-lego-main")


async def test_sensor_reads_return_a_named_reading(transport: RecordingTransport) -> None:
    reading = await device("fake-lego-main").sensor("sensor.distance")
    assert reading.name == "sensor.distance"
    assert reading["distance"] == 42
    assert reading.value == 42


async def test_an_ambiguous_reading_asks_which_value(
    transport: RecordingTransport,
) -> None:
    from citxr import SensorReading

    reading = SensorReading(name="imu", values={"pitch": 1, "yaw": 2})
    with pytest.raises(KeyError, match="name the one you want"):
        _ = reading.value


async def test_log_reaches_the_runtime(transport: RecordingTransport) -> None:
    await log("hello")
    assert transport.methods() == ["log"]


# ------------------------------------------------------------ FR-057 parallel


async def test_parallel_starts_everything_together(transport: RecordingTransport) -> None:
    s1 = device("fake-s1-main")
    lego = device("fake-lego-main")

    await parallel(
        s1.drive.velocity(speed=0.2, durationSeconds=1),
        lego.motor.speed(speed=200),
        log("moving both"),
    )

    assert sorted(transport.methods()) == ["command", "command", "log"]


async def test_parallel_with_nothing_to_do_is_not_an_error(
    transport: RecordingTransport,
) -> None:
    assert await parallel() == ()


async def test_a_failing_action_cancels_its_siblings() -> None:
    """A half-executed parallel move is two robots going different ways."""

    started = asyncio.Event()
    cancelled = False

    async def slow() -> None:
        nonlocal cancelled
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled = True
            raise

    async def fails() -> None:
        await started.wait()
        raise RuntimeError("adapter said no")

    set_bridge(Bridge(RecordingTransport()))
    with pytest.raises(RuntimeError, match="adapter said no"):
        await parallel(slow(), fails())

    assert cancelled is True


# -------------------------------------------------------- FR-015 cancellation


async def test_a_cancelled_session_stops_at_the_next_checkpoint(
    transport: RecordingTransport,
) -> None:
    s1 = device("fake-s1-main")
    active_bridge().cancel()

    with pytest.raises(CancelledError):
        await s1.drive.velocity(speed=0.2, durationSeconds=1)
    assert transport.calls == []


async def test_sleep_checks_for_cancellation(transport: RecordingTransport) -> None:
    active_bridge().cancel()
    with pytest.raises(CancelledError):
        await sleep(0)


async def test_an_interval_loop_stops_when_the_session_does(
    transport: RecordingTransport,
) -> None:
    runs = 0

    @every(0.001)
    async def tick() -> None:
        nonlocal runs
        runs += 1
        if runs == 3:
            active_bridge().cancel()

    subscription = program().intervals[0]
    completed = await run_interval(subscription)

    assert completed == 3
    assert runs == 3


async def test_sleep_refuses_to_go_backwards(transport: RecordingTransport) -> None:
    with pytest.raises(ValueError):
        await sleep(-1)


# ------------------------------------------------------------ program capture


async def test_when_and_every_register_without_running(
    transport: RecordingTransport,
) -> None:
    @when("leap.gesture.open_palm")
    async def stop_everything() -> None:  # pragma: no cover - never invoked here
        await device("fake-s1-main").stop()

    @every(0.5)
    async def creep() -> None:  # pragma: no cover - never invoked here
        await device("fake-s1-main").drive.velocity(speed=0.1)

    assert [event.trigger for event in program().events] == ["leap.gesture.open_palm"]
    assert [interval.seconds for interval in program().intervals] == [0.5]
    assert transport.calls == []


# -------------------------------------------------------------- FR-012 errors


async def test_a_refusal_tells_the_student_what_to_do() -> None:
    set_bridge(
        Bridge(
            RecordingTransport(
                reject={
                    "accepted": False,
                    "code": "DEVICE_NOT_ARMED",
                    "message": "Device is not armed",
                    "recovery": "Ask your instructor to arm it.",
                }
            )
        )
    )

    with pytest.raises(CommandRejected) as rejected:
        await device("fake-s1-main").drive.velocity(speed=0.2)

    assert rejected.value.code == "DEVICE_NOT_ARMED"
    assert rejected.value.recovery == "Ask your instructor to arm it."
    assert "Ask your instructor" in str(rejected.value)
