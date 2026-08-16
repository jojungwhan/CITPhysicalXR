"""The student-facing API (FR-014).

The same names work in generated and handwritten Python, which is the point:
a student who outgrows blocks reads their own generated code and recognises it.

Design rules this module keeps to:

- Every device call goes through the bridge. Nothing here talks to hardware.
- Every loop and handler passes a cancellation checkpoint (FR-015), so stopping
  a session actually stops it rather than waiting for a student's `while True`.
- ``parallel`` is a real primitive (FR-057), not a loop that pretends.
- A device is addressed by its exact id or project alias (FR-019). There is no
  "the robot", no nearest-device lookup, and no name matching.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .bridge import CancelledError, active_bridge, checkpoint


@dataclass(frozen=True, slots=True)
class SensorReading:
    """One sensor value with the time the device reported it."""

    name: str
    values: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    @property
    def value(self) -> Any:
        """The single reading, for sensors that report exactly one number."""

        if len(self.values) != 1:
            raise KeyError(
                f"Sensor {self.name!r} reports {sorted(self.values)}; "
                "name the one you want, for example reading['distance']"
            )
        return next(iter(self.values.values()))


class _Capability:
    """`s1.drive.velocity(...)` -- a namespace bound to one device.

    The attribute chain spells the capability, not a capability plus an action:
    a manifest advertises ``drive.velocity``, so that is what goes on the wire
    (FR-007). The action is ``set``, which is what performing a capability
    means. Splitting it the other way sends ``drive``, which is not a
    capability any device declares and which the protocol schema rejects.
    """

    DEFAULT_ACTION = "set"

    def __init__(self, device: Device, namespace: str) -> None:
        self._device = device
        self._namespace = namespace

    def __getattr__(self, name: str) -> Callable[..., Awaitable[Mapping[str, Any]]]:
        if name.startswith("_"):
            raise AttributeError(name)

        capability = f"{self._namespace}.{name}"

        async def call(**arguments: Any) -> Mapping[str, Any]:
            return await self._device.send(
                capability=capability,
                action=self.DEFAULT_ACTION,
                **arguments,
            )

        return call


class Device:
    """A handle on one exact device."""

    def __init__(self, device_id: str) -> None:
        self._device_id = device_id

    @property
    def device_id(self) -> str:
        return self._device_id

    def __repr__(self) -> str:
        return f"device({self._device_id!r})"

    def __getattr__(self, capability: str) -> _Capability:
        if capability.startswith("_"):
            raise AttributeError(capability)
        return _Capability(self, capability)

    async def send(self, *, capability: str, action: str, **arguments: Any) -> Mapping[str, Any]:
        checkpoint()
        return await active_bridge().call(
            "command",
            device_id=self._device_id,
            capability=capability,
            action=action,
            arguments=arguments,
        )

    async def stop(self) -> Mapping[str, Any]:
        """Always available, and never refused for being unarmed."""

        return await self.send(capability="drive.stop", action="stop")

    async def sensor(self, name: str) -> SensorReading:
        checkpoint()
        result = await active_bridge().call("read_sensor", device_id=self._device_id, sensor=name)
        values = result.get("values", {})
        return SensorReading(name=name, values=dict(values) if values else {})

    async def info(self) -> Mapping[str, Any]:
        checkpoint()
        return await active_bridge().call("device_info", device_id=self._device_id)


_DEVICES: dict[str, Device] = {}


def device(device_id: str) -> Device:
    """Address one device by its exact id or project alias (FR-019)."""

    if not device_id or not isinstance(device_id, str):
        raise ValueError("A device id must be a non-empty string")
    existing = _DEVICES.get(device_id)
    if existing is None:
        existing = Device(device_id)
        _DEVICES[device_id] = existing
    return existing


def _reset_devices() -> None:
    """Used by the host between runs. Not part of the student API."""

    _DEVICES.clear()


async def sleep(seconds: float) -> None:
    """Wait, with a cancellation checkpoint on each side (FR-015)."""

    checkpoint()
    if seconds < 0:
        raise ValueError("Cannot sleep for a negative time")
    await asyncio.sleep(seconds)
    checkpoint()


async def log(message: str, **context: Any) -> None:
    """Print into the Studio console. Redaction happens in the runtime."""

    checkpoint()
    await active_bridge().call("log", message=str(message), context=context)


async def parallel(*actions: Awaitable[Any]) -> Sequence[Any]:
    """FR-057. Start every action together and wait for all of them.

    If one fails the rest are cancelled, because a half-executed parallel move
    is the case where two robots keep going in different directions.
    """

    checkpoint()
    if not actions:
        return ()
    tasks = [asyncio.ensure_future(action) for action in actions]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


@dataclass(frozen=True, slots=True)
class EventSubscription:
    """What `@when` registered, so the host can run and cancel it."""

    trigger: str
    device_id: str | None
    handler: Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class IntervalSubscription:
    """What `@every` registered."""

    seconds: float
    handler: Callable[[], Awaitable[None]]


class Program:
    """Collects what a student's module declared, so the host can run it."""

    def __init__(self) -> None:
        self.events: list[EventSubscription] = []
        self.intervals: list[IntervalSubscription] = []

    def clear(self) -> None:
        self.events.clear()
        self.intervals.clear()


_PROGRAM = Program()


def program() -> Program:
    return _PROGRAM


@dataclass(frozen=True, slots=True)
class Trigger:
    """A named thing to wait for, produced by a device's event helpers."""

    name: str
    device_id: str | None = None


def when(
    trigger: Trigger | str,
) -> Callable[[Callable[[], Awaitable[None]]], Callable[[], Awaitable[None]]]:
    """Run a handler when a trigger fires."""

    resolved = trigger if isinstance(trigger, Trigger) else Trigger(name=trigger)

    def decorate(handler: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        _PROGRAM.events.append(
            EventSubscription(trigger=resolved.name, device_id=resolved.device_id, handler=handler)
        )
        return handler

    return decorate


def every(
    seconds: float,
) -> Callable[[Callable[[], Awaitable[None]]], Callable[[], Awaitable[None]]]:
    """Run a handler on an interval, with a checkpoint between runs."""

    if seconds <= 0:
        raise ValueError("An interval must be positive")

    def decorate(handler: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        _PROGRAM.intervals.append(IntervalSubscription(seconds=seconds, handler=handler))
        return handler

    return decorate


async def run_interval(subscription: IntervalSubscription, *, iterations: int | None = None) -> int:
    """Drive one interval subscription. The host owns the loop, not the student."""

    completed = 0
    while iterations is None or completed < iterations:
        try:
            checkpoint()
        except CancelledError:
            return completed
        await subscription.handler()
        completed += 1
        try:
            await sleep(subscription.seconds)
        except CancelledError:
            return completed
    return completed
