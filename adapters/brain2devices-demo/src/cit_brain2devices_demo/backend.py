"""Backends for the bounded Brain2Devices demonstration controller."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class BrainDemoBackendError(RuntimeError):
    """The bounded demo backend rejected or could not complete an operation."""


class BrainDemoBackend(Protocol):
    async def start(self) -> Mapping[str, object]: ...

    async def status(self) -> Mapping[str, object]: ...

    async def arm(self, parameters: Mapping[str, object]) -> Mapping[str, object]: ...

    async def stop(self, *, reason: str) -> Mapping[str, object]: ...

    async def close(self) -> None: ...


class SimulatedBrainDemoBackend:
    """Safe one-shot state machine used by CI and tutor UI practice."""

    def __init__(self) -> None:
        self._state: dict[str, object] = {
            "available": True,
            "active": False,
            "armed": False,
            "phase": "idle",
            "progress": 0.0,
            "message": "Simulation is ready; no aircraft can move",
            "error": None,
            "triggeredBy": None,
            "simulated": True,
        }
        self._armed_at: float | None = None
        self._dwell_seconds = 0.0

    async def start(self) -> Mapping[str, object]:
        return await self.status()

    async def status(self) -> Mapping[str, object]:
        if self._armed_at is not None:
            elapsed = max(0.0, time.monotonic() - self._armed_at)
            duration = max(1.0, self._dwell_seconds)
            progress = min(1.0, elapsed / duration)
            self._state["progress"] = progress
            if progress >= 1.0:
                self._state.update(
                    {
                        "active": False,
                        "armed": False,
                        "phase": "simulated_completed",
                        "message": "Simulation completed; no physical flight command was sent",
                        "triggeredBy": "attention",
                    }
                )
                self._armed_at = None
        return dict(self._state)

    async def arm(self, parameters: Mapping[str, object]) -> Mapping[str, object]:
        self._dwell_seconds = _bounded_number(parameters.get("dwellSeconds"), 0.0, 10.0)
        self._armed_at = time.monotonic()
        self._state.update(
            {
                "active": True,
                "armed": True,
                "phase": "waiting",
                "progress": 0.0,
                "message": "Simulating a one-shot MindWave threshold",
                "error": None,
                "triggeredBy": None,
                "signals": _signals_from_parameters(parameters),
                "dwellSeconds": self._dwell_seconds,
            }
        )
        return await self.status()

    async def stop(self, *, reason: str) -> Mapping[str, object]:
        self._armed_at = None
        self._state.update(
            {
                "active": False,
                "armed": False,
                "phase": "idle",
                "progress": 0.0,
                "message": f"Simulation stopped: {reason}",
                "triggeredBy": None,
            }
        )
        return dict(self._state)

    async def close(self) -> None:
        await self.stop(reason="adapter_shutdown")


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


class Brain2DevicesApiDemoBackend:
    """Loopback-only projection of Brain2Devices' characterized one-shot gate."""

    def __init__(self, *, origin: str = "http://127.0.0.1:8765") -> None:
        if origin != "http://127.0.0.1:8765":
            raise ValueError("Brain2Devices demo API is restricted to loopback")
        self._origin = origin
        self._token: str | None = None

    async def start(self) -> Mapping[str, object]:
        self._token = await asyncio.to_thread(self._read_token)
        status = await self.status()
        if status.get("available") is not True:
            raise BrainDemoBackendError(
                str(status.get("message", "Brain2Devices one-shot demo is unavailable"))[:500]
            )
        return status

    async def status(self) -> Mapping[str, object]:
        state = await asyncio.to_thread(self._request, "/api/state", None)
        return _project_status(state)

    async def arm(self, parameters: Mapping[str, object]) -> Mapping[str, object]:
        response = await asyncio.to_thread(
            self._request,
            "/api/brain/demo-trigger/arm",
            {
                "signals": _signals_from_parameters(parameters),
                "dwell_seconds": parameters["dwellSeconds"],
                "confirmed": True,
            },
        )
        trigger = response.get("demo_trigger")
        return _normalize_trigger(trigger if isinstance(trigger, dict) else {})

    async def stop(self, *, reason: str) -> Mapping[str, object]:
        status = await self.status()
        operation = "already_stopped"
        if status.get("armed") is True:
            await asyncio.to_thread(self._request, "/api/brain/demo-trigger/disarm", {})
            operation = "trigger_disarmed"
        elif status.get("demoRunning") is True:
            await asyncio.to_thread(
                self._request,
                "/api/fleet/local-radios/sequential-auto/cancel",
                {"confirmed": True},
            )
            operation = "demo_cancel_requested"
        return {**dict(await self.status()), "stopReason": reason, "stopOperation": operation}

    async def close(self) -> None:
        # Brain2Devices owns the local service. Disarm/cancel the bounded workflow,
        # but do not stop independent MindWave, Tello, or camera processes.
        try:
            await self.stop(reason="adapter_shutdown")
        except BrainDemoBackendError:
            pass

    def _read_token(self) -> str:
        try:
            with urlopen(f"{self._origin}/", timeout=5) as response:
                page = response.read(65_536).decode("utf-8")
        except (OSError, URLError, UnicodeDecodeError) as error:
            raise BrainDemoBackendError("Brain2Devices loopback service is unavailable") from error
        parser = _TokenParser()
        parser.feed(page)
        if parser.token is None:
            raise BrainDemoBackendError("Brain2Devices local control grant is unavailable")
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
                raise BrainDemoBackendError("Brain2Devices control grant is unavailable")
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
                error_value = json.loads(error.read(65_536).decode("utf-8"))
                if isinstance(error_value, dict):
                    detail = str(error_value.get("error", ""))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass
            raise BrainDemoBackendError(
                (detail or f"Brain2Devices returned HTTP {error.code}")[:500]
            ) from error
        except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BrainDemoBackendError("Brain2Devices returned an invalid response") from error
        if not isinstance(value, dict):
            raise BrainDemoBackendError("Brain2Devices response must be an object")
        if body is not None and value.get("accepted") is not True:
            raise BrainDemoBackendError(str(value.get("error", "Operation was rejected"))[:500])
        return value


