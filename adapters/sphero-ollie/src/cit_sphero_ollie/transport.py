"""Injectable Ollie transport; Sphero protocol code stays outside Fabric core."""

from __future__ import annotations

import asyncio
import math
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .discovery import scan_sphero_ollies
from .models import SpheroSensorSnapshot
from .policy import OllieRoll, vector_to_roll


class OllieTransport(Protocol):
    @property
    def connected(self) -> bool: ...

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def stop(self) -> None: ...

    async def set_velocity(self, forward: float, right: float, clockwise: float) -> OllieRoll: ...

    async def set_color(self, red: int, green: int, blue: int) -> None: ...

    async def reset_aim(self) -> None: ...

    async def read_sensor(self) -> SpheroSensorSnapshot: ...


class FakeOllieTransport:
    def __init__(self) -> None:
        self._connected = False
        self._sequence = 0
        self._heading = 0
        self._speed = 0
        self._color = (0, 0, 0)
        self.commands: list[tuple[str, tuple[object, ...]]] = []

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def stop(self) -> None:
        self._speed = 0
        self.commands.append(("stop", ()))

    async def set_velocity(self, forward: float, right: float, clockwise: float) -> OllieRoll:
        roll = vector_to_roll(forward, right, clockwise)
        self._heading = roll.heading_degrees
        self._speed = roll.speed_value
        self.commands.append(("velocity", (forward, right, clockwise, roll)))
        return roll

    async def set_color(self, red: int, green: int, blue: int) -> None:
        _validate_rgb(red, green, blue)
        self._color = (red, green, blue)
        self.commands.append(("color", self._color))

    async def reset_aim(self) -> None:
        self.commands.append(("reset_aim", ()))

    async def read_sensor(self) -> SpheroSensorSnapshot:
        self._sequence += 1
        return SpheroSensorSnapshot.from_values(
            self._sequence,
            {
                "model": "sphero-ollie",
                "headingDegrees": self._heading,
                "speedValue": self._speed,
                "mainLed": {
                    "red": self._color[0],
                    "green": self._color[1],
                    "blue": self._color[2],
                },
                "simulated": True,
            },
        )


@dataclass(frozen=True, slots=True)
class _ToyIdentity:
    address: str
    name: str


class _ExactBleakAdapter:
    """Synchronous adapter shape expected by spherov2, backed by modern Bleak."""

    def __init__(self, target: Any) -> None:
        self._event_loop = asyncio.new_event_loop()
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._event_loop.run_forever,
            name="cit-sphero-ollie-bleak",
            daemon=True,
        )
        self._thread.start()
        self._client: Any = None
        try:
            self._client = self._execute(self._connect(target))
        except BaseException:
            self.close(disconnect=False)
            raise

    async def _connect(self, target: Any) -> Any:
        from bleak import BleakClient

        client = BleakClient(target, timeout=8.0)
        await client.connect()
        return client

    def _execute(self, coroutine: Any) -> Any:
        with self._lock:
            return asyncio.run_coroutine_threadsafe(coroutine, self._event_loop).result(timeout=15)

    def close(self, disconnect: bool = True) -> None:
        client, self._client = self._client, None
        try:
            if disconnect and client is not None and client.is_connected:
                self._execute(client.disconnect())
        finally:
            with self._lock:
                self._event_loop.call_soon_threadsafe(self._event_loop.stop)
                self._thread.join(timeout=10)
            if not self._thread.is_alive():
                self._event_loop.close()

    def set_callback(self, uuid: str, callback: object) -> None:
        if self._client is None:
            raise RuntimeError("Sphero Ollie BLE client is closed")
        self._execute(self._client.start_notify(uuid, callback))

    def write(self, uuid: str, data: bytes | bytearray) -> None:
        if self._client is None:
            raise RuntimeError("Sphero Ollie BLE client is closed")
        self._execute(self._client.write_gatt_char(uuid, data, response=True))


def _with_response_validation(execute: Callable[[Any], Any]) -> Callable[[Any], Any]:
    def execute_and_validate(packet: Any) -> Any:
        response = execute(packet)
        check_error = getattr(response, "check_error", None)
        if not callable(check_error):
            raise RuntimeError("Sphero Ollie returned an invalid command response")
        check_error()
        return response

    return execute_and_validate


