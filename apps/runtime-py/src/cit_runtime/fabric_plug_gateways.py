"""Signed clients for privately paired Matter gateways; no Matter identity is copied."""

from __future__ import annotations

import asyncio
import http.client
import json
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .fabric_unlock_automation import (
    RemotePlugPowerRequest,
    RemotePlugPowerResult,
    RemotePlugSiteState,
    RemotePlugState,
    RemotePlugStateRequest,
    UnlockAutomationError,
    sign_remote_power_event,
    sign_remote_state_event,
)


class GatewayKnownPlug(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodeId: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    displayName: str = Field(min_length=1, max_length=160)


class GatewayConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    siteId: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    displayName: str = Field(min_length=1, max_length=160)
    origin: str
    deviceId: str = Field(pattern=r"^desktop-[a-f0-9]{16}$")
    secret: str = Field(min_length=43, max_length=128, pattern=r"^[A-Za-z0-9_-]+$", repr=False)
    knownPlugs: list[GatewayKnownPlug] = Field(default_factory=list, max_length=8)

    @field_validator("origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+ts\.net", parsed.hostname)
            is None
            or parsed.port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("A gateway must use an exact private Tailscale HTTPS origin")
        return value.rstrip("/")


class GatewaySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    siteId: str
    displayName: str
    connected: bool
    canControl: bool = False
    generatedAt: datetime | None = None
    plugs: list[RemotePlugState] = Field(default_factory=list)
    message: str | None = None


GatewayTransport = Callable[[GatewayConfiguration, str, dict[str, object], str], dict[str, object]]


def gateway_request(
    configuration: GatewayConfiguration, route: str, body: dict[str, object], signature: str
) -> dict[str, object]:
    hostname = urlsplit(configuration.origin).hostname
    assert hostname is not None
    connection = http.client.HTTPSConnection(hostname, timeout=8)
    try:
        connection.request(
            "POST",
            f"/api/v1/fabric/remote-plugs/{route}",
            body=json.dumps(body, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-CIT-Remote-Signature": signature},
        )
        response = connection.getresponse()
        payload = response.read(65_537)
        if not 200 <= response.status < 300 or len(payload) > 65_536:
            raise ValueError("Gateway rejected the request")
        document: object = json.loads(payload)
        if not isinstance(document, dict):
            raise ValueError("Invalid gateway response")
        return document
    finally:
        connection.close()


class PlugGatewayService:
    def __init__(
        self,
        configurations: Sequence[GatewayConfiguration],
        sequence_path: Path,
        *,
        transport: GatewayTransport = gateway_request,
    ) -> None:
        if len(configurations) > 8 or len({item.siteId for item in configurations}) != len(
            configurations
        ):
            raise ValueError("Configure at most eight gateways with distinct site IDs")
        self._configurations = {item.siteId: item for item in configurations}
        self._sequence_path = sequence_path
        self._transport = transport
        self._locks = {item.siteId: threading.Lock() for item in configurations}
        self._cache: dict[str, tuple[float, GatewaySnapshot]] = {}

    def _sequence(self, device_id: str) -> int:
        self._sequence_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._sequence_path) as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS gateway_sequences "
                "(device_id TEXT PRIMARY KEY, sequence INTEGER NOT NULL)"
            )
            # Commit the counter before sending: a lost response must never cause replay.
            row = database.execute(
                "INSERT INTO gateway_sequences VALUES (?, 1) ON CONFLICT(device_id) "
                "DO UPDATE SET sequence = sequence + 1 RETURNING sequence",
                (device_id,),
            ).fetchone()
        assert row is not None
        return int(row[0])

    def _configuration(self, site_id: str) -> GatewayConfiguration:
        configuration = self._configurations.get(site_id)
        if configuration is None:
            raise UnlockAutomationError(
                "PLUG_GATEWAY_NOT_FOUND", "This plug gateway is not configured.", status_code=404
            )
        return configuration

    def _state(self, site_id: str) -> GatewaySnapshot:
        configuration = self._configuration(site_id)
        with self._locks[site_id]:
            cached = self._cache.get(site_id)
            if cached is not None and time.monotonic() - cached[0] < 3:
                return cached[1].model_copy(deep=True)
            snapshot = GatewaySnapshot(
                siteId=site_id, displayName=configuration.displayName, connected=False
            )
            snapshot.plugs = [
                RemotePlugState(nodeId=plug.nodeId, displayName=plug.displayName, available=False)
                for plug in configuration.knownPlugs
            ]
            try:
                event = RemotePlugStateRequest(
                    deviceId=configuration.deviceId,
                    eventId=uuid4(),
                    sequence=self._sequence(configuration.deviceId),
                    occurredAtEpochMs=int(time.time() * 1000),
                )
                state = RemotePlugSiteState.model_validate(
                    self._transport(
                        configuration,
                        "state",
                        event.model_dump(mode="json"),
                        sign_remote_state_event(event, configuration.secret),
                    )
                )
                if (
                    state.siteId != site_id
                    or abs((datetime.now(UTC) - state.generatedAt).total_seconds()) > 120
                ):
                    raise ValueError("Gateway returned the wrong site or stale state")
                snapshot.connected = True
                snapshot.generatedAt = state.generatedAt
                snapshot.plugs = state.plugs
            except (OSError, ValueError, http.client.HTTPException):
                snapshot.message = (
                    "Gateway unavailable. Check Tailscale and the gateway connection."
                )
                if cached is not None:
                    snapshot.plugs = [
                        plug.model_copy(update={"available": False, "on": None})
                        for plug in cached[1].plugs
                    ]
            self._cache[site_id] = (time.monotonic(), snapshot)
            return snapshot.model_copy(deep=True)

    async def snapshots(self) -> list[GatewaySnapshot]:
        return list(
            await asyncio.gather(
                *(asyncio.to_thread(self._state, site_id) for site_id in self._configurations)
            )
        )

    async def power(
        self, site_id: str, on: bool, selected_node_ids: list[str]
    ) -> RemotePlugPowerResult:
        return await asyncio.to_thread(self._power, site_id, on, selected_node_ids)

    def _power(
        self, site_id: str, on: bool, selected_node_ids: list[str] | None
    ) -> RemotePlugPowerResult:
        configuration = self._configuration(site_id)
        with self._locks[site_id]:
            try:
                event = RemotePlugPowerRequest(
                    deviceId=configuration.deviceId,
                    eventId=uuid4(),
                    sequence=self._sequence(configuration.deviceId),
                    occurredAtEpochMs=int(time.time() * 1000),
                    on=on,
                    selectedNodeIds=selected_node_ids,
                )
                result = RemotePlugPowerResult.model_validate(
                    self._transport(
                        configuration,
                        "power",
                        event.model_dump(mode="json"),
                        sign_remote_power_event(event, configuration.secret),
                    )
                )
                if result.siteId != site_id or result.on != on:
                    raise ValueError("Gateway returned a mismatched command result")
                return result
            except (OSError, ValueError, http.client.HTTPException) as error:
                raise UnlockAutomationError(
                    "PLUG_GATEWAY_RESULT_UNKNOWN",
                    "The command result is unknown. Refresh the plug status before trying again.",
                    status_code=502,
                ) from error
            finally:
                # Force observation after commands, including timeouts; never assume a state.
                cached = self._cache.get(site_id)
                if cached is not None:
                    self._cache[site_id] = (0, cached[1])

    async def stop_all(self) -> tuple[list[str], list[str]]:
        """Explicit global stop sends OFF once to each gateway's saved group."""
        site_ids = list(self._configurations)
        results = await asyncio.gather(
            *(asyncio.to_thread(self._power, site_id, False, None) for site_id in site_ids),
            return_exceptions=True,
        )
        stopped: list[str] = []
        failed: list[str] = []
        for site_id, result in zip(site_ids, results, strict=True):
            if isinstance(result, RemotePlugPowerResult) and result.accepted:
                stopped.append(site_id)
            else:
                failed.append(site_id)
        return stopped, failed


def configured_plug_gateways(raw: str, sequence_path: Path) -> PlugGatewayService:
    try:
        document = json.loads(raw)
        if not isinstance(document, list):
            raise ValueError("Expected gateway list")
        configurations = [GatewayConfiguration.model_validate(item) for item in document]
        return PlugGatewayService(configurations, sequence_path)
    except ValueError:
        raise ValueError("The protected plug-gateway configuration is invalid") from None