def _signals_from_parameters(parameters: Mapping[str, object]) -> dict[str, dict[str, object]]:
    return {
        "attention": {
            "enabled": parameters["attentionEnabled"],
            "threshold": parameters["attentionThreshold"],
        },
        "meditation": {
            "enabled": parameters["meditationEnabled"],
            "threshold": parameters["meditationThreshold"],
        },
        "blink": {
            "enabled": parameters["blinkEnabled"],
            "threshold": parameters["blinkThreshold"],
        },
    }


def _project_status(state: Mapping[str, object]) -> dict[str, object]:
    brain = state.get("brain")
    trigger: Mapping[str, object] = {}
    if isinstance(brain, dict) and isinstance(brain.get("demo_trigger"), dict):
        trigger = brain["demo_trigger"]
    projected = _normalize_trigger(trigger)
    fleet = state.get("fleet")
    sequential: Mapping[str, object] = {}
    if isinstance(fleet, dict) and isinstance(fleet.get("sequential_demo"), dict):
        sequential = fleet["sequential_demo"]
    projected.update(
        {
            "demoRunning": sequential.get("running") is True,
            "demoState": _optional_text(sequential.get("state")),
            "demoPhase": _optional_text(sequential.get("phase")),
            "demoMessage": _optional_text(sequential.get("message")),
            "simulated": False,
        }
    )
    return projected


def _normalize_trigger(trigger: Mapping[str, object]) -> dict[str, object]:
    signals = trigger.get("signals")
    return {
        "available": trigger.get("available") is True,
        "active": trigger.get("active") is True,
        "armed": trigger.get("armed") is True,
        "phase": _optional_text(trigger.get("phase")) or "unavailable",
        "progress": _bounded_number(trigger.get("progress"), 0.0, 1.0),
        "message": _optional_text(trigger.get("message")) or "Status unavailable",
        "error": _optional_text(trigger.get("error")),
        "triggeredBy": _optional_text(trigger.get("triggered_by")),
        "dwellSeconds": _bounded_number(trigger.get("dwell_seconds"), 0.0, 10.0),
        "signals": signals if isinstance(signals, dict) else {},
    }


def _optional_text(value: object) -> str | None:
    return str(value)[:500] if isinstance(value, str) and value else None


def _bounded_number(value: object, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return minimum
    return min(maximum, max(minimum, float(value)))
