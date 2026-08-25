"""Supervised subprocess boundaries for the Python 3.8 upstream integration."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import math
import os
import subprocess
from collections import deque
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from .contract import UPSTREAM_REVISION


class VendorProcessError(RuntimeError):
    """The external worker was unavailable or rejected a bounded request."""


@dataclass(frozen=True, slots=True)
class VendorConfiguration:
    repository: Path
    python_executable: Path
    robot_mode: str = "dry-run"
    connection: str = "sta"
    protocol: str = "tcp"
    robot_ip: str | None = None
    local_ip: str | None = None
    serial_number: str | None = None
    bridge_dll: Path | None = None
    leap_stop_file: Path | None = None
    preferred_hand: str = "right"
    max_speed: float = 0.35
    max_yaw_degrees: float = 35.0
    invert_strafe: bool = False
    invert_yaw: bool = False


@dataclass(frozen=True, slots=True)
class LeapHandSample:
    hand_id: int
    handedness: str
    visible_time_seconds: float
    palm_x_mm: float
    palm_y_mm: float
    palm_z_mm: float
    velocity_x_mm_per_second: float
    velocity_y_mm_per_second: float
    velocity_z_mm_per_second: float
    direction_x: float
    direction_y: float
    direction_z: float
    normal_x: float
    normal_y: float
    normal_z: float
    pinch_strength: float
    grab_strength: float
    pinch_distance_mm: float
    yaw_degrees: float


@dataclass(frozen=True, slots=True)
class GestureSignal:
    sequence: int
    monotonic_nanoseconds: int
    state: str
    reason: str
    confidence: float
    forward_meters_per_second: float
    right_meters_per_second: float
    clockwise_radians_per_second: float
    tracking: bool
    hand: LeapHandSample | None = None
    sensor_frame_id: int | None = None
    sensor_frame_rate_hz: float | None = None
    total_hand_count: int = 0
    service_connected: bool = False
    device_present: bool = False


def gesture_event_payload(signal: GestureSignal) -> dict[str, object]:
    """Build the single canonical Leap payload used by both bridge variants."""

    hand = signal.hand
    return {
        "forwardMetersPerSecond": signal.forward_meters_per_second,
        "rightMetersPerSecond": signal.right_meters_per_second,
        "clockwiseRadiansPerSecond": signal.clockwise_radians_per_second,
        "state": signal.state,
        "reason": signal.reason,
        "tracking": signal.tracking,
        "vendorSequence": signal.sequence,
        "sensorFrameId": signal.sensor_frame_id,
        "sensorFrameRateHertz": signal.sensor_frame_rate_hz,
        "totalHandCount": signal.total_hand_count,
        "serviceConnected": signal.service_connected,
        "devicePresent": signal.device_present,
        "hand": (
            None
            if hand is None
            else {
                "handId": hand.hand_id,
                "handedness": hand.handedness,
                "visibleTimeSeconds": hand.visible_time_seconds,
                "palmMillimeters": {
                    "x": hand.palm_x_mm,
                    "y": hand.palm_y_mm,
                    "z": hand.palm_z_mm,
                },
                "velocityMillimetersPerSecond": {
                    "x": hand.velocity_x_mm_per_second,
                    "y": hand.velocity_y_mm_per_second,
                    "z": hand.velocity_z_mm_per_second,
                },
                "direction": {
                    "x": hand.direction_x,
                    "y": hand.direction_y,
                    "z": hand.direction_z,
                },
                "palmNormal": {
                    "x": hand.normal_x,
                    "y": hand.normal_y,
                    "z": hand.normal_z,
                },
                "pinchStrength": hand.pinch_strength,
                "grabStrength": hand.grab_strength,
                "pinchDistanceMillimeters": hand.pinch_distance_mm,
                "yawDegrees": hand.yaw_degrees,
            }
        ),
    }


class RobotBackend(Protocol):
    async def start(self) -> None: ...

    async def set_velocity(
        self,
        *,
        forward: float,
        right: float,
        clockwise: float,
        idempotency_key: str,
    ) -> Mapping[str, object]: ...

    async def set_light(
        self,
        *,
        red: int,
        green: int,
        blue: int,
        idempotency_key: str,
    ) -> Mapping[str, object]: ...

    async def stop(self, *, reason: str) -> None: ...

    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RobotCameraFrame:
    sequence: int
    jpeg: bytes


def upstream_revision(repository: Path) -> str:
    """Resolve the exact checkout without importing any upstream code."""

    completed = subprocess.run(
        ["git", "-C", str(repository.resolve()), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if completed.returncode != 0:
        diagnostic = completed.stderr.strip() or "git rev-parse failed"
        raise VendorProcessError(diagnostic[:500])
    return completed.stdout.strip()


def verify_upstream_checkout(repository: Path) -> None:
    package = repository.resolve() / "robomaster_gesture" / "__init__.py"
    if not package.is_file():
        raise VendorProcessError(f"Upstream package was not found at {repository.resolve()}")
    revision = upstream_revision(repository)
    if revision != UPSTREAM_REVISION:
        raise VendorProcessError(
            f"Upstream checkout is {revision}, but this adapter is characterized for "
            f"{UPSTREAM_REVISION}"
        )


def verify_vendor_configuration(configuration: VendorConfiguration, *, leap: bool) -> None:
    verify_upstream_checkout(configuration.repository)
    if not configuration.python_executable.is_file():
        raise VendorProcessError(
            f"External Python was not found: {configuration.python_executable.resolve()}"
        )
    if configuration.robot_mode not in {"dry-run", "sdk", "s1-app"}:
        raise VendorProcessError(f"Unsupported robot mode {configuration.robot_mode!r}")
    if configuration.connection not in {"ap", "sta", "rndis"}:
        raise VendorProcessError(f"Unsupported DJI connection {configuration.connection!r}")
    if configuration.protocol not in {"tcp", "udp"}:
        raise VendorProcessError(f"Unsupported DJI protocol {configuration.protocol!r}")
    if not 0.05 <= configuration.max_speed <= 0.35:
        raise VendorProcessError("Maximum speed must be between 0.05 and 0.35 m/s")
    if not 5.0 <= configuration.max_yaw_degrees <= 35.0:
        raise VendorProcessError("Maximum yaw must be between 5 and 35 degrees/s")
    if leap:
        if configuration.bridge_dll is None or not configuration.bridge_dll.is_file():
            raise VendorProcessError(f"Leap bridge DLL was not found: {configuration.bridge_dll}")
        if configuration.leap_stop_file is None:
            raise VendorProcessError("Leap mode requires an exact local stop-file path")


def _worker_path() -> Path:
    return Path(__file__).with_name("vendor_worker.py").resolve()


def _creation_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0


class VendorRobotProcess:
    """One request/response JSON-lines process owning the robot connection."""

    def __init__(self, configuration: VendorConfiguration) -> None:
        self.configuration = configuration
        self._process: asyncio.subprocess.Process | None = None
        self._request_lock = asyncio.Lock()
        self._stderr_task: asyncio.Task[None] | None = None
        self._diagnostics: deque[str] = deque(maxlen=20)

    @property
    def diagnostics(self) -> tuple[str, ...]:
        return tuple(self._diagnostics)

    async def start(self) -> None:
        if self._process is not None and self._process.returncode is None:
            return
        verify_vendor_configuration(self.configuration, leap=False)
        arguments = [
            str(self.configuration.python_executable.resolve()),
            str(_worker_path()),
            "robot",
            "--repository",
            str(self.configuration.repository.resolve()),
            "--robot-mode",
            self.configuration.robot_mode,
            "--connection",
            self.configuration.connection,
            "--protocol",
            self.configuration.protocol,
            "--max-speed",
            str(self.configuration.max_speed),
            "--max-yaw",
            str(self.configuration.max_yaw_degrees),
        ]
        for flag, value in (
            ("--robot-ip", self.configuration.robot_ip),
            ("--local-ip", self.configuration.local_ip),
            ("--serial-number", self.configuration.serial_number),
        ):
            if value:
                arguments.extend((flag, value))
        self._process = await asyncio.create_subprocess_exec(
            *arguments,
            cwd=str(self.configuration.repository.resolve()),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=_creation_flags(),
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        await self._request("connect", deadline_seconds=30.0)

    async def set_velocity(
        self,
        *,
        forward: float,
        right: float,
        clockwise: float,
        idempotency_key: str,
    ) -> Mapping[str, object]:
        return await self._request(
            "set_velocity",
            payload={
                "forwardMetersPerSecond": forward,
                "rightMetersPerSecond": right,
                "clockwiseRadiansPerSecond": clockwise,
                "idempotencyKey": idempotency_key,
            },
            deadline_seconds=2.0,
        )

    async def set_light(
        self,
        *,
        red: int,
        green: int,
        blue: int,
        idempotency_key: str,
    ) -> Mapping[str, object]:
        return await self._request(
            "set_light",
            payload={
                "red": red,
                "green": green,
                "blue": blue,
                "idempotencyKey": idempotency_key,
            },
            deadline_seconds=2.0,
        )

    async def stop(self, *, reason: str) -> None:
        process = self._process
        if process is None or process.returncode is not None:
            return
        try:
            await self._request(
                "stop",
                payload={"reason": reason},
                deadline_seconds=1.0,
            )
        except VendorProcessError:
            return

    async def start_camera(self) -> None:
        await self._request("camera_start", deadline_seconds=10.0)

    async def camera_frame(self, *, after_sequence: int) -> RobotCameraFrame | None:
        value = await self._request(
            "camera_frame",
            payload={"afterSequence": after_sequence},
            deadline_seconds=1.0,
        )
        if value.get("ready") is not True:
            return None
        try:
            sequence = value["sequence"]
            if not isinstance(sequence, int) or isinstance(sequence, bool):
                raise ValueError("camera frame sequence is invalid")
            encoded = value["jpegBase64"]
            if not isinstance(encoded, str) or len(encoded) > 1_500_000:
                raise ValueError("camera frame encoding is invalid")
            jpeg = base64.b64decode(encoded, validate=True)
        except (KeyError, TypeError, ValueError, binascii.Error) as error:
            raise VendorProcessError("Robot worker returned an invalid camera frame") from error
        if sequence <= after_sequence:
            return None
        if not 32 <= len(jpeg) <= 1_048_576:
            raise VendorProcessError("Robot worker camera frame is outside Fabric limits")
        if not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
            raise VendorProcessError("Robot worker camera payload is not a complete JPEG")
        return RobotCameraFrame(sequence=sequence, jpeg=jpeg)

    async def stop_camera(self) -> None:
        process = self._process
        if process is None or process.returncode is not None:
            return
        try:
            await self._request("camera_stop", deadline_seconds=2.0)
        except VendorProcessError:
            return

    async def close(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            if process.returncode is None:
                try:
                    await self._request("shutdown", deadline_seconds=2.0)
                except VendorProcessError:
                    pass
            if process.returncode is None:
                try:
                    await asyncio.wait_for(process.wait(), timeout=2.0)
                except TimeoutError:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=1.0)
                    except TimeoutError:
                        process.kill()
                        await process.wait()
        finally:
            if self._stderr_task is not None:
                await self._stderr_task
            self._stderr_task = None
            self._process = None

    async def _request(
        self,
        operation: str,
        *,
        payload: Mapping[str, object] | None = None,
        deadline_seconds: float,
    ) -> Mapping[str, object]:
        process = self._process
        if process is None or process.stdin is None or process.stdout is None:
            raise VendorProcessError("Robot worker is not running")
        if process.returncode is not None:
            raise VendorProcessError(self._exit_message(process.returncode))
        request_id = str(uuid4())
        request: dict[str, object] = {"requestId": request_id, "operation": operation}
        request.update(payload or {})
        async with self._request_lock:
            process.stdin.write((json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8"))
            await process.stdin.drain()
            try:
                raw = await asyncio.wait_for(
                    process.stdout.readline(),
                    timeout=deadline_seconds,
                )
            except TimeoutError as error:
                raise VendorProcessError(
                    f"Robot worker timed out during {operation}; its local watchdog stops motion"
                ) from error
        if not raw:
            raise VendorProcessError(self._exit_message(process.returncode))
        try:
            value: object = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise VendorProcessError("Robot worker returned an invalid JSON frame") from error
        if not isinstance(value, dict) or value.get("requestId") != request_id:
            raise VendorProcessError("Robot worker response identity did not match its request")
        if value.get("ok") is not True:
            message = value.get("message")
            raise VendorProcessError(
                str(message)[:500] if message else "Robot worker rejected the request"
            )
        return value

    async def _drain_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        while raw := await process.stderr.readline():
            self._diagnostics.append(raw.decode("utf-8", errors="replace").strip()[:500])

    def _exit_message(self, return_code: int | None) -> str:
        diagnostic = next(reversed(self._diagnostics), "no diagnostic was reported")
        return f"Robot worker exited with code {return_code}: {diagnostic}"


class VendorLeapProcess:
    """Read-only semantic-event process; it never imports or owns a robot."""

    def __init__(self, configuration: VendorConfiguration) -> None:
        self.configuration = configuration
        self._process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._diagnostics: deque[str] = deque(maxlen=20)

    @property
    def diagnostics(self) -> tuple[str, ...]:
        return tuple(self._diagnostics)

    async def events(self) -> AsyncIterator[GestureSignal]:
        await self._start()
        process = self._process
        if process is None or process.stdout is None:
            raise VendorProcessError("Leap worker is not running")
        ready = await self._read_frame(deadline_seconds=10.0)
        if ready.get("type") != "ready":
            raise VendorProcessError(str(ready.get("message", "Leap worker did not become ready")))
        while process.returncode is None:
            frame = await self._read_frame(deadline_seconds=2.0)
            if frame.get("type") == "fatal":
                raise VendorProcessError(str(frame.get("message", "Leap worker failed")))
            if frame.get("type") != "gesture":
                continue
            try:
                hand = _leap_hand_from_frame(frame.get("hand"))
                frame_rate = frame.get("sensorFrameRateHertz")
                yield GestureSignal(
                    sequence=int(frame["sequence"]),
                    monotonic_nanoseconds=int(frame["monotonicNanoseconds"]),
                    state=str(frame["state"]),
                    reason=str(frame["reason"]),
                    confidence=float(frame["confidence"]),
                    forward_meters_per_second=float(frame["forwardMetersPerSecond"]),
                    right_meters_per_second=float(frame["rightMetersPerSecond"]),
                    clockwise_radians_per_second=float(frame["clockwiseRadiansPerSecond"]),
                    tracking=bool(frame["tracking"]),
                    hand=hand,
                    sensor_frame_id=_optional_int(frame.get("sensorFrameId")),
                    sensor_frame_rate_hz=(
                        None if frame_rate is None else _finite_float(frame_rate)
                    ),
                    total_hand_count=int(frame.get("totalHandCount", 0)),
                    service_connected=bool(frame.get("serviceConnected", False)),
                    device_present=bool(frame.get("devicePresent", False)),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise VendorProcessError("Leap worker emitted an invalid gesture frame") from error

    async def close(self) -> None:
        process = self._process
        if process is None:
            return
        stop_file = self.configuration.leap_stop_file
        if stop_file is not None:
            stop_file.parent.mkdir(parents=True, exist_ok=True)
            stop_file.write_text("stop\n", encoding="ascii")
        try:
            if process.returncode is None:
                try:
                    await asyncio.wait_for(process.wait(), timeout=2.0)
                except TimeoutError:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=1.0)
                    except TimeoutError:
                        process.kill()
                        await process.wait()
        finally:
            if self._stderr_task is not None:
                await self._stderr_task
            self._stderr_task = None
            self._process = None

    async def _start(self) -> None:
        if self._process is not None and self._process.returncode is None:
            return
        verify_vendor_configuration(self.configuration, leap=True)
        bridge_dll = self.configuration.bridge_dll
        stop_file = self.configuration.leap_stop_file
        if bridge_dll is None or stop_file is None:
            raise VendorProcessError("Leap configuration is incomplete")
        stop_file.parent.mkdir(parents=True, exist_ok=True)
        stop_file.unlink(missing_ok=True)
        arguments = [
            str(self.configuration.python_executable.resolve()),
            str(_worker_path()),
            "leap",
            "--repository",
            str(self.configuration.repository.resolve()),
            "--bridge-dll",
            str(bridge_dll.resolve()),
            "--stop-file",
            str(stop_file.resolve()),
            "--hand",
            self.configuration.preferred_hand,
            "--max-speed",
            str(self.configuration.max_speed),
            "--max-yaw",
            str(self.configuration.max_yaw_degrees),
        ]
        if self.configuration.invert_strafe:
            arguments.append("--invert-strafe")
        if self.configuration.invert_yaw:
            arguments.append("--invert-yaw")
        self._process = await asyncio.create_subprocess_exec(
            *arguments,
            cwd=str(self.configuration.repository.resolve()),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=_creation_flags(),
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def _read_frame(self, *, deadline_seconds: float) -> dict[str, Any]:
        process = self._process
        if process is None or process.stdout is None:
            raise VendorProcessError("Leap worker is not running")
        try:
            raw = await asyncio.wait_for(
                process.stdout.readline(),
                timeout=deadline_seconds,
            )
        except TimeoutError as error:
            raise VendorProcessError("Leap worker stopped reporting health") from error
        if not raw:
            diagnostic = next(reversed(self._diagnostics), "no diagnostic was reported")
            raise VendorProcessError(
                f"Leap worker exited with code {process.returncode}: {diagnostic}"
            )
        try:
            value: object = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise VendorProcessError("Leap worker returned an invalid JSON frame") from error
        if not isinstance(value, dict):
            raise VendorProcessError("Leap worker frame must be an object")
        return value

    async def _drain_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        while raw := await process.stderr.readline():
            self._diagnostics.append(raw.decode("utf-8", errors="replace").strip()[:500])


def demo_gesture_signals() -> tuple[GestureSignal, ...]:
    """A bounded, software-only pulse followed by stop for regression testing."""

    return (
        GestureSignal(
            sequence=1,
            monotonic_nanoseconds=1,
            state="DRIVING",
            reason="simulated bounded forward gesture",
            confidence=1.0,
            forward_meters_per_second=0.10,
            right_meters_per_second=0.0,
            clockwise_radians_per_second=0.0,
            tracking=True,
            hand=_demo_hand(pinch_strength=0.92),
            sensor_frame_id=1,
            sensor_frame_rate_hz=60.0,
            total_hand_count=1,
            service_connected=True,
            device_present=True,
        ),
        GestureSignal(
            sequence=2,
            monotonic_nanoseconds=2,
            state="WAITING",
            reason="simulated pinch release - stopped",
            confidence=1.0,
            forward_meters_per_second=0.0,
            right_meters_per_second=0.0,
            clockwise_radians_per_second=0.0,
            tracking=True,
            hand=_demo_hand(pinch_strength=0.10),
            sensor_frame_id=2,
            sensor_frame_rate_hz=60.0,
            total_hand_count=1,
            service_connected=True,
            device_present=True,
        ),
    )


def demo_hand_preview_signal(sequence: int) -> GestureSignal:
    """Keep the simulator's hand display live without requesting movement."""

    if sequence < 3:
        raise ValueError("Demo preview sequences must follow the bounded pulse")
    stopped = demo_gesture_signals()[-1]
    return replace(
        stopped,
        sequence=sequence,
        monotonic_nanoseconds=sequence * 1_000_000_000,
        reason="simulated live hand preview - stopped",
        sensor_frame_id=sequence,
    )


