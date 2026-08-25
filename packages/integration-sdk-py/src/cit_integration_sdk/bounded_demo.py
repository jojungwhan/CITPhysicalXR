"""Reusable, preemptible timing for a bounded ground-robot demonstration."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

DemoDrive = Callable[[str, int], Awaitable[None]]
DemoStop = Callable[[str], Awaitable[None]]
DemoError = Callable[[Exception], None]


class BoundedGroundDemonstration:
    """Schedule one forward/stop/backward/stop sequence without blocking stop input.

    Adapters retain ownership of vendor translation. Repeating the bounded velocity
    pulse also refreshes their independent deadman watchdogs; a stalled task stops
    receiving refreshes and therefore fails safe.
    """

    def __init__(
        self,
        *,
        drive: DemoDrive,
        stop: DemoStop,
        on_error: DemoError | None = None,
        meters_per_second: float = 0.12,
        keepalive_seconds: float = 0.15,
        pause_seconds: float = 0.15,
    ) -> None:
        if not 0.01 <= meters_per_second <= 10:
            raise ValueError("Demonstration speed is invalid")
        if not 0.001 <= keepalive_seconds <= 0.25:
            raise ValueError("Demonstration keepalive is invalid")
        if not 0 <= pause_seconds <= 0.5:
            raise ValueError("Demonstration pause is invalid")
        self._drive = drive
        self._stop = stop
        self._on_error = on_error
        self._meters_per_second = meters_per_second
        self._keepalive_seconds = keepalive_seconds
        self._pause_seconds = pause_seconds
        self._task: asyncio.Task[None] | None = None
        self.last_error: str | None = None

    @property
    def active(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self, *, distance_meters: float) -> None:
        if isinstance(distance_meters, bool) or not isinstance(distance_meters, (int, float)):
            raise ValueError("Demonstration distance must be numeric")
        distance = float(distance_meters)
        if not 0.05 <= distance <= 0.1:
            raise ValueError("Demonstration distance must be from 0.05 through 0.1 metres")
        await self.cancel(reason="demonstration_restarted")
        self.last_error = None
        self._task = asyncio.create_task(
            self._run(distance),
            name="cit-bounded-ground-demonstration",
        )

    async def cancel(self, *, reason: str, force_stop: bool = False) -> None:
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if task is not None or force_stop:
            await self._stop(reason)

    async def _run(self, distance_meters: float) -> None:
        current = asyncio.current_task()
        duration = distance_meters / self._meters_per_second
        try:
            await self._pulse("forward", duration)
            await self._stop("demonstration_forward_complete")
            if self._pause_seconds > 0:
                await asyncio.sleep(self._pause_seconds)
            await self._pulse("backward", duration)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # task errors are converted into adapter health
            self.last_error = str(error)[:500]
            if self._on_error is not None:
                self._on_error(error)
        finally:
            try:
                await self._stop("demonstration_complete")
            finally:
                if self._task is current:
                    self._task = None

    async def _pulse(self, direction: str, duration_seconds: float) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_seconds
        pulse = 0
        while True:
            await self._drive(direction, pulse)
            pulse += 1
            remaining = deadline - loop.time()
            if remaining <= 0:
                return
            await asyncio.sleep(min(self._keepalive_seconds, remaining))
