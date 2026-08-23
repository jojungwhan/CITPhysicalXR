"""Bounded Matter OnOff plug backend."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from .matter_client import MatterServerClient, MatterServerError


class SmartPlugError(RuntimeError):
    """A Matter plug operation failed without exposing setup or Wi-Fi credentials."""


class MatterClientProtocol(Protocol):
    nodes: dict[int, dict[str, object]]

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def refresh_node(self, node_id: int) -> dict[str, object]: ...

    async def read_on_off(self, node_id: int, endpoint_id: int) -> bool: ...

    async def set_on_off(self, node_id: int, endpoint_id: int, on: bool) -> None: ...


@dataclass(frozen=True, slots=True)
class MatterSmartPlugConfiguration:
    server_url: str
    matter_node_id: int
    endpoint_id: int
    verify_timeout_seconds: float = 3.0

    def validate(self) -> None:
        if self.matter_node_id < 1:
            raise SmartPlugError("Matter node ID must be positive")
        if not 1 <= self.endpoint_id <= 0xFFFF:
            raise SmartPlugError("Matter endpoint must be between 1 and 65535")
        if not 0.5 <= self.verify_timeout_seconds <= 10:
            raise SmartPlugError("Matter verification timeout must be between 0.5 and 10 seconds")


class MatterSmartPlug:
    """Expose only the standard Matter OnOff cluster for one plug endpoint."""

    def __init__(
        self,
        configuration: MatterSmartPlugConfiguration,
        *,
        client: MatterClientProtocol | None = None,
    ) -> None:
        self.configuration = configuration
        self._client = client or MatterServerClient(configuration.server_url)
        self._started = False
        self._lock = asyncio.Lock()

    async def start(self) -> bool:
        self.configuration.validate()
        try:
            await self._client.connect()
            node = self._client.nodes.get(self.configuration.matter_node_id)
            if node is None:
                node = await self._client.refresh_node(self.configuration.matter_node_id)
            if node.get("available") is not True:
                raise SmartPlugError("Matter smart plug is commissioned but currently unavailable")
            self._started = True
            return await self.read_state()
        except (MatterServerError, OSError) as error:
            raise SmartPlugError(str(error)) from error

    async def read_state(self) -> bool:
        if not self._started:
            raise SmartPlugError("Matter smart-plug backend is not started")
        try:
            return await self._client.read_on_off(
                self.configuration.matter_node_id,
                self.configuration.endpoint_id,
            )
        except (MatterServerError, OSError) as error:
            raise SmartPlugError(str(error)) from error

    async def set_power(self, on: bool) -> bool:
        if type(on) is not bool:
            raise SmartPlugError("Smart-plug state must be boolean")
        if not self._started:
            raise SmartPlugError("Matter smart-plug backend is not started")
        async with self._lock:
            current = await self.read_state()
            if current == on:
                return current
            try:
                await self._client.set_on_off(
                    self.configuration.matter_node_id,
                    self.configuration.endpoint_id,
                    on,
                )
                deadline = (
                    asyncio.get_running_loop().time() + self.configuration.verify_timeout_seconds
                )
                while asyncio.get_running_loop().time() < deadline:
                    observed = await self.read_state()
                    if observed == on:
                        return observed
                    await asyncio.sleep(0.2)
            except (MatterServerError, OSError) as error:
                raise SmartPlugError(str(error)) from error
            raise SmartPlugError("Matter smart plug did not reach the requested verified state")

    async def close(self) -> None:
        self._started = False
        await self._client.close()