def _demo_hand(*, pinch_strength: float) -> LeapHandSample:
    return LeapHandSample(
        hand_id=1,
        handedness="right",
        visible_time_seconds=1.0,
        palm_x_mm=0.0,
        palm_y_mm=180.0,
        palm_z_mm=-120.0,
        velocity_x_mm_per_second=0.0,
        velocity_y_mm_per_second=0.0,
        velocity_z_mm_per_second=0.0,
        direction_x=0.0,
        direction_y=0.0,
        direction_z=-1.0,
        normal_x=0.0,
        normal_y=1.0,
        normal_z=0.0,
        pinch_strength=pinch_strength,
        grab_strength=0.15,
        pinch_distance_mm=20.0 if pinch_strength >= 0.6 else 55.0,
        yaw_degrees=0.0,
    )


def _finite_float(value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("numeric Leap value must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Leap value must be finite")
    return result


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("Leap frame id must be an integer")
    return value


def _leap_hand_from_frame(value: object) -> LeapHandSample | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Leap hand must be an object")

    def vector(name: str) -> tuple[float, float, float]:
        candidate = value.get(name)
        if not isinstance(candidate, dict):
            raise ValueError(f"Leap hand {name} must be an object")
        return (
            _finite_float(candidate.get("x")),
            _finite_float(candidate.get("y")),
            _finite_float(candidate.get("z")),
        )

    palm = vector("palmMillimeters")
    velocity = vector("velocityMillimetersPerSecond")
    direction = vector("direction")
    normal = vector("palmNormal")
    handedness = str(value.get("handedness", "")).casefold()
    if handedness not in {"left", "right"}:
        raise ValueError("Leap handedness must be left or right")
    return LeapHandSample(
        hand_id=int(value["handId"]),
        handedness=handedness,
        visible_time_seconds=_finite_float(value["visibleTimeSeconds"]),
        palm_x_mm=palm[0],
        palm_y_mm=palm[1],
        palm_z_mm=palm[2],
        velocity_x_mm_per_second=velocity[0],
        velocity_y_mm_per_second=velocity[1],
        velocity_z_mm_per_second=velocity[2],
        direction_x=direction[0],
        direction_y=direction[1],
        direction_z=direction[2],
        normal_x=normal[0],
        normal_y=normal[1],
        normal_z=normal[2],
        pinch_strength=_finite_float(value["pinchStrength"]),
        grab_strength=_finite_float(value["grabStrength"]),
        pinch_distance_mm=_finite_float(value["pinchDistanceMillimeters"]),
        yaw_degrees=_finite_float(value["yawDegrees"]),
    )


def validate_velocity_parameters(parameters: Mapping[str, object]) -> tuple[float, float, float]:
    expected = {
        "forwardMetersPerSecond",
        "rightMetersPerSecond",
        "clockwiseRadiansPerSecond",
    }
    if set(parameters) != expected:
        unknown = sorted(set(parameters) ^ expected)
        raise ValueError(f"Velocity parameters differ from the canonical contract: {unknown}")

    def number(name: str, limit: float) -> float:
        raw = parameters[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"{name} must be numeric")
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
        if abs(value) > limit:
            raise ValueError(f"{name} exceeds the device-level bound")
        return value

    return (
        number("forwardMetersPerSecond", 0.35),
        number("rightMetersPerSecond", 0.35),
        number("clockwiseRadiansPerSecond", math.radians(35.0)),
    )
