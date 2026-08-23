"""Injectable BLE transport; vendor protocol stays outside the Fabric core."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, Protocol

from .discovery import scan_wonder_robots
from .models import WonderRobotModel, WonderSensorSnapshot
from .policy import (
    DASH_HEAD_PAN_MAX_DEGREES,
    DASH_HEAD_PAN_MIN_DEGREES,
    DASH_HEAD_TILT_MAX_DEGREES,
    DASH_HEAD_TILT_MIN_DEGREES,
    DASH_MAX_CLOCKWISE_RADIANS_PER_SECOND,
    DASH_MAX_FORWARD_METERS_PER_SECOND,
    WONDER_SOUND_CUE_COUNT,
)
from .protocol import (
    COMMAND_CHARACTERISTIC_UUID,
    COMMON_SENSOR_CHARACTERISTIC_UUID,
    DASH_SENSOR_CHARACTERISTIC_UUID,
    color_packets,
    decode_common_sensor,
    decode_dash_sensor,
    drive_packet,
    head_packets,
    sound_packet,
    stop_packet,
)

SensorCallback = Callable[[WonderSensorSnapshot], Coroutine[object, object, None]]


class WonderTransport(Protocol):
    @property
    def connected(self) -> bool: ...

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def stop(self) -> None: ...

    async def set_velocity(self, forward: float, right: float, clockwise: float) -> None: ...

    async def set_color(self, red: int, green: int, blue: int) -> None: ...

    async def play_cue(self, cue_index: int) -> None: ...

    async def set_head_pose(self, pan_degrees: int, tilt_degrees: int) -> None: ...

    def set_sensor_callback(self, callback: SensorCallback) -> None: ...


class FakeWonderTransport:
    def __init__(self, model: WonderRobotModel) -> None:
        self.model = model
        self._connected = False
        self._callback: SensorCallback | None = None
        self.commands: list[tuple[str, tuple[object, ...]]] = []
        self._sequence = 0

    @property
    def connected(self) -> bool:
        return self._connected

    def set_sensor_callback(self, callback: SensorCallback) -> None:
        self._callback = callback

    async def connect(self) -> None:
        self._connected = True
        await self.publish_sensor(
            {
                "model": self.model.value,
                "mainButtonPressed": False,
                "pickedUp": False,
                "simulated": True,
            }
        )

    async def disconnect(self) -> None:
        self._connected = False

    async def stop(self) -> None:
        self.commands.append(("stop", ()))

    async def set_velocity(self, forward: float, right: float, clockwise: float) -> None:
        if self.model is WonderRobotModel.DOT:
            raise ValueError("Dot has no drive motors")
        self.commands.append(("velocity", (forward, right, clockwise)))

    async def set_color(self, red: int, green: int, blue: int) -> None:
        self.commands.append(("color", (red, green, blue)))

    async def play_cue(self, cue_index: int) -> None:
        self.commands.append(("cue", (cue_index,)))

    async def set_head_pose(self, pan_degrees: int, tilt_degrees: int) -> None:
        if self.model is WonderRobotModel.DOT:
            raise ValueError("Dot has no movable head")
        self.commands.append(("head", (pan_degrees, tilt_degrees)))

    async def publish_sensor(self, values: dict[str, object]) -> None:
        self._sequence += 1
        if self._callback is not None:
            await self._callback(WonderSensorSnapshot.from_values(self._sequence, values))


class BleakWonderTransport:
    """Exact-candidate BLE connection with fail-closed command writes."""

    def __init__(
        self,
        candidate_id: str,
        model: WonderRobotModel,
        *,
        scan_timeout_seconds: float = 8,
    ) -> None:
        self.candidate_id = candidate_id
        self.model = model
        self.scan_timeout_seconds = scan_timeout_seconds
        self._client: Any = None
        self._callback: SensorCallback | None = None
        self._sensor_values: dict[str, object] = {"model": model.value}
        self._sequence = 0
        self._pending_snapshot: WonderSensorSnapshot | None = None
        self._snapshot_task: asyncio.Task[None] | None = None

    @property
    def connected(self) -> bool:
        return self._client is not None and bool(self._client.is_connected)

    def set_sensor_callback(self, callback: SensorCallback) -> None:
        self._callback = callback

    async def connect(self) -> None:
        try:
            from bleak import BleakClient
        except ImportError as error:
            raise RuntimeError("The optional Bleak hardware transport is not installed") from error
        matches = [
            item
            for item in await scan_wonder_robots(self.scan_timeout_seconds)
            if item.candidate_id == self.candidate_id and item.model is self.model
        ]
        if len(matches) != 1:
            raise RuntimeError("The exact selected Dash/Dot advertisement is no longer visible")
        candidate = matches[0]
        self._client = BleakClient(candidate.device or candidate.address)
        await self._client.connect()
        await self._client.start_notify(
            COMMON_SENSOR_CHARACTERISTIC_UUID, self._common_notification
        )
        if self.model is WonderRobotModel.DASH:
            await self._client.start_notify(
                DASH_SENSOR_CHARACTERISTIC_UUID, self._dash_notification
            )

    async def disconnect(self) -> None:
        client, self._client = self._client, None
        if client is not None and client.is_connected:
            await client.disconnect()
        if self._snapshot_task is not None:
            await asyncio.gather(self._snapshot_task, return_exceptions=True)
        self._snapshot_task = None
        self._pending_snapshot = None

    async def _write(self, packet: bytes) -> None:
        if not self.connected:
            raise RuntimeError("Dash/Dot is not connected")
        # Let Bleak select write-with/without-response from the characteristic
        # properties. Dash/Dot firmware generations do not all expose the same
        # write flag, and forcing the wrong mode makes a healthy robot fail.
        await self._client.write_gatt_char(COMMAND_CHARACTERISTIC_UUID, packet)

    async def stop(self) -> None:
        if self.model is WonderRobotModel.DASH:
            await self._write(stop_packet())

    async def set_velocity(self, forward: float, right: float, clockwise: float) -> None:
        if self.model is WonderRobotModel.DOT:
            raise ValueError("Dot has no drive motors")
        if abs(right) > 1e-9:
            raise ValueError("Dash differential drive cannot strafe")
        if (
            abs(forward) > DASH_MAX_FORWARD_METERS_PER_SECOND
            or abs(clockwise) > DASH_MAX_CLOCKWISE_RADIANS_PER_SECOND
        ):
            raise ValueError("Dash velocity exceeds the adapter classroom bounds")
        if abs(forward) > 1e-9 and abs(clockwise) > 1e-9:
            raise ValueError("Dash cannot combine linear and angular velocity")
        await self._write(
            drive_packet(
                round(forward / DASH_MAX_FORWARD_METERS_PER_SECOND * 200),
                round(clockwise / DASH_MAX_CLOCKWISE_RADIANS_PER_SECOND * 200),
            )
        )

    async def set_color(self, red: int, green: int, blue: int) -> None:
        if any(value < 0 or value > 255 for value in (red, green, blue)):
            raise ValueError("RGB channels must be between 0 and 255")
        for packet in color_packets(red, green, blue):
            await self._write(packet)

    async def play_cue(self, cue_index: int) -> None:
        if cue_index not in range(WONDER_SOUND_CUE_COUNT):
            raise ValueError("Only the three fixed classroom sound cues are allowed")
        await self._write(sound_packet(cue_index))

    async def set_head_pose(self, pan_degrees: int, tilt_degrees: int) -> None:
        if self.model is WonderRobotModel.DOT:
            raise ValueError("Dot has no movable head")
        if not (
            DASH_HEAD_PAN_MIN_DEGREES <= pan_degrees <= DASH_HEAD_PAN_MAX_DEGREES
            and DASH_HEAD_TILT_MIN_DEGREES <= tilt_degrees <= DASH_HEAD_TILT_MAX_DEGREES
        ):
            raise ValueError("Dash head pose exceeds the adapter bounds")
        for packet in head_packets(pan_degrees, tilt_degrees):
            await self._write(packet)

    def _common_notification(self, _sender: object, value: bytearray) -> None:
        try:
            self._sensor_values.update(decode_common_sensor(bytes(value)))
        except ValueError:
            return
        self._schedule_snapshot()

    def _dash_notification(self, _sender: object, value: bytearray) -> None:
        try:
            self._sensor_values.update(decode_dash_sensor(bytes(value), self._sensor_values))
        except ValueError:
            return
        self._schedule_snapshot()

    def _schedule_snapshot(self) -> None:
        self._sequence += 1
        if self._callback is not None:
            self._pending_snapshot = WonderSensorSnapshot.from_values(
                self._sequence, self._sensor_values
            )
            if self._snapshot_task is None or self._snapshot_task.done():
                self._snapshot_task = asyncio.create_task(self._publish_pending_snapshots())

    async def _publish_pending_snapshots(self) -> None:
        while self._pending_snapshot is not None and self._callback is not None:
            snapshot, self._pending_snapshot = self._pending_snapshot, None
            await self._callback(snapshot)
