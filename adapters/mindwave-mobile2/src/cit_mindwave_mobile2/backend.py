"""MindWave backend boundary and supervised Brain2Devices worker."""

from __future__ import annotations

import asyncio
import json
import math
import os
import subprocess
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.error import URLError
from urllib.request import urlopen

from cit_integration_sdk import ExternalSourceCheckoutError, verify_external_git_checkout

from .contract import BRAIN2DEVICES_REVISION


class MindWaveBackendError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MindWaveEvent:
    kind: str
    attention: int | None = None
    meditation: int | None = None
    signal_quality: float | None = None
    blink_strength: int | None = None
    connected: bool | None = None
    message: str | None = None


class MindWaveBackend(Protocol):
    async def start(self) -> None: ...

    async def next_event(self) -> MindWaveEvent: ...

    async def close(self) -> None: ...


class SimulatedMindWaveBackend:
    def __init__(self, *, sample_interval_seconds: float = 0.5) -> None:
        self._sample_interval = sample_interval_seconds
        self._started_at = 0.0
        self._connected = False

    async def start(self) -> None:
        self._started_at = time.monotonic()
        self._connected = True

    async def next_event(self) -> MindWaveEvent:
        if not self._connected:
            raise MindWaveBackendError("Simulated MindWave is not connected")
        await asyncio.sleep(self._sample_interval)
        phase = time.monotonic() - self._started_at
        return MindWaveEvent(
            kind="reading",
            attention=50 + round(18 * math.sin(phase / 2.2)),
            meditation=50 + round(18 * math.cos(phase / 2.8)),
            signal_quality=96.0,
        )

    async def close(self) -> None:
        self._connected = False


class Brain2DevicesApiMindWaveBackend:
    """Read-only semantic projection of a running Brain2Devices headset."""

    def __init__(
        self,
        *,
        origin: str = "http://127.0.0.1:8765",
        sample_interval_seconds: float = 0.5,
    ) -> None:
        if origin != "http://127.0.0.1:8765":
            raise ValueError("Brain2Devices API mode is restricted to loopback")
        if sample_interval_seconds < 0.2:
            raise ValueError("MindWave API sampling interval must be at least 0.2 seconds")
        self._origin = origin
        self._sample_interval = sample_interval_seconds
        self._connected = False
        self._last_blink_count = 0

    async def start(self) -> None:
        state = await asyncio.to_thread(self._state)
        headset = state.get("headset")
        if not isinstance(headset, dict) or headset.get("connection") != "connected":
            raise MindWaveBackendError("Brain2Devices MindWave is not connected")
        blink = self._blink(headset)
        self._last_blink_count = blink[0] if blink is not None else 0
        self._connected = True

    async def next_event(self) -> MindWaveEvent:
        if not self._connected:
            raise MindWaveBackendError("Brain2Devices MindWave is not connected")
        await asyncio.sleep(self._sample_interval)
        state = await asyncio.to_thread(self._state)
        headset = state.get("headset")
        if not isinstance(headset, dict):
            raise MindWaveBackendError("Brain2Devices headset state is unavailable")
        connected = headset.get("connection") == "connected"
        if not connected:
            self._connected = False
            return MindWaveEvent(
                kind="status",
                connected=False,
                message="Brain2Devices reports the MindWave disconnected",
            )
        blink = self._blink(headset)
        if blink is not None:
            blink_count, blink_strength = blink
            if blink_count < self._last_blink_count:
                self._last_blink_count = blink_count
            elif blink_count > self._last_blink_count:
                self._last_blink_count = blink_count
                return MindWaveEvent(kind="blink", blink_strength=blink_strength)
        attention = headset.get("attention")
        meditation = headset.get("meditation")
        quality = headset.get("signal_quality")
        if (
            isinstance(attention, bool)
            or not isinstance(attention, int)
            or isinstance(meditation, bool)
            or not isinstance(meditation, int)
            or isinstance(quality, bool)
            or not isinstance(quality, (int, float))
        ):
            return MindWaveEvent(
                kind="status",
                connected=True,
                message="Waiting for a fresh MindWave semantic reading",
            )
        return MindWaveEvent(
            kind="reading",
            attention=attention,
            meditation=meditation,
            signal_quality=float(quality),
        )

    async def close(self) -> None:
        self._connected = False

    @staticmethod
    def _blink(headset: dict[str, object]) -> tuple[int, int] | None:
        blink = headset.get("blink")
        if not isinstance(blink, dict):
            return None
        count = blink.get("count")
        strength = blink.get("strength")
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            or isinstance(strength, bool)
            or not isinstance(strength, int)
            or not 0 <= strength <= 255
        ):
            return None
        return count, strength

    def _state(self) -> dict[str, object]:
        try:
            with urlopen(f"{self._origin}/api/state", timeout=5) as response:
                raw = response.read(262_144)
            value: object = json.loads(raw.decode("utf-8"))
        except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MindWaveBackendError("Brain2Devices loopback service is unavailable") from error
        if not isinstance(value, dict):
            raise MindWaveBackendError("Brain2Devices state must be an object")
        return value


