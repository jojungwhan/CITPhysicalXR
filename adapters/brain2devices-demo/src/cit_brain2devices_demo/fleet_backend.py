"""Bounded, one-shot fleet-sequence backends.

The sequence controller is deliberately separate from every per-aircraft
adapter. Its public operation is an instructor-configured workflow, not a raw
takeoff primitive.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from html.parser import HTMLParser
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class FleetSequenceBackendError(RuntimeError):
    """A fleet sequence could not be safely accepted or completed."""


class FleetSequenceBackend(Protocol):
    async def start(self) -> Mapping[str, object]: ...

    async def status(self) -> Mapping[str, object]: ...

    async def arm(self, parameters: Mapping[str, object]) -> Mapping[str, object]: ...

    async def trigger(self, *, source_node_id: str | None) -> Mapping[str, object]: ...

    async def stop(self, *, reason: str) -> Mapping[str, object]: ...

    async def close(self) -> None: ...


class Brain2DevicesFleetApi(Protocol):
    """The only upstream boundary used by the physical sequence controller."""

    async def open(self) -> None: ...

    async def state(self) -> Mapping[str, object]: ...

    async def fleet_command(
        self,
        action: str,
        drone_ids: Sequence[str],
    ) -> Mapping[str, object]: ...


class _TokenParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "meta":
            return
        values = dict(attrs)
        if values.get("name") == "brain2devices-token" and values.get("content"):
            self.token = values["content"]


class Brain2DevicesLocalFleetApi:
    """Loopback-only client exposing only state and bounded fleet commands."""

    def __init__(self, *, origin: str = "http://127.0.0.1:8765") -> None:
        if origin != "http://127.0.0.1:8765":
            raise ValueError("Brain2Devices fleet API is restricted to loopback")
        self._origin = origin
        self._token: str | None = None

    async def open(self) -> None:
        self._token = await asyncio.to_thread(self._read_token)

    async def state(self) -> Mapping[str, object]:
        return await asyncio.to_thread(self._request, "/api/state", None)

    async def fleet_command(
        self,
        action: str,
        drone_ids: Sequence[str],
    ) -> Mapping[str, object]:
        if action not in {"takeoff", "land", "emergency"}:
            raise ValueError("The bounded fleet client permits only takeoff, land, or emergency")
        if not drone_ids or len(drone_ids) > 8 or len(set(drone_ids)) != len(drone_ids):
            raise ValueError("Fleet command requires one to eight unique drone IDs")
        return await asyncio.to_thread(
            self._request,
            "/api/fleet/command",
            {"action": action, "drone_ids": list(drone_ids), "confirmed": True},
        )

    def _read_token(self) -> str:
        try:
            with urlopen(f"{self._origin}/", timeout=5) as response:
                page = response.read(65_536).decode("utf-8")
        except (OSError, URLError, UnicodeDecodeError) as error:
            raise FleetSequenceBackendError(
                "Brain2Devices loopback service is unavailable"
            ) from error
        parser = _TokenParser()
        parser.feed(page)
        if parser.token is None:
            raise FleetSequenceBackendError("Brain2Devices local control grant is unavailable")
        return parser.token

    def _request(
        self,
        path: str,
        body: Mapping[str, object] | None,
    ) -> dict[str, object]:
        headers = {"Accept": "application/json"}
        data = None
        method = "GET"
        if body is not None:
            if self._token is None:
                raise FleetSequenceBackendError("Brain2Devices local control grant is unavailable")
            data = json.dumps(dict(body), separators=(",", ":")).encode("utf-8")
            method = "POST"
            headers.update(
                {
                    "Content-Type": "application/json",
                    "X-Brain2Devices-Token": self._token,
                }
            )
        request = Request(f"{self._origin}{path}", data=data, method=method, headers=headers)
        try:
            with urlopen(request, timeout=15) as response:
                raw = response.read(262_144)
            value: object = json.loads(raw.decode("utf-8"))
        except HTTPError as error:
            detail = ""
            try:
                parsed: object = json.loads(error.read(65_536).decode("utf-8"))
                if isinstance(parsed, dict):
                    detail = str(parsed.get("error", ""))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass
            raise FleetSequenceBackendError(
                (detail or f"Brain2Devices returned HTTP {error.code}")[:500]
            ) from error
        except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FleetSequenceBackendError("Brain2Devices returned an invalid response") from error
        if not isinstance(value, dict):
            raise FleetSequenceBackendError("Brain2Devices response must be an object")
        if body is not None and value.get("accepted") is not True:
            raise FleetSequenceBackendError(str(value.get("error", "Operation was rejected"))[:500])
        return value


class Brain2DevicesApiFleetSequenceBackend:
    """Dispatch one takeoff at a time and confirm flight before advancing."""

    def __init__(
        self,
        *,
        api: Brain2DevicesFleetApi,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        allowed_drone_ids: Sequence[str] | None = None,
        confirmation_attempts: int = 50,
        confirmation_interval_seconds: float = 0.2,
        monotonic: Callable[[], float] = time.monotonic,
        arm_ttl_seconds: float = 60.0,
    ) -> None:
        if confirmation_attempts < 1:
            raise ValueError("confirmation_attempts must be positive")
        if confirmation_interval_seconds <= 0:
            raise ValueError("confirmation interval must be positive")
        if not 5 <= arm_ttl_seconds <= 120:
            raise ValueError("arm_ttl_seconds must be from 5 to 120")
        self._api = api
        self._sleep = sleep
        self._monotonic = monotonic
        self._arm_ttl_seconds = arm_ttl_seconds
        self._armed_deadline: float | None = None
        if allowed_drone_ids is not None and (
            not 2 <= len(allowed_drone_ids) <= 8
            or len(set(allowed_drone_ids)) != len(allowed_drone_ids)
        ):
            raise ValueError("allowed_drone_ids must contain two to eight unique IDs")
        self._allowed_drone_ids = (
            None if allowed_drone_ids is None else frozenset(allowed_drone_ids)
        )
        self._confirmation_attempts = confirmation_attempts
        self._confirmation_interval_seconds = confirmation_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._selected: tuple[str, ...] = ()
        self._allowed_sources: frozenset[str] = frozenset()
        self._interval_seconds = 2.0
        self._minimum_battery = 30
        self._state: dict[str, object] = {
            "available": False,
            "active": False,
            "armed": False,
            "phase": "starting",
            "progress": 0.0,
            "message": "Checking the local Brain2Devices fleet",
            "error": None,
            "triggeredBy": None,
            "selectedDroneIds": [],
            "launchedDroneIds": [],
            "landRequestedDroneIds": [],
            "availableDrones": [],
            "simulated": False,
        }

    async def start(self) -> Mapping[str, object]:
        await self._api.open()
        drones = _fleet_drones(await self._api.state())
        available = _project_available_drones(self._approved_drones(drones))
        connected = [item for item in available if item["connection"] == "connected"]
        self._state.update(
            {
                "available": len(connected) >= 2,
                "phase": "idle" if len(connected) >= 2 else "unavailable",
                "message": (
                    f"{len(connected)} connected aircraft are ready for selection"
                    if len(connected) >= 2
                    else "Connect at least two independently routed Tellos"
                ),
                "availableDrones": available,
            }
        )
        return await self.status()

    async def status(self) -> Mapping[str, object]:
        self._expire_arm_if_needed()
        return _copy_status(self._state)

    async def arm(self, parameters: Mapping[str, object]) -> Mapping[str, object]:
        if self._task is not None and not self._task.done():
            raise FleetSequenceBackendError("A fleet sequence is already running")
        selected = _string_tuple(parameters.get("droneIds"), name="droneIds")
        if self._allowed_drone_ids is not None:
            outside_assignment = set(selected) - self._allowed_drone_ids
            if outside_assignment:
                raise FleetSequenceBackendError(
                    "Sequence requested aircraft outside this Fabric session: "
                    + ", ".join(sorted(outside_assignment))
                )
        allowed_sources = _string_tuple(
            parameters.get("allowedSourceNodeIds"),
            name="allowedSourceNodeIds",
            minimum=0,
            maximum=8,
        )
        minimum_battery = _bounded_integer(
            parameters.get("minimumBatteryPercent"),
            name="minimumBatteryPercent",
            minimum=20,
            maximum=100,
        )
        drones = _fleet_drones(await self._api.state())
        for drone_id in selected:
            _require_grounded_ready(drones, drone_id, minimum_battery)
        self._selected = selected
        self._allowed_sources = frozenset(allowed_sources)
        self._interval_seconds = _bounded_number(
            parameters.get("launchIntervalSeconds"),
            name="launchIntervalSeconds",
            minimum=1,
            maximum=15,
        )
        self._minimum_battery = minimum_battery
        self._armed_deadline = self._monotonic() + self._arm_ttl_seconds
        self._state.update(
            {
                "available": True,
                "active": False,
                "armed": True,
                "phase": "armed",
                "progress": 0.0,
                "message": "One ordered fleet launch is armed and waiting for an approved trigger",
                "error": None,
                "triggeredBy": None,
                "selectedDroneIds": list(selected),
                "launchedDroneIds": [],
                "landRequestedDroneIds": [],
                "availableDrones": _project_available_drones(self._approved_drones(drones)),
                "launchIntervalSeconds": self._interval_seconds,
                "minimumBatteryPercent": self._minimum_battery,
                "allowedSourceNodeIds": sorted(self._allowed_sources),
                "armTimeoutSeconds": self._arm_ttl_seconds,
            }
        )
        return await self.status()

    async def trigger(self, *, source_node_id: str | None) -> Mapping[str, object]:
        self._expire_arm_if_needed()
        if self._state.get("armed") is not True:
            raise ValueError("Fleet sequence is not armed")
        if source_node_id is not None and source_node_id not in self._allowed_sources:
            raise ValueError("Trigger source is not allowed by the armed sequence")
        self._state.update(
            {
                "active": True,
                "armed": False,
                "phase": "launching",
                "progress": 0.0,
                "message": "Validating the first aircraft",
                "error": None,
                "triggeredBy": source_node_id or "instructor_button",
                "launchedDroneIds": [],
                "landRequestedDroneIds": [],
            }
        )
        self._armed_deadline = None
        self._task = asyncio.create_task(self._run_sequence(), name="physical-fleet-sequence")
        return await self.status()

    async def stop(self, *, reason: str) -> Mapping[str, object]:
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._task = None
        self._armed_deadline = None
        land_error = await self._request_land(self._selected)
        self._state.update(
            {
                "active": False,
                "armed": False,
                "phase": "stopped" if land_error is None else "failed",
                "progress": 0.0,
                "message": (
                    f"Sequence stopped; landing requested for the selected fleet: {reason}"
                    if land_error is None
                    else "Sequence stopped, but the local landing request failed"
                ),
                "error": land_error,
                "landRequestedDroneIds": list(self._selected),
            }
        )
        return await self.status()

    def _expire_arm_if_needed(self) -> None:
        deadline = self._armed_deadline
        if deadline is None or self._state.get("armed") is not True or self._monotonic() < deadline:
            return
        self._armed_deadline = None
        self._state.update(
            {
                "active": False,
                "armed": False,
                "phase": "expired",
                "message": "The one-shot fleet arm expired; review and arm again",
                "error": None,
                "triggeredBy": None,
            }
        )

    async def close(self) -> None:
        await self.stop(reason="adapter_shutdown")

    async def _run_sequence(self) -> None:
        launched: list[str] = []
        attempted: list[str] = []
        try:
            total = len(self._selected)
            for index, drone_id in enumerate(self._selected):
                drones = _fleet_drones(await self._api.state())
                _require_grounded_ready(drones, drone_id, self._minimum_battery)
                attempted.append(drone_id)
                self._state.update(
                    {
                        "message": f"Sending launch {index + 1} of {total} to {drone_id}",
                        "currentDroneId": drone_id,
                    }
                )
                await self._api.fleet_command("takeoff", (drone_id,))
                await self._wait_until_flying(drone_id)
                launched.append(drone_id)
                self._state.update(
                    {
                        "launchedDroneIds": list(launched),
                        "progress": len(launched) / total,
                        "message": f"Confirmed aircraft {len(launched)} of {total} airborne",
                    }
                )
                if index + 1 < total:
                    await self._sleep(self._interval_seconds)
            self._state.update(
                {
                    "active": False,
                    "phase": "completed",
                    "progress": 1.0,
                    "message": f"All {total} aircraft reported airborne in order",
                    "currentDroneId": None,
                }
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            possible_airborne = tuple(dict.fromkeys((*launched, *attempted)))
            land_error = await self._request_land(possible_airborne)
            detail = str(error)[:500]
            if land_error is not None:
                detail = f"{detail}; landing request also failed: {land_error}"[:500]
            self._state.update(
                {
                    "active": False,
                    "armed": False,
                    "phase": "failed",
                    "error": detail,
                    "message": "Sequence failed; no further launch was attempted",
                    "currentDroneId": None,
                    "landRequestedDroneIds": list(possible_airborne),
                }
            )

    async def _wait_until_flying(self, drone_id: str) -> None:
        for _attempt in range(self._confirmation_attempts):
            drones = _fleet_drones(await self._api.state())
            drone = drones.get(drone_id)
            if drone is None:
                raise FleetSequenceBackendError(f"Drone {drone_id!r} disappeared after takeoff")
            if drone.get("connection") != "connected":
                raise FleetSequenceBackendError(
                    f"Drone {drone_id!r} disconnected before airborne confirmation"
                )
            command_error = drone.get("command_error")
            if isinstance(command_error, dict) and command_error:
                detail = command_error.get("detail") or command_error.get("title")
                raise FleetSequenceBackendError(
                    f"Drone {drone_id!r} rejected takeoff: {str(detail)[:300]}"
                )
            if drone.get("flight") == "flying":
                return
            await self._sleep(self._confirmation_interval_seconds)
        raise FleetSequenceBackendError(
            f"Drone {drone_id!r} did not report airborne before the confirmation timeout"
        )

    async def _request_land(self, drone_ids: Sequence[str]) -> str | None:
        if not drone_ids:
            return None
        try:
            await self._api.fleet_command("land", tuple(drone_ids))
        except Exception as error:
            return str(error)[:500]
        return None

    def _approved_drones(
        self,
        drones: Mapping[str, Mapping[str, object]],
    ) -> dict[str, Mapping[str, object]]:
        if self._allowed_drone_ids is None:
            return dict(drones)
        return {
            drone_id: drone
            for drone_id, drone in drones.items()
            if drone_id in self._allowed_drone_ids
        }


class SimulatedFleetSequenceBackend:
    """Software-only ordered fleet used by CI and tutor rehearsal."""

    def __init__(
        self,
        *,
        drone_ids: Sequence[str] = ("primary", "drone-2"),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        arm_ttl_seconds: float = 60.0,
    ) -> None:
        if not 2 <= len(drone_ids) <= 8 or len(set(drone_ids)) != len(drone_ids):
            raise ValueError("Simulation requires two to eight unique drone IDs")
        if not 5 <= arm_ttl_seconds <= 120:
            raise ValueError("arm_ttl_seconds must be from 5 to 120")
        self._available_drone_ids = tuple(drone_ids)
        self._sleep = sleep
        self._monotonic = monotonic
        self._arm_ttl_seconds = arm_ttl_seconds
        self._armed_deadline: float | None = None
        self._task: asyncio.Task[None] | None = None
        self._selected: tuple[str, ...] = ()
        self._allowed_sources: frozenset[str] = frozenset()
        self._interval_seconds = 2.0
        self._minimum_battery = 30
        self._state: dict[str, object] = {
            "available": True,
            "active": False,
            "armed": False,
            "phase": "idle",
            "progress": 0.0,
            "message": "Simulation is ready; no physical aircraft can move",
            "error": None,
            "triggeredBy": None,
            "selectedDroneIds": [],
            "launchedDroneIds": [],
            "availableDrones": self._available_drones(),
            "simulated": True,
        }
        self.command_log: list[str] = []

    async def start(self) -> Mapping[str, object]:
        return await self.status()

    async def status(self) -> Mapping[str, object]:
        self._expire_arm_if_needed()
        return _copy_status(self._state)

    async def arm(self, parameters: Mapping[str, object]) -> Mapping[str, object]:
        if self._task is not None and not self._task.done():
            raise FleetSequenceBackendError("A fleet sequence is already running")
        selected = _string_tuple(parameters.get("droneIds"), name="droneIds")
        unknown = set(selected) - set(self._available_drone_ids)
        if unknown:
            raise FleetSequenceBackendError(
                f"Unknown simulated drone IDs: {', '.join(sorted(unknown))}"
            )
        self._selected = selected
        self._allowed_sources = frozenset(
            _string_tuple(
                parameters.get("allowedSourceNodeIds"),
                name="allowedSourceNodeIds",
                minimum=0,
                maximum=8,
            )
        )
        self._interval_seconds = _bounded_number(
            parameters.get("launchIntervalSeconds"),
            name="launchIntervalSeconds",
            minimum=1,
            maximum=15,
        )
        self._minimum_battery = _bounded_integer(
            parameters.get("minimumBatteryPercent"),
            name="minimumBatteryPercent",
            minimum=20,
            maximum=100,
        )
        self._armed_deadline = self._monotonic() + self._arm_ttl_seconds
        self._state.update(
            {
                "active": False,
                "armed": True,
                "phase": "armed",
                "progress": 0.0,
                "message": "One sequential launch is armed and waiting for an approved trigger",
                "error": None,
                "triggeredBy": None,
                "selectedDroneIds": list(self._selected),
                "launchedDroneIds": [],
                "launchIntervalSeconds": self._interval_seconds,
                "minimumBatteryPercent": self._minimum_battery,
                "allowedSourceNodeIds": sorted(self._allowed_sources),
                "armTimeoutSeconds": self._arm_ttl_seconds,
            }
        )
        return await self.status()

    async def trigger(self, *, source_node_id: str | None) -> Mapping[str, object]:
        self._expire_arm_if_needed()
        if self._state.get("armed") is not True:
            raise ValueError("Fleet sequence is not armed")
        if source_node_id is not None and source_node_id not in self._allowed_sources:
            raise ValueError("Trigger source is not allowed by the armed sequence")
        self._state.update(
            {
                "active": True,
                "armed": False,
                "phase": "launching",
                "progress": 0.0,
                "message": "Starting the ordered simulated launch",
                "triggeredBy": source_node_id or "instructor_button",
                "launchedDroneIds": [],
            }
        )
        self._armed_deadline = None
        self._task = asyncio.create_task(self._run_sequence(), name="simulated-fleet-sequence")
        return await self.status()

    async def stop(self, *, reason: str) -> Mapping[str, object]:
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        launched_value = self._state.get("launchedDroneIds")
        launched = (
            [item for item in launched_value if isinstance(item, str)]
            if isinstance(launched_value, list)
            else []
        )
        for drone_id in launched:
            self.command_log.append(f"land:{drone_id}")
        self._task = None
        self._armed_deadline = None
        self._state.update(
            {
                "active": False,
                "armed": False,
                "phase": "stopped",
                "message": f"Sequence stopped and launched simulations landed: {reason}",
                "progress": 0.0,
                "launchedDroneIds": [],
            }
        )
        return await self.status()

    def _expire_arm_if_needed(self) -> None:
        deadline = self._armed_deadline
        if deadline is None or self._state.get("armed") is not True or self._monotonic() < deadline:
            return
        self._armed_deadline = None
        self._state.update(
            {
                "active": False,
                "armed": False,
                "phase": "expired",
                "message": "The one-shot fleet arm expired; review and arm again",
                "error": None,
                "triggeredBy": None,
            }
        )

    async def close(self) -> None:
        await self.stop(reason="adapter_shutdown")

    async def _run_sequence(self) -> None:
        launched: list[str] = []
        try:
            total = len(self._selected)
            for index, drone_id in enumerate(self._selected):
                self.command_log.append(f"takeoff:{drone_id}")
                launched.append(drone_id)
                self._state.update(
                    {
                        "launchedDroneIds": list(launched),
                        "progress": len(launched) / total,
                        "message": f"Confirmed simulated launch {len(launched)} of {total}",
                    }
                )
                if index + 1 < total:
                    await self._sleep(self._interval_seconds)
            self._state.update(
                {
                    "active": False,
                    "phase": "completed",
                    "progress": 1.0,
                    "message": f"All {total} simulated launches completed in order",
                }
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._state.update(
                {
                    "active": False,
                    "armed": False,
                    "phase": "failed",
                    "error": str(error)[:500],
                    "message": "Sequence failed; no further launch was attempted",
                }
            )

    def _available_drones(self) -> list[dict[str, object]]:
        return [
            {
                "id": drone_id,
                "label": f"Simulated Tello {index + 1}",
                "connection": "connected",
                "flight": "landed",
                "batteryPercent": 87 - index,
            }
            for index, drone_id in enumerate(self._available_drone_ids)
        ]


def _string_tuple(
    value: object,
    *,
    name: str,
    minimum: int = 2,
    maximum: int = 8,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{name} must contain {minimum} to {maximum} identifiers")
    if any(not isinstance(item, str) or not item or len(item) > 128 for item in value):
        raise ValueError(f"{name} contains an invalid identifier")
    result = tuple(value)
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _bounded_number(
    value: object,
    *,
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not minimum <= result <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return result


def _bounded_integer(
    value: object,
    *,
    name: str,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def _copy_status(state: Mapping[str, object]) -> dict[str, object]:
    return {
        key: ([dict(item) for item in value] if key == "availableDrones" else list(value))
        if isinstance(value, list)
        else value
        for key, value in state.items()
    }


def _fleet_drones(state: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    fleet = state.get("fleet")
    if not isinstance(fleet, dict) or not isinstance(fleet.get("drones"), list):
        raise FleetSequenceBackendError("Brain2Devices fleet state is unavailable")
    drones: dict[str, Mapping[str, object]] = {}
    for value in fleet["drones"]:
        if not isinstance(value, dict):
            continue
        drone_id = value.get("id")
        if isinstance(drone_id, str) and drone_id:
            drones[drone_id] = value
    return drones


def _project_available_drones(
    drones: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    projected: list[dict[str, object]] = []
    for drone_id, drone in drones.items():
        telemetry = drone.get("telemetry")
        battery = telemetry.get("battery_percent") if isinstance(telemetry, dict) else None
        projected.append(
            {
                "id": drone_id,
                "label": str(drone.get("label") or drone_id)[:128],
                "connection": str(drone.get("connection") or "unknown"),
                "flight": str(drone.get("flight") or "unknown"),
                "batteryPercent": battery,
            }
        )
    return projected


def _require_grounded_ready(
    drones: Mapping[str, Mapping[str, object]],
    drone_id: str,
    minimum_battery: int,
) -> None:
    drone = drones.get(drone_id)
    if drone is None:
        raise FleetSequenceBackendError(f"Brain2Devices does not report drone {drone_id!r}")
    if drone.get("connection") != "connected":
        raise FleetSequenceBackendError(f"Drone {drone_id!r} is not connected")
    if drone.get("flight") != "landed":
        raise FleetSequenceBackendError(f"Drone {drone_id!r} is not confirmed landed")
    telemetry = drone.get("telemetry")
    battery = telemetry.get("battery_percent") if isinstance(telemetry, dict) else None
    if isinstance(battery, bool) or not isinstance(battery, (int, float)):
        raise FleetSequenceBackendError(f"Drone {drone_id!r} has no verified battery reading")
    if float(battery) < minimum_battery:
        raise FleetSequenceBackendError(
            f"Drone {drone_id!r} battery {float(battery):g}% is below {minimum_battery}%"
        )
