"""Injectable clocks.

FR-060 and FR-070 require monotonic timing for watchdogs and a separate wall
clock for protocol timestamps. Nothing in the runtime reads a clock directly, so
every timeout is reproducible in a test.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """A wall clock for protocol fields and a monotonic source for timeouts."""

    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...


class SystemClock:
    """The only clock permitted to read the host."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()


class ManualClock:
    """A clock advanced by tests, keeping both sources consistent."""

    def __init__(
        self,
        *,
        start: datetime | None = None,
        monotonic_start: float = 0.0,
    ) -> None:
        initial = start if start is not None else datetime(2026, 1, 1, tzinfo=UTC)
        if initial.tzinfo is None or initial.utcoffset() is None:
            raise ValueError("Manual clock start must be timezone aware")
        self._now = initial
        self._monotonic = monotonic_start

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, seconds: float) -> None:
        """Move both sources forward by the same amount."""

        if seconds < 0:
            raise ValueError("A monotonic clock cannot move backwards")
        self._monotonic += seconds
        self._now = self._now + timedelta(seconds=seconds)
