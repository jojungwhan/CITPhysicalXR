"""Simulator and isolated TinyTuya LAN backend."""

from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Protocol


class SmartPlugError(RuntimeError):
    """A smart-plug operation failed without exposing its credentials."""


class SmartPlugBackend(Protocol):
    async def start(self) -> bool: ...

    async def read_state(self) -> bool: ...

    async def set_power(self, on: bool) -> bool: ...

    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class TinyTuyaConfiguration:
    device_id: str = field(repr=False)
    local_key: str = field(repr=False)
    device_address: str
    protocol_version: str = "3.3"
    switch_dps: int = 1
    timeout_seconds: float = 3.0

    def validate(self) -> None:
        if not self.device_id.strip():
            raise SmartPlugError("Tuya device ID cannot be empty")
        if len(self.local_key) != 16:
            raise SmartPlugError("Tuya local key must contain exactly 16 characters")
        try:
            address = ipaddress.ip_address(self.device_address)
        except ValueError as error:
            raise SmartPlugError("Smart-plug address must be an exact IP address") from error
        if address.version != 4:
            raise SmartPlugError("This adapter currently supports an exact IPv4 LAN address")
        if not (address.is_private or address.is_loopback or address.is_link_local):
            raise SmartPlugError("Smart-plug address must remain on a private local network")
        if self.protocol_version not in {"3.1", "3.2", "3.3", "3.4", "3.5"}:
            raise SmartPlugError("Unsupported Tuya LAN protocol version")
        if not 1 <= self.switch_dps <= 255:
            raise SmartPlugError("Switch datapoint must be between 1 and 255")
        if not 0.1 <= self.timeout_seconds <= 10:
            raise SmartPlugError("Device timeout must be between 0.1 and 10 seconds")


class SimulatedSmartPlug:
    def __init__(self, *, initially_on: bool = False) -> None:
        self._on = initially_on
        self.started = False
        self.closed = False
        self.commands: list[bool] = []

    async def start(self) -> bool:
        self.started = True
        self.closed = False
        return self._on

    async def read_state(self) -> bool:
        if not self.started or self.closed:
            raise SmartPlugError("Simulated smart plug is not running")
        return self._on

    async def set_power(self, on: bool) -> bool:
        if type(on) is not bool:
            raise SmartPlugError("Smart-plug state must be boolean")
        if not self.started or self.closed:
            raise SmartPlugError("Simulated smart plug is not running")
        if self._on != on:
            self.commands.append(on)
            self._on = on
        return self._on

    async def close(self) -> None:
        self.closed = True


class TinyTuyaLanPlug:
    """Serialize blocking TinyTuya calls outside the event loop."""

    def __init__(
        self,
        configuration: TinyTuyaConfiguration,
        *,
        device_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.configuration = configuration
        self._device_factory = device_factory
        self._device: Any | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> bool:
        self.configuration.validate()
        if self._device is None:
            factory = self._device_factory
            if factory is None:
                try:
                    outlet_device = import_module("tinytuya").OutletDevice
                except ImportError as error:
                    raise SmartPlugError(
                        "TinyTuya 1.20.0 is required for physical LAN mode"
                    ) from error
                factory = outlet_device
            self._device = factory(
                self.configuration.device_id,
                address=self.configuration.device_address,
                local_key=self.configuration.local_key,
                connection_timeout=self.configuration.timeout_seconds,
                connection_retry_limit=1,
                version=float(self.configuration.protocol_version),
                persist=False,
            )
        return await self.read_state()

    async def read_state(self) -> bool:
        async with self._lock:
            device = self._require_device()
            response = await asyncio.to_thread(device.status)
            return self._extract_state(response)

    async def set_power(self, on: bool) -> bool:
        if type(on) is not bool:
            raise SmartPlugError("Smart-plug state must be boolean")
        async with self._lock:
            device = self._require_device()
            current = self._extract_state(await asyncio.to_thread(device.status))
            if current == on:
                return current
            response = await asyncio.to_thread(
                device.set_status,
                on,
                switch=self.configuration.switch_dps,
            )
            self._require_mapping(response, operation="set power")
            verified = self._extract_state(await asyncio.to_thread(device.status))
            if verified != on:
                raise SmartPlugError("Smart plug did not reach the requested verified state")
            return verified

    async def close(self) -> None:
        async with self._lock:
            device = self._device
            self._device = None
            close = getattr(device, "close", None)
            if callable(close):
                await asyncio.to_thread(close)

    def _require_device(self) -> Any:
        if self._device is None:
            raise SmartPlugError("Smart-plug LAN backend is not started")
        return self._device

    def _extract_state(self, response: object) -> bool:
        value = self._require_mapping(response, operation="read status")
        dps = value.get("dps")
        if not isinstance(dps, Mapping):
            raise SmartPlugError("Smart-plug status did not contain a DPS object")
        state = dps.get(str(self.configuration.switch_dps))
        if state is None:
            state = dps.get(self.configuration.switch_dps)
        if type(state) is not bool:
            raise SmartPlugError(
                f"Smart-plug DPS {self.configuration.switch_dps} is missing or not boolean"
            )
        return state

    @staticmethod
    def _require_mapping(response: object, *, operation: str) -> Mapping[object, object]:
        if not isinstance(response, Mapping):
            raise SmartPlugError(f"TinyTuya returned an invalid response during {operation}")
        error = response.get("Error") or response.get("Err") or response.get("error")
        if error:
            raise SmartPlugError(f"TinyTuya rejected {operation}: {str(error)[:300]}")
        return response
