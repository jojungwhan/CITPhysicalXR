"""Authenticated out-of-process adapter WebSocket transport."""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from cit_protocol import (
    AdapterAcknowledgementFrame,
    AdapterAuthenticationFrame,
    AdapterCommandFrame,
    AdapterCommandLifecycleFrame,
    AdapterEventFrame,
    AdapterHeartbeatFrame,
    AdapterRegisteredFrame,
    AdapterRegistrationFrame,
    AdapterStopFrame,
    AdapterWelcomeFrame,
    FabricCommandLifecycleStage,
    FabricResolvedCommand,
    IntegrationNode,
    to_wire,
)
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from .fabric import (
    FabricConflictError,
    FabricDispatchOutcome,
    FabricNotFoundError,
    FabricPolicyError,
    InteractionFabric,
)
from .fabric_auth import (
    FabricAuthenticationError,
    FabricAuthorizationError,
    FabricAuthService,
    FabricPrincipal,
)
from .fabric_repository import SQLiteFabricRepository

_AUTH_TIMEOUT_SECONDS = 5.0
_REGISTRATION_TIMEOUT_SECONDS = 5.0
_IDLE_TIMEOUT_SECONDS = 20.0
_MAX_FRAME_BYTES = 131_072
_MAX_FRAMES_PER_SECOND = 200
_MAX_SEEN_FRAME_IDS = 4096


@dataclass(slots=True)
class _AdapterConnection:
    identity: FabricPrincipal
    websocket: WebSocket
    node_ids: tuple[str, ...]
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    seen_frame_ids: set[str] = field(default_factory=set)
    seen_frame_order: deque[str] = field(default_factory=deque)
    frame_times: deque[float] = field(default_factory=deque)