@dataclass(frozen=True, slots=True)
class Brain2DevicesMindWaveConfiguration:
    repository: Path
    python_executable: Path
    attempts: int = 3
    timeout_seconds: int = 15


def verify_brain2devices_checkout(repository: Path) -> None:
    try:
        verify_external_git_checkout(
            repository,
            expected_revision=BRAIN2DEVICES_REVISION,
            required_path="src/brain2devices/hardware/mindwave.py",
            source_name="Brain2Devices",
        )
    except ExternalSourceCheckoutError as error:
        raise MindWaveBackendError(str(error)) from error


class Brain2DevicesMindWaveProcess:
    """One process owns one Brain2Devices ``HeadsetClient`` and no drone."""

    def __init__(self, configuration: Brain2DevicesMindWaveConfiguration) -> None:
        self.configuration = configuration
        self._process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._diagnostics: deque[str] = deque(maxlen=20)
        self._pending: deque[MindWaveEvent] = deque()

    async def start(self) -> None:
        verify_brain2devices_checkout(self.configuration.repository)
        if not self.configuration.python_executable.is_file():
            raise MindWaveBackendError(
                f"Brain2Devices Python was not found: {self.configuration.python_executable}"
            )
        self._process = await asyncio.create_subprocess_exec(
            str(self.configuration.python_executable.resolve()),
            str(Path(__file__).with_name("vendor_worker.py").resolve()),
            "--repository",
            str(self.configuration.repository.resolve()),
            "--attempts",
            str(self.configuration.attempts),
            "--timeout-seconds",
            str(self.configuration.timeout_seconds),
            cwd=str(self.configuration.repository.resolve()),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        deadline = asyncio.get_running_loop().time() + self.configuration.timeout_seconds * 4
        while asyncio.get_running_loop().time() < deadline:
            value = await self._read_frame(timeout_seconds=5)
            if value.get("type") == "ready":
                return
            event = self._event_from_frame(value)
            if event is not None:
                self._pending.append(event)
        raise MindWaveBackendError("MindWave worker did not become ready")

    async def next_event(self) -> MindWaveEvent:
        if self._pending:
            return self._pending.popleft()
        while True:
            value = await self._read_frame(timeout_seconds=10)
            if value.get("type") == "fatal":
                raise MindWaveBackendError(str(value.get("message", "MindWave worker failed")))
            event = self._event_from_frame(value)
            if event is not None:
                return event

    async def close(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            if process.returncode is None and process.stdin is not None:
                process.stdin.write(b'{"operation":"shutdown"}\n')
                await process.stdin.drain()
            if process.returncode is None:
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    process.terminate()
                    await process.wait()
        finally:
            if self._stderr_task is not None:
                await self._stderr_task
            self._stderr_task = None
            self._process = None

    async def _read_frame(self, *, timeout_seconds: float) -> dict[str, object]:
        process = self._process
        if process is None or process.stdout is None:
            raise MindWaveBackendError("MindWave worker is not running")
        try:
            raw = await asyncio.wait_for(process.stdout.readline(), timeout=timeout_seconds)
        except TimeoutError as error:
            raise MindWaveBackendError("MindWave worker stopped reporting") from error
        if not raw:
            diagnostic = next(reversed(self._diagnostics), "no diagnostic was reported")
            raise MindWaveBackendError(
                f"MindWave worker exited with code {process.returncode}: {diagnostic}"
            )
        try:
            value: object = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MindWaveBackendError("MindWave worker returned invalid JSON") from error
        if not isinstance(value, dict):
            raise MindWaveBackendError("MindWave worker frame must be an object")
        return value

    @staticmethod
    def _event_from_frame(value: dict[str, object]) -> MindWaveEvent | None:
        kind = value.get("type")
        if kind == "reading":
            return MindWaveEvent(
                kind="reading",
                attention=Brain2DevicesMindWaveProcess._integer(value, "attention"),
                meditation=Brain2DevicesMindWaveProcess._integer(value, "meditation"),
                signal_quality=Brain2DevicesMindWaveProcess._number(value, "signalQuality"),
            )
        if kind == "blink":
            return MindWaveEvent(
                kind="blink",
                blink_strength=Brain2DevicesMindWaveProcess._integer(value, "strength"),
            )
        if kind == "status":
            return MindWaveEvent(
                kind="status",
                connected=bool(value.get("connected")),
                message=str(value.get("message", ""))[:500],
            )
        return None

    @staticmethod
    def _number(value: dict[str, object], field: str) -> float:
        raw = value.get(field)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise MindWaveBackendError(f"MindWave worker field {field!r} must be numeric")
        return float(raw)

    @staticmethod
    def _integer(value: dict[str, object], field: str) -> int:
        number = Brain2DevicesMindWaveProcess._number(value, field)
        if not number.is_integer():
            raise MindWaveBackendError(f"MindWave worker field {field!r} must be an integer")
        return int(number)

    async def _drain_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        while raw := await process.stderr.readline():
            self._diagnostics.append(raw.decode(errors="replace").strip()[:500])