class Spherov2OllieTransport:
    """Exact-candidate Ollie transport using spherov2 behind an optional boundary."""

    def __init__(
        self,
        candidate_id: str,
        *,
        scan_timeout_seconds: float = 8,
        color_factory: Callable[[int, int, int], Any] | None = None,
    ) -> None:
        self.candidate_id = candidate_id
        self.scan_timeout_seconds = scan_timeout_seconds
        self._toy: Any = None
        self._api: Any = None
        self._color_factory = color_factory
        self._connected = False
        self._sequence = 0

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        try:
            from spherov2.sphero_edu import SpheroEduAPI
            from spherov2.toy.ollie import Ollie
            from spherov2.types import Color
        except ImportError as error:
            raise RuntimeError(
                "Sphero Ollie hardware support is not installed; run the CIT business installer"
            ) from error
        matches = [
            item
            for item in await scan_sphero_ollies(self.scan_timeout_seconds)
            if item.candidate_id == self.candidate_id
        ]
        if len(matches) != 1:
            raise RuntimeError(
                "The exact selected 2B-XXXX Ollie advertisement is no longer visible"
            )
        candidate = matches[0]
        target = candidate.device or candidate.address

        def adapter_factory(_address: str) -> _ExactBleakAdapter:
            return _ExactBleakAdapter(target)

        self._toy = Ollie(_ToyIdentity(candidate.address, candidate.display_name), adapter_factory)
        self._api = SpheroEduAPI(self._toy)
        try:
            await asyncio.to_thread(self._api.__enter__)
        except BaseException:
            self._toy = None
            self._api = None
            raise
        self._toy._execute = _with_response_validation(self._toy._execute)
        self._color_factory = Color
        self._connected = True

    async def disconnect(self) -> None:
        api, self._api = self._api, None
        self._connected = False
        self._toy = None
        if api is not None:
            await asyncio.to_thread(api.__exit__, None, None, None)

    def _require_api(self) -> Any:
        if not self._connected or self._api is None:
            raise RuntimeError("Sphero Ollie is not connected")
        return self._api

    async def stop(self) -> None:
        await asyncio.to_thread(self._require_api().stop_roll)

    async def set_velocity(self, forward: float, right: float, clockwise: float) -> OllieRoll:
        roll = vector_to_roll(forward, right, clockwise)
        api = self._require_api()

        def apply_roll() -> None:
            if roll.speed_value == 0:
                api.stop_roll()
                return
            api.set_heading(roll.heading_degrees)
            api.set_speed(roll.speed_value)

        await asyncio.to_thread(apply_roll)
        return roll

    async def set_color(self, red: int, green: int, blue: int) -> None:
        _validate_rgb(red, green, blue)
        api = self._require_api()
        color_factory = self._color_factory
        if color_factory is None:
            raise RuntimeError("Sphero Ollie is not connected")
        await asyncio.to_thread(api.set_main_led, color_factory(red, green, blue))

    async def reset_aim(self) -> None:
        await asyncio.to_thread(self._require_api().reset_aim)

    async def read_sensor(self) -> SpheroSensorSnapshot:
        api = self._require_api()
        toy = self._toy

        def collect() -> dict[str, object]:
            values: dict[str, object] = {"model": "sphero-ollie", "simulated": False}
            getters = {
                "acceleration": api.get_acceleration,
                "orientation": api.get_orientation,
                "gyroscope": api.get_gyroscope,
                "velocity": api.get_velocity,
                "location": api.get_location,
                "distance": api.get_distance,
                "speed": api.get_speed,
                "headingDegrees": api.get_heading,
            }
            for name, getter in getters.items():
                try:
                    values[name] = _plain_value(getter())
                except (AttributeError, KeyError, RuntimeError, TimeoutError, ValueError):
                    continue
            if toy is not None:
                try:
                    values["powerState"] = _plain_value(toy.get_power_state())
                except (AttributeError, RuntimeError, TimeoutError, ValueError):
                    pass
            return values

        values = await asyncio.to_thread(collect)
        self._sequence += 1
        return SpheroSensorSnapshot.from_values(self._sequence, values)


def _validate_rgb(red: int, green: int, blue: int) -> None:
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (red, green, blue)):
        raise ValueError("RGB channels must be integers")
    if any(value < 0 or value > 255 for value in (red, green, blue)):
        raise ValueError("RGB channels must be between 0 and 255")


def _plain_value(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if hasattr(value, "_asdict"):
        return _plain_value(value._asdict())
    if isinstance(value, (list, tuple)):
        return [_plain_value(item) for item in value]
    return str(value)[:100]
