"""Authenticated wire client shared by out-of-process Fabric adapters.

This module owns only the stable Fabric transport ceremony. Device lifecycle,
vendor calls, validation, safe state, and event semantics remain in each
adapter. Keeping that boundary narrow prevents a shared helper from becoming a
second orchestration core.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from cit_protocol import (
    AdapterAuthenticationFrame,
    AdapterCommandLifecycleFrame,
    AdapterEventFrame,
    AdapterHeartbeatFrame,
    AdapterRegistrationFrame,
    FabricCommandLifecycleEvent,
    FabricResolvedCommand,
    HealthReport,
    IntegrationNode,
    PluginManifest,
    to_wire,
)
from websockets.asyncio.client import connect
from websockets.typing import Origin


class AdapterSocket(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...


@dataclass(frozen=True, slots=True)
class FabricConnectionConfiguration:
    adapter_url: str
    adapter_token: str = field(repr=False)
    fabric_origin: str
    session_id: str
    site_id: str
    room_id: str


class FabricAdapterClient:
    """One authenticated adapter connection with canonical frame builders."""

    def __init__(
        self,
        configuration: FabricConnectionConfiguration,
        *,
        manifest: PluginManifest,
        nodes: Sequence[IntegrationNode],
    ) -> None:
        if not nodes:
            raise ValueError("An adapter must register at least one node")
        node_ids = [node.nodeId for node in nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Adapter node IDs must be unique")
        if any(node.pluginId != manifest.pluginId for node in nodes):
            raise ValueError("Every node must belong to the registered plugin manifest")
        self.configuration = configuration
        self.manifest = manifest
        self.nodes = tuple(nodes)
        self._socket: AdapterSocket | None = None
        self._send_lock = asyncio.Lock()
        base_sequence = time.time_ns()
        self._sequences = {node.nodeId: base_sequence for node in nodes}

    @asynccontextmanager
    async def connected(self) -> AsyncIterator[FabricAdapterClient]:
        """Connect, authenticate, register, then yield the ready wire client."""

        if self._socket is not None:
            raise RuntimeError("Fabric adapter client is already connected")
        async with connect(
            self.configuration.adapter_url,
            origin=Origin(self.configuration.fabric_origin),
            max_size=131_072,
            open_timeout=10,
            close_timeout=3,
        ) as raw_socket:
            self._socket = cast(AdapterSocket, raw_socket)
            try:
                await self.authenticate_and_register()
                yield self
            finally:
                self._socket = None

    async def authenticate_and_register(self) -> None:
        authentication = AdapterAuthenticationFrame.model_validate(
            {
                "frameType": "adapter.authenticate",
                "frameId": str(uuid4()),
                "protocolVersion": 1,
                "credential": self.configuration.adapter_token,
                "sentAt": datetime.now(UTC),
            }
        )
        await self.send(authentication)
        welcome = await self.receive_json()
        if welcome.get("frameType") != "adapter.welcome":
            raise RuntimeError("Fabric did not accept adapter authentication")

        registration = AdapterRegistrationFrame.model_validate(
            {
                "frameType": "adapter.register",
                "frameId": str(uuid4()),
                "protocolVersion": 1,
                "manifest": self.manifest.model_dump(mode="json", exclude_none=True),
                "nodes": [node.model_dump(mode="json", exclude_none=True) for node in self.nodes],
                "sentAt": datetime.now(UTC),
            }
        )
        await self.send(registration)
        registered = await self.receive_json()
        if registered.get("frameType") != "adapter.registered":
            raise RuntimeError("Fabric did not accept adapter registration")
        expected = {node.nodeId for node in self.nodes}
        received = set(registered.get("registeredNodeIds", []))
        if received != expected:
            raise RuntimeError("Fabric registered a different adapter node set")

    async def receive_json(self) -> dict[str, Any]:
        raw = await self._require_socket().recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        value: object = json.loads(raw)
        if not isinstance(value, dict):
            raise RuntimeError("Fabric frame must be an object")
        return value

    async def send(self, model: Any) -> None:
        payload = json.dumps(to_wire(model), separators=(",", ":"))
        async with self._send_lock:
            await self._require_socket().send(payload)

    async def publish_event(
        self,
        *,
        topic: str,
        source_node_id: str,
        payload: Mapping[str, object],
        confidence: float | None = 1.0,
        ttl_ms: int = 2_000,
        data_classification: str = "operational",
        correlation_id: str | UUID | None = None,
        causation_id: str | UUID | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        if source_node_id not in self._sequences:
            raise ValueError("Event source is not registered by this adapter")
        now = timestamp or datetime.now(UTC)
        await self.send(
            AdapterEventFrame.model_validate(
                {
                    "frameType": "adapter.event",
                    "frameId": str(uuid4()),
                    "protocolVersion": 1,
                    "event": {
                        "messageId": str(uuid4()),
                        "schemaVersion": "1.0",
                        "messageType": "event",
                        "topic": topic,
                        "sourceNodeId": source_node_id,
                        "sourceCapability": topic,
                        "siteId": self.configuration.site_id,
                        "roomId": self.configuration.room_id,
                        "sessionId": self.configuration.session_id,
                        "timestamp": now,
                        "monotonicTimestamp": time.monotonic_ns(),
                        "sequence": self.next_sequence(source_node_id),
                        "correlationId": str(correlation_id or uuid4()),
                        "causationId": str(causation_id) if causation_id is not None else None,
                        "confidence": confidence,
                        "ttlMs": ttl_ms,
                        "dataClassification": data_classification,
                        "payload": dict(payload),
                    },
                    "sentAt": now,
                }
            )
        )

    async def publish_heartbeat(self, reports: Sequence[HealthReport]) -> None:
        registered = set(self._sequences)
        if any(report.nodeId not in registered for report in reports):
            raise ValueError("Heartbeat contains a node not registered by this adapter")
        await self.send(
            AdapterHeartbeatFrame.model_validate(
                {
                    "frameType": "adapter.heartbeat",
                    "frameId": str(uuid4()),
                    "protocolVersion": 1,
                    "reports": [
                        report.model_dump(mode="json", exclude_none=True) for report in reports
                    ],
                    "sentAt": datetime.now(UTC),
                }
            )
        )

    async def publish_lifecycle(
        self,
        command: FabricResolvedCommand,
        stage: str,
        *,
        code: str | None = None,
        message: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        if command.targetNodeId not in self._sequences:
            raise ValueError("Lifecycle target is not registered by this adapter")
        now = datetime.now(UTC)
        lifecycle = FabricCommandLifecycleEvent.model_validate(
            {
                "messageId": str(uuid4()),
                "schemaVersion": "1.0",
                "messageType": "command.lifecycle",
                "commandId": command.commandId,
                "requestMessageId": command.requestMessageId,
                "sessionId": command.sessionId,
                "targetNodeId": command.targetNodeId,
                "stage": stage,
                "occurredAt": now,
                "correlationId": command.correlationId,
                "code": code,
                "message": message,
                "details": dict(details or {}),
            }
        )
        await self.send(
            AdapterCommandLifecycleFrame.model_validate(
                {
                    "frameType": "adapter.command_lifecycle",
                    "frameId": str(uuid4()),
                    "protocolVersion": 1,
                    "lifecycle": lifecycle.model_dump(mode="json", exclude_none=True),
                    "sentAt": now,
                }
            )
        )

    def next_sequence(self, node_id: str) -> int:
        try:
            self._sequences[node_id] += 1
        except KeyError as error:
            raise ValueError("Sequence requested for an unregistered node") from error
        return self._sequences[node_id]

    def _require_socket(self) -> AdapterSocket:
        if self._socket is None:
            raise RuntimeError("Fabric adapter client is not connected")
        return self._socket
