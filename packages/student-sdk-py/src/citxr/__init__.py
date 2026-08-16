"""The CIT Physical XR student API.

The same names work in generated and handwritten Python (FR-014):

    from citxr import device, when, every, parallel, sleep, log

    s1 = device("s1-main")

    @every(0.5)
    async def creep():
        await s1.drive.velocity(forward=0.2, durationSeconds=0.5)

Nothing here reaches hardware. Every call goes through a constrained bridge to
the local runtime, which decides whether it is allowed (FR-013).
"""

from .api import (
    Device,
    EventSubscription,
    IntervalSubscription,
    Program,
    SensorReading,
    Trigger,
    device,
    every,
    log,
    parallel,
    program,
    run_interval,
    sleep,
    when,
)
from .bridge import (
    ALLOWED_CALLS,
    Bridge,
    CancelledError,
    CommandRejected,
    Transport,
    TransportError,
    active_bridge,
    checkpoint,
    set_bridge,
)

__all__ = [
    "ALLOWED_CALLS",
    "Bridge",
    "CancelledError",
    "CommandRejected",
    "Device",
    "EventSubscription",
    "IntervalSubscription",
    "Program",
    "SensorReading",
    "Transport",
    "TransportError",
    "Trigger",
    "active_bridge",
    "checkpoint",
    "device",
    "every",
    "log",
    "parallel",
    "program",
    "run_interval",
    "set_bridge",
    "sleep",
    "when",
]