class FabricAdapterConnections:
    def __init__(
        self,
        fabric: InteractionFabric,
        auth: FabricAuthService,
        repository: SQLiteFabricRepository,
        *,
        clock: Any,
        runtime_id: str = "cit-runtime-local",
    ) -> None:
        self._fabric = fabric
        self._auth = auth
        self._repository = repository
        self._clock = clock
        self._runtime_id = runtime_id
        self._by_node_id: dict[str, _AdapterConnection] = {}
        self._lock = asyncio.Lock()

    async def run(
        self,
        websocket: WebSocket,
        *,
        allowed_origins: frozenset[str],
    ) -> None:
        origin = websocket.headers.get("origin")
        if origin is not None and origin not in allowed_origins:
            await websocket.close(code=4403, reason="WebSocket origin is not allowed")
            return
        await websocket.accept()
        connection: _AdapterConnection | None = None
        try:
            authentication = await self._receive_model(
                websocket,
                AdapterAuthenticationFrame,
                deadline_seconds=_AUTH_TIMEOUT_SECONDS,
            )
            principal = self._auth.authenticate(authentication.credential, at=self._clock())
            self._auth.require(principal, "fabric.adapters.connect")
            _require_fresh_frame(authentication.sentAt, now=self._clock())
            await websocket.send_json(
                to_wire(
                    AdapterWelcomeFrame.model_validate(
                        {
                            "frameType": "adapter.welcome",
                            "frameId": str(uuid4()),
                            "protocolVersion": 1,
                            "runtimeId": self._runtime_id,
                            "heartbeatIntervalMs": 5000,
                            "sentAt": self._clock(),
                        }
                    )
                )
            )
            registration = await self._receive_model(
                websocket,
                AdapterRegistrationFrame,
                deadline_seconds=_REGISTRATION_TIMEOUT_SECONDS,
            )
            _require_fresh_frame(registration.sentAt, now=self._clock())
            self._authorize_registration(principal, registration)
            nodes = self._fabric.register_plugin_and_nodes(
                registration.manifest,
                registration.nodes,
            )
            connection = _AdapterConnection(
                identity=principal,
                websocket=websocket,
                node_ids=tuple(node.nodeId for node in nodes),
            )
            await self._install_connection(connection)
            await self._send(
                connection,
                AdapterRegisteredFrame.model_validate(
                    {
                        "frameType": "adapter.registered",
                        "frameId": str(uuid4()),
                        "protocolVersion": 1,
                        "registeredNodeIds": list(connection.node_ids),
                        "sentAt": self._clock(),
                    }
                ),
            )
            self._repository.record_fabric_audit(
                actor_id=principal.identity_id,
                action="fabric.adapter.register",
                resource_type="plugin",
                resource_id=registration.manifest.pluginId,
                outcome="succeeded",
                correlation_id=str(registration.frameId),
                occurred_at=self._clock(),
                details={"nodeCount": len(connection.node_ids)},
            )
            while True:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=_IDLE_TIMEOUT_SECONDS,
                )
                value = _parse_frame(raw)
                self._enforce_rate(connection)
                frame_type = value.get("frameType")
                if frame_type == "adapter.heartbeat":
                    heartbeat_frame = AdapterHeartbeatFrame.model_validate(value)
                    duplicate = self._remember_frame(
                        connection,
                        str(heartbeat_frame.frameId),
                    )
                    if not duplicate:
                        self._handle_heartbeat(connection, heartbeat_frame)
                    await self._acknowledge(
                        connection,
                        heartbeat_frame.frameId,
                        duplicate=duplicate,
                    )
                elif frame_type == "adapter.event":
                    event_frame = AdapterEventFrame.model_validate(value)
                    duplicate_frame = self._remember_frame(
                        connection,
                        str(event_frame.frameId),
                    )
                    self._require_owned_node(connection, event_frame.event.sourceNodeId)
                    if duplicate_frame:
                        await self._acknowledge(
                            connection,
                            event_frame.frameId,
                            duplicate=True,
                        )
                        continue
                    result = await self._fabric.ingest_event(event_frame.event)
                    await self._acknowledge(
                        connection,
                        event_frame.frameId,
                        duplicate=result.duplicate,
                        stream_sequence=(
                            result.stored_event.stream_sequence
                            if result.stored_event is not None
                            else None
                        ),
                    )
                elif frame_type == "adapter.command_lifecycle":
                    lifecycle_frame = AdapterCommandLifecycleFrame.model_validate(value)
                    duplicate_frame = self._remember_frame(
                        connection,
                        str(lifecycle_frame.frameId),
                    )
                    self._require_owned_node(
                        connection,
                        lifecycle_frame.lifecycle.targetNodeId,
                    )
                    if duplicate_frame:
                        await self._acknowledge(
                            connection,
                            lifecycle_frame.frameId,
                            duplicate=True,
                        )
                        continue
                    stored = self._fabric.accept_adapter_lifecycle(lifecycle_frame.lifecycle)
                    await self._acknowledge(
                        connection,
                        lifecycle_frame.frameId,
                        duplicate=stored is None,
                        stream_sequence=stored.stream_sequence if stored is not None else None,
                    )
                else:
                    await websocket.close(code=4400, reason="Unsupported adapter frame")
                    return
        except TimeoutError:
            await websocket.close(code=4408, reason="Adapter authentication or heartbeat timed out")
        except FabricAuthenticationError:
            await websocket.close(code=4401, reason="Adapter authentication failed")
        except (FabricAuthorizationError, FabricPolicyError):
            await websocket.close(code=4403, reason="Adapter frame was not authorized")
        except FabricNotFoundError:
            await websocket.close(code=4404, reason="Adapter frame references unknown state")
        except FabricConflictError:
            await websocket.close(code=4409, reason="Adapter frame conflicts with current state")
        except (ValidationError, ValueError, json.JSONDecodeError):
            await websocket.close(code=4400, reason="Adapter frame is invalid")
        except WebSocketDisconnect:
            pass
        finally:
            if connection is not None:
                await self._remove_connection(connection)

    async def dispatch(
        self,
        command: FabricResolvedCommand,
        node: IntegrationNode,
    ) -> FabricDispatchOutcome:
        connection = self._by_node_id.get(node.nodeId)
        if connection is None:
            return FabricDispatchOutcome(
                accepted=False,
                terminal_stage=FabricCommandLifecycleStage.FAILED,
                code="ADAPTER_OFFLINE",
                message="The out-of-process adapter is not connected",
            )
        frame = AdapterCommandFrame.model_validate(
            {
                "frameType": "adapter.command",
                "frameId": str(uuid4()),
                "protocolVersion": 1,
                "command": command.model_dump(mode="json", exclude_none=True),
                "sentAt": self._clock(),
            }
        )
        try:
            await self._send(connection, frame)
        except (RuntimeError, WebSocketDisconnect):
            return FabricDispatchOutcome(
                accepted=False,
                terminal_stage=FabricCommandLifecycleStage.FAILED,
                code="ADAPTER_SEND_FAILED",
                message="The adapter connection failed during dispatch",
            )
        return FabricDispatchOutcome(accepted=True)

    async def stop_nodes(self, *, reason: str) -> dict[str, tuple[str, ...]]:
        stopped: list[str] = []
        failed: list[str] = []
        for node_id, connection in tuple(self._by_node_id.items()):
            frame = AdapterStopFrame.model_validate(
                {
                    "frameType": "adapter.stop",
                    "frameId": str(uuid4()),
                    "protocolVersion": 1,
                    "nodeId": node_id,
                    "reason": reason,
                    "sentAt": self._clock(),
                }
            )
            try:
                await self._send(connection, frame)
            except (RuntimeError, WebSocketDisconnect):
                failed.append(node_id)
            else:
                stopped.append(node_id)
        return {"stopped": tuple(stopped), "failed": tuple(failed)}

    def connected_node_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_node_id))

    async def _install_connection(self, connection: _AdapterConnection) -> None:
        replaced: list[_AdapterConnection] = []
        async with self._lock:
            for node_id in connection.node_ids:
                previous = self._by_node_id.get(node_id)
                if (
                    previous is not None
                    and previous is not connection
                    and not any(item is previous for item in replaced)
                ):
                    replaced.append(previous)
                self._by_node_id[node_id] = connection
        for previous in replaced:
            await previous.websocket.close(code=4001, reason="Adapter node connection was replaced")

    async def _remove_connection(self, connection: _AdapterConnection) -> None:
        removed: list[str] = []
        async with self._lock:
            for node_id in connection.node_ids:
                if self._by_node_id.get(node_id) is connection:
                    self._by_node_id.pop(node_id, None)
                    removed.append(node_id)
        if removed:
            self._fabric.disconnect_nodes(removed)

    def _authorize_registration(
        self,
        principal: FabricPrincipal,
        registration: AdapterRegistrationFrame,
    ) -> None:
        allowed_plugins = {
            role.removeprefix("plugin.") for role in principal.roles if role.startswith("plugin.")
        }
        if allowed_plugins and registration.manifest.pluginId not in allowed_plugins:
            raise FabricAuthorizationError("Adapter identity cannot register this plugin")
        for node in registration.nodes:
            self._auth.require(
                principal,
                "fabric.nodes.write",
                site_id=node.siteId,
                room_id=node.roomId,
            )

    def _handle_heartbeat(
        self,
        connection: _AdapterConnection,
        frame: AdapterHeartbeatFrame,
    ) -> None:
        for report in frame.reports:
            self._require_owned_node(connection, report.nodeId)
            self._fabric.report_health(report)

    @staticmethod
    def _require_owned_node(connection: _AdapterConnection, node_id: str) -> None:
        if node_id not in connection.node_ids:
            raise FabricAuthorizationError("Adapter frame names a node it did not register")

    @staticmethod
    def _enforce_rate(connection: _AdapterConnection) -> None:
        now = time.monotonic()
        cutoff = now - 1.0
        while connection.frame_times and connection.frame_times[0] < cutoff:
            connection.frame_times.popleft()
        if len(connection.frame_times) >= _MAX_FRAMES_PER_SECOND:
            raise ValueError("Adapter frame rate exceeds its limit")
        connection.frame_times.append(now)

    @staticmethod
    def _remember_frame(connection: _AdapterConnection, frame_id: str) -> bool:
        if frame_id in connection.seen_frame_ids:
            return True
        connection.seen_frame_ids.add(frame_id)
        connection.seen_frame_order.append(frame_id)
        while len(connection.seen_frame_order) > _MAX_SEEN_FRAME_IDS:
            expired = connection.seen_frame_order.popleft()
            connection.seen_frame_ids.discard(expired)
        return False

    async def _acknowledge(
        self,
        connection: _AdapterConnection,
        frame_id: Any,
        *,
        duplicate: bool,
        stream_sequence: int | None = None,
    ) -> None:
        frame = AdapterAcknowledgementFrame.model_validate(
            {
                "frameType": "adapter.ack",
                "frameId": str(uuid4()),
                "protocolVersion": 1,
                "acknowledgedFrameId": str(frame_id),
                "status": "duplicate" if duplicate else "accepted",
                "streamSequence": stream_sequence,
                "sentAt": self._clock(),
            }
        )
        await self._send(connection, frame)

    @staticmethod
    async def _send(connection: _AdapterConnection, frame: Any) -> None:
        async with connection.send_lock:
            await connection.websocket.send_json(to_wire(frame))

    @staticmethod
    async def _receive_model(
        websocket: WebSocket,
        model_type: Any,
        *,
        deadline_seconds: float,
    ) -> Any:
        async with asyncio.timeout(deadline_seconds):
            raw = await websocket.receive_text()
        return model_type.model_validate(_parse_frame(raw))


def _parse_frame(raw: str) -> dict[str, object]:
    if len(raw.encode("utf-8")) > _MAX_FRAME_BYTES:
        raise ValueError("Adapter frame exceeds the 128 KiB limit")

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"Adapter frame repeats key {key!r}")
            value[key] = item
        return value

    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError("Adapter frame must be an object")
    return value


def _require_fresh_frame(sent_at: datetime, *, now: datetime) -> None:
    if sent_at.tzinfo is None or sent_at.utcoffset() is None:
        raise ValueError("Adapter frame timestamp must include an offset")
    if abs(now - sent_at) > timedelta(seconds=30):
        raise ValueError("Adapter frame timestamp is stale")
