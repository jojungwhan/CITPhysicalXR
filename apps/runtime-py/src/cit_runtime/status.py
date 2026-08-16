"""What the instructor console shows for one device (FR-065, UI 11.3).

Every field here is observed rather than declared. Battery comes from the
telemetry the device actually sent; firmware appears only if the adapter
reported it; the last command is recorded where commands are dispatched. A field
the runtime has not been told is ``None``, and the console says so, because a
confident "Battery 100%" for a device that has never reported one is worse than
a blank.

The warnings are derived the same way. A warning exists because something was
observed -- a low battery reading, a stale heartbeat, a failed adapter, an arm
window about to close -- and disappears when the observation does.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime

from cit_protocol import DeviceEvent

# A battery reading at or below this is worth an instructor's attention before a
# hub dies in the middle of someone's lesson.
LOW_BATTERY_PERCENT = 20.0

# An arm window with less than this left is about to lapse (FR-066 step 6).
ARM_EXPIRY_WARNING_SECONDS = 30.0

_BATTERY_EVENT_SUFFIXES = ("battery", "battery_warning")
_FIRMWARE_EVENT_NAMES = frozenset({"diagnostic.firmware", "diagnostic.version"})


@dataclass(frozen=True, slots=True)
class DeviceStatus:
    """The observed half of a device card. Runtime-owned state lives elsewhere."""

    device_id: str
    battery_percent: float | None = None
    battery_reported_at: datetime | None = None
    firmware: str | None = None
    last_command_capability: str | None = None
    last_command_action: str | None = None
    last_command_at: datetime | None = None
    last_command_result: str | None = None
    last_telemetry_name: str | None = None
    last_telemetry_at: datetime | None = None
    warnings: tuple[str, ...] = field(default=())


class DeviceStatusProjection:
    """Folds the event stream and dispatch results into per-device status."""

    def __init__(self) -> None:
        self._status: dict[str, DeviceStatus] = {}

    def _current(self, device_id: str) -> DeviceStatus:
        return self._status.get(device_id, DeviceStatus(device_id=device_id))

    def get(self, device_id: str) -> DeviceStatus:
        return self._current(device_id)

    def observe(self, event: DeviceEvent) -> None:
        """Subscribe this to the router. Historical events are ignored.

        A replayed recording must not repaint the console as though a robot had
        just reported in (FR-064).
        """

        if event.historical:
            return
        current = self._current(event.deviceId)
        updated = current

        if event.category == "telemetry":
            updated = replace(
                updated,
                last_telemetry_name=event.name,
                last_telemetry_at=event.receivedAt,
            )
        if event.name.endswith(_BATTERY_EVENT_SUFFIXES):
            percent = _percent(dict(event.values))
            if percent is not None:
                updated = replace(
                    updated,
                    battery_percent=percent,
                    battery_reported_at=event.receivedAt,
                )
        elif event.name in _FIRMWARE_EVENT_NAMES:
            values = dict(event.values)
            reported = values.get("version") or values.get("firmware")
            if isinstance(reported, str) and reported:
                updated = replace(updated, firmware=reported)

        self._status[event.deviceId] = updated

    def note_command(
        self,
        *,
        device_id: str,
        capability: str,
        action: str,
        result: str,
        at: datetime,
    ) -> None:
        self._status[device_id] = replace(
            self._current(device_id),
            last_command_capability=capability,
            last_command_action=action,
            last_command_at=at,
            last_command_result=result,
        )

    def forget(self, device_id: str) -> None:
        self._status.pop(device_id, None)


def _percent(values: Mapping[str, object]) -> float | None:
    for key in ("percent", "batteryPercent", "level"):
        value = values.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def derive_warnings(
    status: DeviceStatus,
    *,
    device_state: str,
    failure_reason: str | None,
    arm_seconds_remaining: float | None,
    stale_watchdogs: Mapping[str, float],
) -> tuple[str, ...]:
    """Turn observations into the warning strings a device card shows."""

    warnings: list[str] = []
    if failure_reason is not None:
        warnings.append(f"adapter: {failure_reason}")
    elif device_state in {"disconnected", "failed"}:
        warnings.append(f"device is {device_state}")
    if status.battery_percent is not None and status.battery_percent <= LOW_BATTERY_PERCENT:
        warnings.append(f"battery {status.battery_percent:.0f}%")
    if arm_seconds_remaining is not None and arm_seconds_remaining <= ARM_EXPIRY_WARNING_SECONDS:
        warnings.append(f"arm expires in {arm_seconds_remaining:.0f}s")
    for kind, age in sorted(stale_watchdogs.items()):
        warnings.append(f"{kind} heartbeat {age * 1000:.0f} ms old")
    return tuple(warnings)
