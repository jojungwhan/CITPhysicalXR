"""Durable state for the versioned CIT Interaction Fabric boundary."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, TypeVar
from uuid import uuid4

from cit_protocol import (
    CoursePack,
    FabricCommandLifecycleEvent,
    FabricCommandLifecycleStage,
    FabricCommandPriority,
    FabricEventEnvelope,
    FabricNodeConnectionState,
    FabricResolvedCommand,
    HealthReport,
    IntegrationNode,
    InteractionSession,
    PluginManifest,
    RoleBinding,
)
from pydantic import BaseModel

FABRIC_PAGE_LIMIT = 500
_MAX_JSON_BYTES = 65_536
_MAX_COURSE_PACK_JSON_BYTES = 131_072
_PRIORITY_RANK: dict[FabricCommandPriority, int] = {
    FabricCommandPriority.emergency_stop: 6,
    FabricCommandPriority.safety_engine: 5,
    FabricCommandPriority.instructor_override: 4,
    FabricCommandPriority.lesson_automation: 3,
    FabricCommandPriority.student_interaction: 2,
    FabricCommandPriority.autonomous_agent: 1,
}
_TERMINAL_COMMAND_STAGES = frozenset(
    {
        FabricCommandLifecycleStage.SUCCEEDED,
        FabricCommandLifecycleStage.FAILED,
        FabricCommandLifecycleStage.CANCELLED,
        FabricCommandLifecycleStage.TIMED_OUT,
        FabricCommandLifecycleStage.REJECTED,
    }
)
_FORBIDDEN_PERSISTED_TERMS = frozenset(
    {
        "accesstoken",
        "apikey",
        "authorization",
        "cookie",
        "credential",
        "password",
        "privatekey",
        "rawaudio",
        "rawbiosignal",
        "rawcamera",
        "rawframe",
        "rawimage",
        "rawvideo",
        "secret",
        "vendortoken",
    }
)


@dataclass(frozen=True, slots=True)
class StoredFabricEvent:
    stream_sequence: int
    event: FabricEventEnvelope


@dataclass(frozen=True, slots=True)
class StoredFabricLifecycle:
    stream_sequence: int
    lifecycle: FabricCommandLifecycleEvent


@dataclass(frozen=True, slots=True)
class FabricIdentityRecord:
    identity_id: str
    actor_type: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    site_id: str | None
    room_id: str | None
    session_id: str | None
    token_hash: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class FabricAuditRecord:
    audit_id: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    correlation_id: str | None
    occurred_at: datetime
    details: dict[str, object]


@dataclass(frozen=True, slots=True)
class FabricRememberedConnectionRecord:
    host_id: str
    reconnect_action_id: str
    requires_grounded_confirmation: bool
    remembered_at: datetime
    remembered_by: str


@dataclass(frozen=True, slots=True)
class FabricLeaseDecision:
    acquired: bool
    holder_session_id: str | None = None
    preempted_session_id: str | None = None


class FabricSequenceConflict(ValueError):
    """Raised when a node reuses a sequence for a different event identity."""


class FabricPersistenceConnection(Protocol):
    _connection: sqlite3.Connection


ModelT = TypeVar("ModelT", bound=BaseModel)


class FabricPersistenceMixin:
    """SQLite operations mixed into the runtime repository's one connection."""

    _connection: sqlite3.Connection

    def remember_fabric_connection(
        self,
        *,
        host_id: str,
        reconnect_action_id: str,
        requires_grounded_confirmation: bool,
        remembered_at: datetime,
        remembered_by: str,
    ) -> FabricRememberedConnectionRecord:
        timestamp = _aware_utc(remembered_at, field_name="remembered_at")
        if not 1 <= len(host_id) <= 160 or not 1 <= len(remembered_by) <= 128:
            raise ValueError("Remembered connection host and actor identifiers are invalid")
        if (
            not 1 <= len(reconnect_action_id) <= 96
            or not reconnect_action_id[0].isalnum()
            or any(
                not (character.isalnum() or character in "._-") for character in reconnect_action_id
            )
        ):
            raise ValueError("Remembered reconnect action identifier is invalid")
        record = FabricRememberedConnectionRecord(
            host_id=host_id,
            reconnect_action_id=reconnect_action_id,
            requires_grounded_confirmation=requires_grounded_confirmation,
            remembered_at=timestamp,
            remembered_by=remembered_by,
        )
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO fabric_remembered_connections (
                    host_id,
                    reconnect_action_id,
                    requires_grounded_confirmation,
                    remembered_at,
                    remembered_by
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(host_id, reconnect_action_id) DO UPDATE SET
                    requires_grounded_confirmation = excluded.requires_grounded_confirmation,
                    remembered_at = excluded.remembered_at,
                    remembered_by = excluded.remembered_by
                WHERE excluded.remembered_at >= fabric_remembered_connections.remembered_at
                """,
                (
                    record.host_id,
                    record.reconnect_action_id,
                    int(record.requires_grounded_confirmation),
                    record.remembered_at.isoformat(),
                    record.remembered_by,
                ),
            )
        return record

    def list_fabric_remembered_connections(
        self,
        *,
        host_id: str,
    ) -> tuple[FabricRememberedConnectionRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT *
            FROM fabric_remembered_connections
            WHERE host_id = ?
            ORDER BY remembered_at DESC, reconnect_action_id
            """,
            (host_id,),
        ).fetchall()
        return tuple(
            FabricRememberedConnectionRecord(
                host_id=str(row["host_id"]),
                reconnect_action_id=str(row["reconnect_action_id"]),
                requires_grounded_confirmation=bool(row["requires_grounded_confirmation"]),
                remembered_at=datetime.fromisoformat(row["remembered_at"]),
                remembered_by=str(row["remembered_by"]),
            )
            for row in rows
        )

    def register_fabric_plugin(
        self,
        manifest: PluginManifest,
        *,
        at: datetime,
    ) -> PluginManifest:
        timestamp = _aware_utc(at, field_name="at")
        encoded = _encode_model(manifest)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO fabric_plugins (
                    plugin_id,
                    plugin_version,
                    manifest_json,
                    registered_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(plugin_id, plugin_version) DO UPDATE SET
                    manifest_json = excluded.manifest_json,
                    updated_at = excluded.updated_at
                """,
                (
                    manifest.pluginId,
                    manifest.pluginVersion,
                    encoded,
                    timestamp.isoformat(),
                    timestamp.isoformat(),
                ),
            )
        return manifest

    def get_fabric_plugin(self, plugin_id: str, version: str) -> PluginManifest | None:
        row = self._connection.execute(
            """
            SELECT manifest_json
            FROM fabric_plugins
            WHERE plugin_id = ? AND plugin_version = ?
            """,
            (plugin_id, version),
        ).fetchone()
        return None if row is None else _decode_model(PluginManifest, row["manifest_json"])

    def list_fabric_plugins(self) -> tuple[PluginManifest, ...]:
        rows = self._connection.execute(
            """
            SELECT manifest_json
            FROM fabric_plugins
            ORDER BY plugin_id, plugin_version
            """
        ).fetchall()
        return tuple(_decode_model(PluginManifest, row["manifest_json"]) for row in rows)

    def upsert_fabric_node(
        self,
        node: IntegrationNode,
        *,
        at: datetime,
        lease_ttl: timedelta,
    ) -> IntegrationNode:
        timestamp = _aware_utc(at, field_name="at")
        if lease_ttl <= timedelta(0):
            raise ValueError("lease_ttl must be positive")
        if self.get_fabric_plugin(node.pluginId, node.pluginVersion) is None:
            raise ValueError(
                f"Plugin {node.pluginId!r} version {node.pluginVersion!r} is not registered"
            )
        normalized = node.model_copy(update={"lastSeenAt": timestamp})
        encoded = _encode_model(normalized)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO fabric_nodes (
                    node_id,
                    plugin_id,
                    plugin_version,
                    site_id,
                    room_id,
                    node_json,
                    connection_state,
                    health_state,
                    last_seen_at,
                    lease_expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    plugin_id = excluded.plugin_id,
                    plugin_version = excluded.plugin_version,
                    site_id = excluded.site_id,
                    room_id = excluded.room_id,
                    node_json = excluded.node_json,
                    connection_state = excluded.connection_state,
                    health_state = excluded.health_state,
                    last_seen_at = excluded.last_seen_at,
                    lease_expires_at = excluded.lease_expires_at
                """,
                (
                    normalized.nodeId,
                    normalized.pluginId,
                    normalized.pluginVersion,
                    normalized.siteId,
                    normalized.roomId,
                    encoded,
                    normalized.connectionState.value,
                    normalized.healthState.value,
                    timestamp.isoformat(),
                    (timestamp + lease_ttl).isoformat(),
                ),
            )
        return normalized

    def get_fabric_node(self, node_id: str) -> IntegrationNode | None:
        row = self._connection.execute(
            "SELECT node_json FROM fabric_nodes WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        return None if row is None else _decode_model(IntegrationNode, row["node_json"])

    def list_fabric_nodes(
        self,
        *,
        site_id: str | None = None,
        room_id: str | None = None,
    ) -> tuple[IntegrationNode, ...]:
        clauses: list[str] = []
        parameters: list[str] = []
        if site_id is not None:
            clauses.append("site_id = ?")
            parameters.append(site_id)
        if room_id is not None:
            clauses.append("room_id = ?")
            parameters.append(room_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._connection.execute(
            f"SELECT node_json FROM fabric_nodes {where} ORDER BY node_id",
            parameters,
        ).fetchall()
        return tuple(_decode_model(IntegrationNode, row["node_json"]) for row in rows)

    def update_fabric_health(
        self,
        report: HealthReport,
        *,
        at: datetime,
        lease_ttl: timedelta,
    ) -> IntegrationNode:
        timestamp = _aware_utc(at, field_name="at")
        reported_at = _aware_utc(report.reportedAt, field_name="report.reportedAt")
        if reported_at > timestamp + timedelta(seconds=30):
            raise ValueError("Health report timestamp is too far in the future")
        current = self.get_fabric_node(report.nodeId)
        if current is None:
            raise LookupError(f"Fabric node {report.nodeId!r} is not registered")
        metadata = current.metadata.model_dump(mode="json")
        if report.batteryPercent is not None:
            metadata["batteryPercent"] = report.batteryPercent
        if report.message is not None:
            metadata["healthMessage"] = report.message
        else:
            metadata.pop("healthMessage", None)
        metadata["healthMetrics"] = report.metrics.model_dump(mode="json")
        updated = current.model_copy(
            update={
                "connectionState": report.connectionState,
                "healthState": report.healthState,
                "lastSeenAt": timestamp,
                "metadata": current.metadata.model_validate(metadata),
            }
        )
        return self.upsert_fabric_node(updated, at=timestamp, lease_ttl=lease_ttl)

    def expire_fabric_nodes(self, *, at: datetime) -> tuple[str, ...]:
        timestamp = _aware_utc(at, field_name="at")
        rows = self._connection.execute(
            """
            SELECT node_id, node_json
            FROM fabric_nodes
            WHERE lease_expires_at <= ?
              AND connection_state NOT IN ('unavailable', 'disconnected', 'unsafe')
            ORDER BY node_id
            """,
            (timestamp.isoformat(),),
        ).fetchall()
        expired: list[str] = []
        with self._connection:
            for row in rows:
                node = _decode_model(IntegrationNode, row["node_json"])
                unavailable = node.model_copy(
                    update={
                        "connectionState": FabricNodeConnectionState.unavailable,
                        "lastSeenAt": timestamp,
                    }
                )
                self._connection.execute(
                    """
                    UPDATE fabric_nodes
                    SET node_json = ?, connection_state = ?, last_seen_at = ?
                    WHERE node_id = ?
                    """,
                    (
                        _encode_model(unavailable),
                        unavailable.connectionState.value,
                        timestamp.isoformat(),
                        unavailable.nodeId,
                    ),
                )
                expired.append(unavailable.nodeId)
            if expired:
                placeholders = ", ".join("?" for _ in expired)
                self._connection.execute(
                    f"""
                    UPDATE fabric_control_leases
                    SET released_at = ?, release_reason = 'node_lease_expired'
                    WHERE released_at IS NULL AND node_id IN ({placeholders})
                    """,
                    (timestamp.isoformat(), *expired),
                )
        return tuple(expired)

    def install_course_pack(
        self,
        course_pack: CoursePack,
        *,
        actor_id: str,
        at: datetime,
    ) -> CoursePack:
        timestamp = _aware_utc(at, field_name="at")
        encoded = _encode_model(course_pack, max_bytes=_MAX_COURSE_PACK_JSON_BYTES)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO fabric_course_packs (
                    course_pack_id,
                    version,
                    course_pack_json,
                    installed_at,
                    installed_by
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(course_pack_id, version) DO UPDATE SET
                    course_pack_json = excluded.course_pack_json,
                    installed_at = excluded.installed_at,
                    installed_by = excluded.installed_by
                """,
                (
                    course_pack.coursePackId,
                    course_pack.version,
                    encoded,
                    timestamp.isoformat(),
                    actor_id,
                ),
            )
        return course_pack

    def get_course_pack(self, course_pack_id: str, version: str) -> CoursePack | None:
        row = self._connection.execute(
            """
            SELECT course_pack_json
            FROM fabric_course_packs
            WHERE course_pack_id = ? AND version = ?
            """,
            (course_pack_id, version),
        ).fetchone()
        return None if row is None else _decode_model(CoursePack, row["course_pack_json"])

    def list_course_packs(self) -> tuple[CoursePack, ...]:
        rows = self._connection.execute(
            """
            SELECT course_pack_json
            FROM fabric_course_packs
            ORDER BY course_pack_id, version
            """
        ).fetchall()
        return tuple(_decode_model(CoursePack, row["course_pack_json"]) for row in rows)

    def create_interaction_session(self, session: InteractionSession) -> InteractionSession:
        if self.get_course_pack(session.coursePackId, session.coursePackVersion) is None:
            raise ValueError("Interaction session references an uninstalled course pack")
        encoded = _encode_model(session)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO fabric_sessions (
                    session_id,
                    course_pack_id,
                    course_pack_version,
                    site_id,
                    room_id,
                    mode,
                    state,
                    session_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.sessionId,
                    session.coursePackId,
                    session.coursePackVersion,
                    session.siteId,
                    session.roomId,
                    session.mode.value,
                    session.state.value,
                    encoded,
                    session.createdAt.isoformat(),
                    session.updatedAt.isoformat(),
                ),
            )
        return session

    def get_interaction_session(self, session_id: str) -> InteractionSession | None:
        row = self._connection.execute(
            "SELECT session_json FROM fabric_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return None if row is None else _decode_model(InteractionSession, row["session_json"])

    def list_interaction_sessions(self) -> tuple[InteractionSession, ...]:
        rows = self._connection.execute(
            """
            SELECT session_json
            FROM fabric_sessions
            ORDER BY created_at DESC, session_id
            """
        ).fetchall()
        return tuple(_decode_model(InteractionSession, row["session_json"]) for row in rows)

    def save_interaction_session(self, session: InteractionSession) -> InteractionSession:
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE fabric_sessions
                SET state = ?, session_json = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (
                    session.state.value,
                    _encode_model(session),
                    session.updatedAt.isoformat(),
                    session.sessionId,
                ),
            )
        if cursor.rowcount != 1:
            raise LookupError(f"Interaction session {session.sessionId!r} was not found")
        return session

    def bind_interaction_role(
        self,
        session: InteractionSession,
        binding: RoleBinding,
    ) -> InteractionSession:
        bindings = [item for item in session.roleBindings if item.role != binding.role]
        bindings.append(binding)
        bindings.sort(key=lambda item: item.role)
        updated = session.model_copy(
            update={"roleBindings": bindings, "updatedAt": binding.assignedAt}
        )
        with self._fabric_immediate_transaction():
            self._connection.execute(
                """
                INSERT INTO fabric_role_bindings (
                    session_id,
                    role,
                    node_id,
                    required_capability,
                    binding_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id, role) DO UPDATE SET
                    node_id = excluded.node_id,
                    required_capability = excluded.required_capability,
                    binding_json = excluded.binding_json
                """,
                (
                    session.sessionId,
                    binding.role,
                    binding.nodeId,
                    binding.requiredCapability,
                    _encode_model(binding),
                ),
            )
            self._connection.execute(
                """
                UPDATE fabric_sessions
                SET state = ?, session_json = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (
                    updated.state.value,
                    _encode_model(updated),
                    updated.updatedAt.isoformat(),
                    updated.sessionId,
                ),
            )
        return updated

    def append_fabric_event(
        self,
        event: FabricEventEnvelope,
        *,
        received_at: datetime,
    ) -> StoredFabricEvent | None:
        timestamp = _aware_utc(received_at, field_name="received_at")
        _validate_fabric_event_for_persistence(event)
        encoded = _encode_model(event)
        with self._fabric_immediate_transaction():
            existing = self._connection.execute(
                "SELECT stream_sequence, event_json FROM fabric_events WHERE message_id = ?",
                (str(event.messageId),),
            ).fetchone()
            if existing is not None:
                return None
            sequence_owner = self._connection.execute(
                """
                SELECT message_id
                FROM fabric_events
                WHERE source_node_id = ? AND source_sequence = ?
                """,
                (event.sourceNodeId, event.sequence),
            ).fetchone()
            if sequence_owner is not None:
                raise FabricSequenceConflict(
                    f"Node {event.sourceNodeId!r} reused sequence {event.sequence}"
                )
            cursor = self._connection.execute(
                """
                INSERT INTO fabric_events (
                    message_id,
                    session_id,
                    source_node_id,
                    source_sequence,
                    topic,
                    event_json,
                    received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.messageId),
                    event.sessionId,
                    event.sourceNodeId,
                    event.sequence,
                    event.topic,
                    encoded,
                    timestamp.isoformat(),
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not assign a Fabric event sequence")
            stream_sequence = int(cursor.lastrowid)
        return StoredFabricEvent(stream_sequence=stream_sequence, event=event)

    def list_fabric_events(
        self,
        *,
        session_id: str | None = None,
        after_stream_sequence: int = 0,
        limit: int = FABRIC_PAGE_LIMIT,
        latest: bool = False,
    ) -> tuple[StoredFabricEvent, ...]:
        if not 1 <= limit <= FABRIC_PAGE_LIMIT:
            raise ValueError(f"limit must be between 1 and {FABRIC_PAGE_LIMIT}")
        clauses = ["stream_sequence > ?"]
        parameters: list[object] = [after_stream_sequence]
        if session_id is not None:
            clauses.append("session_id = ?")
            parameters.append(session_id)
        parameters.append(limit)
        order = "DESC" if latest else "ASC"
        rows = self._connection.execute(
            f"""
            SELECT stream_sequence, event_json
            FROM fabric_events
            WHERE {" AND ".join(clauses)}
            ORDER BY stream_sequence {order}
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        if latest:
            rows.reverse()
        return tuple(
            StoredFabricEvent(
                stream_sequence=int(row["stream_sequence"]),
                event=_decode_model(FabricEventEnvelope, row["event_json"]),
            )
            for row in rows
        )

    def claim_fabric_command(
        self,
        command: FabricResolvedCommand,
    ) -> tuple[FabricResolvedCommand, bool]:
        encoded = _encode_model(command)
        with self._fabric_immediate_transaction():
            existing = self._connection.execute(
                """
                SELECT command_json
                FROM fabric_commands
                WHERE idempotency_key = ?
                """,
                (command.idempotencyKey,),
            ).fetchone()
            if existing is not None:
                return _decode_model(FabricResolvedCommand, existing["command_json"]), False
            self._connection.execute(
                """
                INSERT INTO fabric_commands (
                    command_id,
                    request_message_id,
                    idempotency_key,
                    session_id,
                    target_node_id,
                    action,
                    priority,
                    command_json,
                    requested_at,
                    expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(command.commandId),
                    str(command.requestMessageId),
                    command.idempotencyKey,
                    command.sessionId,
                    command.targetNodeId,
                    command.action,
                    command.priority.value,
                    encoded,
                    command.requestedAt.isoformat(),
                    command.expiresAt.isoformat(),
                ),
            )
        return command, True

    def get_fabric_command(self, command_id: str) -> FabricResolvedCommand | None:
        row = self._connection.execute(
            "SELECT command_json FROM fabric_commands WHERE command_id = ?",
            (command_id,),
        ).fetchone()
        return None if row is None else _decode_model(FabricResolvedCommand, row["command_json"])

    def append_fabric_lifecycle(
        self,
        lifecycle: FabricCommandLifecycleEvent,
    ) -> StoredFabricLifecycle | None:
        encoded = _encode_model(lifecycle)
        with self._fabric_immediate_transaction():
            existing = self._connection.execute(
                """
                SELECT stream_sequence
                FROM fabric_command_lifecycle
                WHERE message_id = ?
                """,
                (str(lifecycle.messageId),),
            ).fetchone()
            if existing is not None:
                return None
            cursor = self._connection.execute(
                """
                INSERT INTO fabric_command_lifecycle (
                    message_id,
                    command_id,
                    stage,
                    lifecycle_json,
                    occurred_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(lifecycle.messageId),
                    str(lifecycle.commandId),
                    lifecycle.stage.value,
                    encoded,
                    lifecycle.occurredAt.isoformat(),
                ),
            )
            if lifecycle.stage in _TERMINAL_COMMAND_STAGES:
                self._connection.execute(
                    """
                    UPDATE fabric_commands
                    SET terminal_stage = ?, terminal_at = ?
                    WHERE command_id = ?
                    """,
                    (
                        lifecycle.stage.value,
                        lifecycle.occurredAt.isoformat(),
                        str(lifecycle.commandId),
                    ),
                )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not assign a command lifecycle sequence")
            stream_sequence = int(cursor.lastrowid)
        return StoredFabricLifecycle(stream_sequence=stream_sequence, lifecycle=lifecycle)

    def list_fabric_lifecycle(
        self,
        *,
        command_id: str | None = None,
        after_stream_sequence: int = 0,
        limit: int = FABRIC_PAGE_LIMIT,
    ) -> tuple[StoredFabricLifecycle, ...]:
        if not 1 <= limit <= FABRIC_PAGE_LIMIT:
            raise ValueError(f"limit must be between 1 and {FABRIC_PAGE_LIMIT}")
        clauses = ["stream_sequence > ?"]
        parameters: list[object] = [after_stream_sequence]
        if command_id is not None:
            clauses.append("command_id = ?")
            parameters.append(command_id)
        parameters.append(limit)
        rows = self._connection.execute(
            f"""
            SELECT stream_sequence, lifecycle_json
            FROM fabric_command_lifecycle
            WHERE {" AND ".join(clauses)}
            ORDER BY stream_sequence
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return tuple(
            StoredFabricLifecycle(
                stream_sequence=int(row["stream_sequence"]),
                lifecycle=_decode_model(
                    FabricCommandLifecycleEvent,
                    row["lifecycle_json"],
                ),
            )
            for row in rows
        )

    def acquire_fabric_control_lease(
        self,
        command: FabricResolvedCommand,
        *,
        at: datetime,
    ) -> FabricLeaseDecision:
        timestamp = _aware_utc(at, field_name="at")
        with self._fabric_immediate_transaction():
            self._connection.execute(
                """
                UPDATE fabric_control_leases
                SET released_at = ?, release_reason = 'expired'
                WHERE released_at IS NULL AND expires_at <= ?
                """,
                (timestamp.isoformat(), timestamp.isoformat()),
            )
            current = self._connection.execute(
                """
                SELECT lease_id, session_id, priority
                FROM fabric_control_leases
                WHERE node_id = ? AND capability = ? AND released_at IS NULL
                """,
                (command.targetNodeId, command.action),
            ).fetchone()
            preempted: str | None = None
            if current is not None:
                current_priority = FabricCommandPriority(current["priority"])
                same_session = current["session_id"] == command.sessionId
                may_preempt = _PRIORITY_RANK[command.priority] > _PRIORITY_RANK[current_priority]
                if not same_session and not may_preempt:
                    return FabricLeaseDecision(
                        acquired=False,
                        holder_session_id=str(current["session_id"]),
                    )
                preempted = None if same_session else str(current["session_id"])
                self._connection.execute(
                    """
                    UPDATE fabric_control_leases
                    SET released_at = ?, release_reason = ?
                    WHERE lease_id = ?
                    """,
                    (
                        timestamp.isoformat(),
                        "renewed" if same_session else "priority_preempted",
                        current["lease_id"],
                    ),
                )
            self._connection.execute(
                """
                INSERT INTO fabric_control_leases (
                    lease_id,
                    node_id,
                    capability,
                    session_id,
                    owner_node_id,
                    priority,
                    acquired_at,
                    expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    command.targetNodeId,
                    command.action,
                    command.sessionId,
                    command.sourceNodeId,
                    command.priority.value,
                    timestamp.isoformat(),
                    command.expiresAt.isoformat(),
                ),
            )
        return FabricLeaseDecision(acquired=True, preempted_session_id=preempted)

    def release_fabric_session_leases(
        self,
        session_id: str,
        *,
        at: datetime,
        reason: str,
    ) -> None:
        timestamp = _aware_utc(at, field_name="at")
        with self._connection:
            self._connection.execute(
                """
                UPDATE fabric_control_leases
                SET released_at = ?, release_reason = ?
                WHERE session_id = ? AND released_at IS NULL
                """,
                (timestamp.isoformat(), reason, session_id),
            )

    def claim_flow_debounce(
        self,
        *,
        session_id: str,
        flow_id: str,
        source_node_id: str,
        at: datetime,
        debounce: timedelta,
    ) -> bool:
        timestamp = _aware_utc(at, field_name="at")
        with self._fabric_immediate_transaction():
            row = self._connection.execute(
                """
                SELECT last_triggered_at
                FROM fabric_flow_debounce
                WHERE session_id = ? AND flow_id = ? AND source_node_id = ?
                """,
                (session_id, flow_id, source_node_id),
            ).fetchone()
            if row is not None:
                last = _aware_utc(
                    datetime.fromisoformat(row["last_triggered_at"]),
                    field_name="persisted last_triggered_at",
                )
                if timestamp - last < debounce:
                    return False
            self._connection.execute(
                """
                INSERT INTO fabric_flow_debounce (
                    session_id,
                    flow_id,
                    source_node_id,
                    last_triggered_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, flow_id, source_node_id) DO UPDATE SET
                    last_triggered_at = excluded.last_triggered_at
                """,
                (session_id, flow_id, source_node_id, timestamp.isoformat()),
            )
        return True

    def upsert_fabric_identity(self, record: FabricIdentityRecord) -> FabricIdentityRecord:
        created_at = _aware_utc(record.created_at, field_name="record.created_at")
        expires_at = _aware_utc(record.expires_at, field_name="record.expires_at")
        if expires_at <= created_at:
            raise ValueError("Identity expiry must follow creation")
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO fabric_identities (
                    identity_id,
                    actor_type,
                    roles_json,
                    permissions_json,
                    site_id,
                    room_id,
                    session_id,
                    token_hash,
                    created_at,
                    expires_at,
                    revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(identity_id) DO UPDATE SET
                    actor_type = excluded.actor_type,
                    roles_json = excluded.roles_json,
                    permissions_json = excluded.permissions_json,
                    site_id = excluded.site_id,
                    room_id = excluded.room_id,
                    session_id = excluded.session_id,
                    token_hash = excluded.token_hash,
                    expires_at = excluded.expires_at,
                    revoked_at = excluded.revoked_at
                """,
                (
                    record.identity_id,
                    record.actor_type,
                    _encode_strings(record.roles),
                    _encode_strings(record.permissions),
                    record.site_id,
                    record.room_id,
                    record.session_id,
                    record.token_hash,
                    created_at.isoformat(),
                    expires_at.isoformat(),
                    record.revoked_at.isoformat() if record.revoked_at is not None else None,
                ),
            )
        return record

    def find_fabric_identity_by_hash(self, token_hash: str) -> FabricIdentityRecord | None:
        row = self._connection.execute(
            "SELECT * FROM fabric_identities WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        return None if row is None else _identity_from_row(row)

    def get_fabric_identity(self, identity_id: str) -> FabricIdentityRecord | None:
        row = self._connection.execute(
            "SELECT * FROM fabric_identities WHERE identity_id = ?",
            (identity_id,),
        ).fetchone()
        return None if row is None else _identity_from_row(row)

    def revoke_fabric_identity(self, identity_id: str, *, at: datetime) -> bool:
        timestamp = _aware_utc(at, field_name="at")
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE fabric_identities
                SET revoked_at = ?
                WHERE identity_id = ? AND revoked_at IS NULL
                """,
                (timestamp.isoformat(), identity_id),
            )
        return cursor.rowcount == 1

    def record_fabric_audit(
        self,
        *,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str | None,
        outcome: str,
        correlation_id: str | None,
        occurred_at: datetime,
        details: dict[str, object] | None = None,
    ) -> FabricAuditRecord:
        if outcome not in {"succeeded", "denied", "failed"}:
            raise ValueError("Unsupported Fabric audit outcome")
        timestamp = _aware_utc(occurred_at, field_name="occurred_at")
        safe_details = details or {}
        details_json = _encode_json(safe_details)
        record = FabricAuditRecord(
            audit_id=str(uuid4()),
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            correlation_id=correlation_id,
            occurred_at=timestamp,
            details=safe_details,
        )
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO fabric_audit (
                    audit_id,
                    actor_id,
                    action,
                    resource_type,
                    resource_id,
                    outcome,
                    correlation_id,
                    occurred_at,
                    details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.audit_id,
                    record.actor_id,
                    record.action,
                    record.resource_type,
                    record.resource_id,
                    record.outcome,
                    record.correlation_id,
                    record.occurred_at.isoformat(),
                    details_json,
                ),
            )
        return record

    def list_fabric_audit(self, *, limit: int = FABRIC_PAGE_LIMIT) -> tuple[FabricAuditRecord, ...]:
        if not 1 <= limit <= FABRIC_PAGE_LIMIT:
            raise ValueError(f"limit must be between 1 and {FABRIC_PAGE_LIMIT}")
        rows = self._connection.execute(
            """
            SELECT *
            FROM fabric_audit
            ORDER BY occurred_at DESC, audit_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return tuple(
            FabricAuditRecord(
                audit_id=str(row["audit_id"]),
                actor_id=str(row["actor_id"]),
                action=str(row["action"]),
                resource_type=str(row["resource_type"]),
                resource_id=row["resource_id"],
                outcome=str(row["outcome"]),
                correlation_id=row["correlation_id"],
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
                details=json.loads(row["details_json"]),
            )
            for row in rows
        )

    @contextmanager
    def _fabric_immediate_transaction(self) -> Iterator[None]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()


def _identity_from_row(row: sqlite3.Row) -> FabricIdentityRecord:
    return FabricIdentityRecord(
        identity_id=str(row["identity_id"]),
        actor_type=str(row["actor_type"]),
        roles=_decode_strings(row["roles_json"]),
        permissions=_decode_strings(row["permissions_json"]),
        site_id=row["site_id"],
        room_id=row["room_id"],
        session_id=row["session_id"],
        token_hash=str(row["token_hash"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
        revoked_at=(
            datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] is not None else None
        ),
    )


def _encode_model(model: BaseModel, *, max_bytes: int = _MAX_JSON_BYTES) -> str:
    return _encode_json(model.model_dump(mode="json", exclude_none=True), max_bytes=max_bytes)


def _decode_model(model_type: type[ModelT], encoded: str) -> ModelT:
    return model_type.model_validate_json(encoded)


def _encode_json(value: object, *, max_bytes: int = _MAX_JSON_BYTES) -> str:
    _validate_json_value(value, depth=0)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ValueError(f"Fabric record exceeds the {max_bytes // 1_024} KiB persistence limit")
    return encoded


def _encode_strings(values: Sequence[str]) -> str:
    if len(values) != len(set(values)):
        raise ValueError("Persisted identity values must be unique")
    return json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))


def _decode_strings(encoded: str) -> tuple[str, ...]:
    value = json.loads(encoded)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("Persisted identity values are invalid")
    return tuple(value)


def _validate_fabric_event_for_persistence(event: FabricEventEnvelope) -> None:
    if event.dataClassification.value in {"sensitive_raw", "secret"}:
        raise ValueError("Raw sensitive data and secrets cannot enter Fabric persistence")
    payload = event.payload.model_dump(mode="json")
    _validate_json_value(payload, depth=0)


def _validate_json_value(value: object, *, depth: int) -> None:
    if depth > 8:
        raise ValueError("Fabric JSON exceeds the maximum nesting depth")
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Fabric JSON numbers must be finite")
        return
    if isinstance(value, str):
        if len(value.encode("utf-8")) > 32_768:
            raise ValueError("One Fabric string exceeds the 32 KiB limit")
        return
    if isinstance(value, list):
        if len(value) > 1024:
            raise ValueError("One Fabric array exceeds 1024 items")
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 128:
            raise ValueError("One Fabric object exceeds 128 fields")
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Fabric object keys must be strings")
            canonical = "".join(character for character in key.lower() if character.isalnum())
            if any(term in canonical for term in _FORBIDDEN_PERSISTED_TERMS):
                raise ValueError("Raw media and credentials cannot enter Fabric persistence")
            _validate_json_value(item, depth=depth + 1)
        return
    raise ValueError(f"Unsupported Fabric JSON value type: {type(value).__name__}")


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a UTC offset")
    return value.astimezone(UTC)
