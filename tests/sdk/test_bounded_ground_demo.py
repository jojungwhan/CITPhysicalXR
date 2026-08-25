from __future__ import annotations

import asyncio

import pytest
from cit_integration_sdk.bounded_demo import BoundedGroundDemonstration


@pytest.mark.asyncio
async def test_bounded_demo_runs_forward_stop_backward_stop() -> None:
    calls: list[tuple[str, object]] = []
    completed = asyncio.Event()

    async def drive(direction: str, pulse: int) -> None:
        calls.append((direction, pulse))

    async def stop(reason: str) -> None:
        calls.append(("stop", reason))
        if reason == "demonstration_complete":
            completed.set()

    demo = BoundedGroundDemonstration(
        drive=drive,
        stop=stop,
        meters_per_second=10,
        keepalive_seconds=0.001,
        pause_seconds=0,
    )
    await demo.start(distance_meters=0.05)
    await asyncio.wait_for(completed.wait(), timeout=1)

    directions = [name for name, _ in calls]
    assert directions[0] == "forward"
    assert "forward" in directions
    assert "backward" in directions
    assert directions[-1] == "stop"


@pytest.mark.asyncio
async def test_bounded_demo_is_preempted_by_stop() -> None:
    stopped = asyncio.Event()

    async def drive(_direction: str, _pulse: int) -> None:
        await asyncio.sleep(0)

    async def stop(reason: str) -> None:
        if reason == "instructor_stop":
            stopped.set()

    demo = BoundedGroundDemonstration(drive=drive, stop=stop)
    await demo.start(distance_meters=0.1)
    await demo.cancel(reason="instructor_stop")

    assert not demo.active
    assert stopped.is_set()
