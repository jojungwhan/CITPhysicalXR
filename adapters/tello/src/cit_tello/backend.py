"""Tello backend boundary and supervised Brain2Devices worker."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from cit_integration_sdk import ExternalSourceCheckoutError, verify_external_git_checkout

from .contract import BRAIN2DEVICES_REVISION


class TelloBackendError(RuntimeError):
    pass


class TelloBackend(Protocol):
    async def start(self) -> Mapping[str, object]: ...

    async def telemetry(self) -> Mapping[str, object]: ...

    async def land(self, *, reason: str) -> Mapping[str, object]: ...

    async def emergency_stop(self, *, reason: str) -> Mapping[str, object]: ...

    async def close(self) -> None: ...


class SimulatedTelloBackend:
    def __init__(self) -> None:
        self.connected = False
        self.flight_state = "landed"
        self.command_log: list[str] = []

    async def start(self) -> Mapping[str, object]:
        self.connected = True
        self.command_log.append("connect")
        return await self.telemetry()

    async def telemetry(self) -> Mapping[str, object]:
        if not self.connected:
            raise TelloBackendError("Simulated Tello is not connected")
        return {
            "batteryPercent": 87,
            "heightCentimeters": 0 if self.flight_state == "landed" else 80,
            "temperatureCelsius": 31,
            "flightState": self.flight_state,
            "source": "simulation",
        }

    async def land(self, *, reason: str) -> Mapping[str, object]:
        if not self.connected:
            raise TelloBackendError("Simulated Tello is not connected")
        self.flight_state = "landed"
        self.command_log.append(f"land:{reason}")
        return {"landed": True, "reason": reason}

    async def emergency_stop(self, *, reason: str) -> Mapping[str, object]:
        if not self.connected:
            raise TelloBackendError("Simulated Tello is not connected")
        self.flight_state = "landed"
        self.command_log.append(f"emergency_stop:{reason}")
        return {"emergencyStopped": True, "reason": reason}

    async def close(self) -> None:
        self.connected = False


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


class Brain2DevicesApiTelloBackend:
    """Adapter-specific view of one already connected Brain2Devices fleet node."""

    def __init__(
        self,
        *,
        origin: str = "http://127.0.0.1:8765",
        drone_id: str = "primary",
    ) -> None:
        if origin != "http://127.0.0.1:8765":
            raise ValueError("Brain2Devices API mode is restricted to loopback")
        if not drone_id or len(drone_id) > 128:
            raise ValueError("Brain2Devices drone ID is invalid")
        self._origin = origin
        self._drone_id = drone_id
        self._token: str | None = None

    async def start(self) -> Mapping[str, object]:
        self._token = await asyncio.to_thread(self._read_token)
        telemetry = await self.telemetry()
        if telemetry.get("connection") != "connected":
            raise TelloBackendError(f"Brain2Devices drone {self._drone_id!r} is not connected")
        return telemetry

    async def telemetry(self) -> Mapping[str, object]:
        state = await asyncio.to_thread(self._request, "/api/state", None)
        fleet = state.get("fleet")
        if not isinstance(fleet, dict) or not isinstance(fleet.get("drones"), list):
            raise TelloBackendError("Brain2Devices fleet state is unavailable")
        drone = next(
            (
                item
                for item in fleet["drones"]
                if isinstance(item, dict) and item.get("id") == self._drone_id
            ),
            None,
        )
        if not isinstance(drone, dict):
            raise TelloBackendError(f"Brain2Devices no longer reports drone {self._drone_id!r}")
        telemetry = drone.get("telemetry")
        if not isinstance(telemetry, dict):
            telemetry = {}
        return {
            "batteryPercent": telemetry.get("battery_percent"),
            "heightCentimeters": telemetry.get("height_cm"),
            "temperatureCelsius": telemetry.get("temperature_c"),
            "flightState": drone.get("flight", "unknown"),
            "connection": drone.get("connection", "unknown"),
            "brain2devicesDroneId": self._drone_id,
            "source": "brain2devices-api",
        }

    async def land(self, *, reason: str) -> Mapping[str, object]:
        await asyncio.to_thread(
            self._request,
            "/api/fleet/command",
            {"action": "land", "drone_ids": [self._drone_id], "confirmed": True},
        )
        return {"landRequested": True, "reason": reason}

    async def emergency_stop(self, *, reason: str) -> Mapping[str, object]:
        await asyncio.to_thread(
            self._request,
            "/api/fleet/command",
            {
                "action": "emergency",
                "drone_ids": [self._drone_id],
                "confirmed": True,
            },
        )
        return {"emergencyStopRequested": True, "reason": reason}

    async def close(self) -> None:
        # The compatibility service is owned and stopped independently.
        return

    def _read_token(self) -> str:
        try:
            with urlopen(f"{self._origin}/", timeout=5) as response:
                page = response.read(65_536).decode("utf-8")
        except (OSError, URLError, UnicodeDecodeError) as error:
            raise TelloBackendError("Brain2Devices loopback service is unavailable") from error
        parser = _TokenParser()
        parser.feed(page)
        if parser.token is None:
            raise TelloBackendError("Brain2Devices local control grant is unavailable")
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
                raise TelloBackendError("Brain2Devices control grant is unavailable")
            data = json.dumps(dict(body), separators=(",", ":")).encode("utf-8")
            method = "POST"
            headers.update(
                {
                    "Content-Type": "application/json",
                    "X-Brain2Devices-Token": self._token,
                }
            )
        try:
            request = Request(f"{self._origin}{path}", data=data, method=method, headers=headers)
            with urlopen(request, timeout=15) as response:
                raw = response.read(262_144)
            value: object = json.loads(raw.decode("utf-8"))
        except HTTPError as error:
            raise TelloBackendError(
                f"Brain2Devices rejected the safe-state operation with HTTP {error.code}"
            ) from error
        except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TelloBackendError("Brain2Devices returned an invalid response") from error
        if not isinstance(value, dict):
            raise TelloBackendError("Brain2Devices response must be an object")
        if body is not None and value.get("accepted") is not True:
            raise TelloBackendError(str(value.get("error", "Operation was rejected"))[:500])
        return value


@dataclass(frozen=True, slots=True)
class Brain2DevicesTelloConfiguration:
    repository: Path
    python_executable: Path
    ip_address: str | None = None


def verify_brain2devices_checkout(repository: Path) -> None:
    try:
        verify_external_git_checkout(
            repository,
            expected_revision=BRAIN2DEVICES_REVISION,
            required_path="src/brain2devices/hardware/tello.py",
            source_name="Brain2Devices",
        )
    except ExternalSourceCheckoutError as error:
        raise TelloBackendError(str(error)) from error


class Brain2DevicesTelloProcess:
    """One process owns one Brain2Devices ``DroneClient`` and no headset."""

    def __init__(self, configuration: Brain2DevicesTelloConfiguration) -> None:
        self.configuration = configuration
        self._process: asyncio.subprocess.Process | None = None
        self._request_lock = asyncio.Lock()
        self._stderr_task: asyncio.Task[None] | None = None
        self._diagnostics: deque[str] = deque(maxlen=20)

    async def start(self) -> Mapping[str, object]:
        verify_brain2devices_checkout(self.configuration.repository)
        if not self.configuration.python_executable.is_file():
            raise TelloBackendError(
                f"Brain2Devices Python was not found: {self.configuration.python_executable}"
            )
        arguments = [
            str(self.configuration.python_executable.resolve()),
            str(Path(__file__).with_name("vendor_worker.py").resolve()),
            "--repository",
            str(self.configuration.repository.resolve()),
        ]
        if self.configuration.ip_address:
            arguments.extend(("--ip-address", self.configuration.ip_address))
        self._process = await asyncio.create_subprocess_exec(
            *arguments,
            cwd=str(self.configuration.repository.resolve()),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        return await self._request("connect", deadline_seconds=45)

    async def telemetry(self) -> Mapping[str, object]:
        return await self._request("telemetry", deadline_seconds=5)

    async def land(self, *, reason: str) -> Mapping[str, object]:
        return await self._request("land", {"reason": reason}, deadline_seconds=12)

    async def emergency_stop(self, *, reason: str) -> Mapping[str, object]:
        return await self._request("emergency_stop", {"reason": reason}, deadline_seconds=3)

    async def close(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            if process.returncode is None:
                try:
                    await self._request("shutdown", deadline_seconds=5)
                except TelloBackendError:
                    pass
            if process.returncode is None:
                try:
                    await asyncio.wait_for(process.wait(), timeout=3)
                except TimeoutError:
                    process.terminate()
                    await process.wait()
        finally:
            if self._stderr_task is not None:
                await self._stderr_task
            self._stderr_task = None
            self._process = None

    async def _request(
        self,
        operation: str,
        payload: Mapping[str, object] | None = None,
        *,
        deadline_seconds: float,
    ) -> Mapping[str, object]:
        process = self._process
        if process is None or process.stdin is None or process.stdout is None:
            raise TelloBackendError("Tello worker is not running")
        if process.returncode is not None:
            raise TelloBackendError(self._exit_message())
        request_id = str(uuid4())
        request = {"requestId": request_id, "operation": operation, **dict(payload or {})}
        async with self._request_lock:
            process.stdin.write((json.dumps(request, separators=(",", ":")) + "\n").encode())
            await process.stdin.drain()
            try:
                raw = await asyncio.wait_for(process.stdout.readline(), timeout=deadline_seconds)
            except TimeoutError as error:
                raise TelloBackendError(f"Tello worker timed out during {operation}") from error
        if not raw:
            raise TelloBackendError(self._exit_message())
        try:
            value: object = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TelloBackendError("Tello worker returned invalid JSON") from error
        if not isinstance(value, dict) or value.get("requestId") != request_id:
            raise TelloBackendError("Tello worker response identity did not match")
        if value.get("ok") is not True:
            raise TelloBackendError(str(value.get("message", "Tello operation failed"))[:500])
        return value

    async def _drain_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        while raw := await process.stderr.readline():
            self._diagnostics.append(raw.decode(errors="replace").strip()[:500])

    def _exit_message(self) -> str:
        process = self._process
        code = None if process is None else process.returncode
        diagnostic = next(reversed(self._diagnostics), "no diagnostic was reported")
        return f"Tello worker exited with code {code}: {diagnostic}"
