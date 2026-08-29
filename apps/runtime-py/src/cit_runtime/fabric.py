"""Capability registry, sessions, bounded flows, arbitration, and command lifecycle."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cit_protocol import (
    CapabilityDescriptor,
    CoursePack,
    CreateInteractionSessionRequest,
    DeviceDescriptor,
    FabricCommandLifecycleEvent,
    FabricCommandLifecycleStage,
    FabricCommandPriority,
    FabricCommandRequest,
    FabricEventEnvelope,
    FabricNodeConnectionState,
    FabricNodeHealthState,
    FabricResolvedCommand,
    FabricSafetyClassification,
    FabricSessionMode,
    FabricSessionState,
    FlowRecipe,
    HealthReport,
    IntegrationNode,
    InteractionSession,
    PluginManifest,
    RoleBinding,
)

from .fabric_course import validate_course_pack
from .fabric_persistence import FabricSequenceConflict, StoredFabricEvent, StoredFabricLifecycle
from .fabric_repository import SQLiteFabricRepository

_NODE_LEASE_TTL = timedelta(seconds=15)
_MAX_CLOCK_SKEW = timedelta(seconds=30)
_MAX_FLOW_COMMAND_TTL = timedelta(seconds=2)
_ARM_INACTIVITY_TTL = timedelta(minutes=2)
# A tutor console that is open and polling counts as attendance. While a class
# is attended an armed session may run for a full teaching block; the moment
# attendance stops it falls back to the unattended window above.
_ARM_ATTENDED_TTL = timedelta(hours=6)
_BRAIN_FLIGHT_DEMO_ARM = "mobility.flight.brain_demo.arm"
_BRAIN_FLIGHT_DEMO_SAFETY_PROFILE = "classroom-drone-monitoring"
_FLEET_SEQUENCE_ARM = "mobility.flight.fleet_sequence.arm"
_FLEET_SEQUENCE_START = "mobility.flight.fleet_sequence.start"
_FLEET_SEQUENCE_SAFETY_PROFILE = "classroom-drone-monitoring"
_MANUAL_FLIGHT_TAKEOFF = "mobility.flight.takeoff"
_MANUAL_FLIGHT_MOVE = "mobility.flight.move"
_MANUAL_FLIGHT_ROTATE = "mobility.flight.rotate"
_MANUAL_FLIGHT_SAFETY_PROFILE = "classroom-drone-monitoring"
_COMMAND_TRANSITIONS: dict[
    FabricCommandLifecycleStage,
    frozenset[FabricCommandLifecycleStage],
] = {
    FabricCommandLifecycleStage.PROPOSED: frozenset(
        {FabricCommandLifecycleStage.VALIDATED, FabricCommandLifecycleStage.REJECTED}
    ),
    FabricCommandLifecycleStage.VALIDATED: frozenset(
        {FabricCommandLifecycleStage.AUTHORIZED, FabricCommandLifecycleStage.REJECTED}
    ),
    FabricCommandLifecycleStage.AUTHORIZED: frozenset(
        {
            FabricCommandLifecycleStage.DISPATCHED,
            FabricCommandLifecycleStage.REJECTED,
            FabricCommandLifecycleStage.FAILED,
        }
    ),
    FabricCommandLifecycleStage.DISPATCHED: frozenset(
        {
            FabricCommandLifecycleStage.ACCEPTED,
            FabricCommandLifecycleStage.RUNNING,
            FabricCommandLifecycleStage.SUCCEEDED,
            FabricCommandLifecycleStage.FAILED,
            FabricCommandLifecycleStage.CANCELLED,
            FabricCommandLifecycleStage.TIMED_OUT,
            FabricCommandLifecycleStage.REJECTED,
        }
    ),
    FabricCommandLifecycleStage.ACCEPTED: frozenset(
        {
            FabricCommandLifecycleStage.RUNNING,
            FabricCommandLifecycleStage.SUCCEEDED,
            FabricCommandLifecycleStage.FAILED,
            FabricCommandLifecycleStage.CANCELLED,
            FabricCommandLifecycleStage.TIMED_OUT,
        }
    ),
    FabricCommandLifecycleStage.RUNNING: frozenset(
        {
            FabricCommandLifecycleStage.SUCCEEDED,
            FabricCommandLifecycleStage.FAILED,
            FabricCommandLifecycleStage.CANCELLED,
            FabricCommandLifecycleStage.TIMED_OUT,
        }
    ),
    FabricCommandLifecycleStage.SUCCEEDED: frozenset(),
    FabricCommandLifecycleStage.FAILED: frozenset(),
    FabricCommandLifecycleStage.CANCELLED: frozenset(),
    FabricCommandLifecycleStage.TIMED_OUT: frozenset(),
    FabricCommandLifecycleStage.REJECTED: frozenset(),
}


class FabricNotFoundError(LookupError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class FabricConflictError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class FabricPolicyError(PermissionError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class FabricDispatchOutcome:
    accepted: bool
    terminal_stage: FabricCommandLifecycleStage | None = None
    code: str | None = None
    message: str | None = None
    details: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class FabricIngestResult:
    stored_event: StoredFabricEvent | None
    duplicate: bool
    command_lifecycle: tuple[FabricCommandLifecycleEvent, ...]


FabricDispatcher = Callable[
    [FabricResolvedCommand, IntegrationNode],
    Awaitable[FabricDispatchOutcome],
]


class InteractionFabric:
    def __init__(
        self,
        repository: SQLiteFabricRepository,
        *,
        clock: Callable[[], datetime],
        session_id_factory: Callable[[], str] | None = None,
        command_id_factory: Callable[[], str] | None = None,
        allow_physical: bool = False,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._session_id_factory = session_id_factory or (lambda: str(uuid4()))
        self._command_id_factory = command_id_factory or (lambda: str(uuid4()))
        self._allow_physical = allow_physical
        self._dispatcher: FabricDispatcher | None = None
        self._last_attended_at: datetime | None = None

    def set_dispatcher(self, dispatcher: FabricDispatcher | None) -> None:
        self._dispatcher = dispatcher

    def install_course_pack(self, course_pack: CoursePack, *, actor_id: str) -> CoursePack:
        validate_course_pack(course_pack)
        return self._repository.install_course_pack(
            course_pack,
            actor_id=actor_id,
            at=self._clock(),
        )

    def list_course_packs(self) -> tuple[CoursePack, ...]:
        return self._repository.list_course_packs()

    def register_plugin_and_nodes(
        self,
        manifest: PluginManifest,
        nodes: Iterable[IntegrationNode],
    ) -> tuple[IntegrationNode, ...]:
        at = self._clock()
        exact_nodes = tuple(nodes)
        if not exact_nodes:
            raise ValueError("At least one Fabric node is required")
        self._validate_manifest(manifest)
        self._repository.register_fabric_plugin(manifest, at=at)
        registered: list[IntegrationNode] = []
        seen_node_ids: set[str] = set()
        for node in exact_nodes:
            if node.nodeId in seen_node_ids:
                raise ValueError(f"Duplicate node ID {node.nodeId!r} in registration")
            seen_node_ids.add(node.nodeId)
            self._validate_node_against_manifest(node, manifest)
            registered.append(
                self._repository.upsert_fabric_node(
                    node,
                    at=at,
                    lease_ttl=_NODE_LEASE_TTL,
                )
            )
        return tuple(registered)

    def report_health(self, report: HealthReport) -> IntegrationNode:
        updated = self._repository.update_fabric_health(
            report,
            at=self._clock(),
            lease_ttl=_NODE_LEASE_TTL,
        )
        if (
            updated.connectionState
            in {
                FabricNodeConnectionState.unavailable,
                FabricNodeConnectionState.disconnected,
                FabricNodeConnectionState.unsafe,
            }
            or updated.healthState is FabricNodeHealthState.unhealthy
        ):
            self._disarm_sessions_for_nodes(
                (updated.nodeId,),
                reason="node_health_lost",
            )
        return updated

    def expire_nodes(self) -> tuple[str, ...]:
        expired = self._repository.expire_fabric_nodes(at=self._clock())
        self._disarm_sessions_for_nodes(expired, reason="node_lease_expired")
        return expired

    def note_console_attendance(self) -> None:
        """Record that an instructor console is currently watching this room."""

        self._last_attended_at = self._clock()

    def _armed_session_ttl(self, now: datetime) -> timedelta:
        if (
            self._last_attended_at is not None
            and now - self._last_attended_at <= _ARM_INACTIVITY_TTL
        ):
            return _ARM_ATTENDED_TTL
        return _ARM_INACTIVITY_TTL

    def expire_armed_sessions(self) -> tuple[str, ...]:
        now = self._clock()
        arm_ttl = self._armed_session_ttl(now)
        expired: list[str] = []
        for session in self._repository.list_interaction_sessions():
            if (
                session.mode is FabricSessionMode.physical
                and session.armed
                and session.updatedAt + arm_ttl <= now
            ):
                self._save_disarmed_session(
                    session,
                    at=now,
                    reason="inactivity_timeout",
                )
                expired.append(session.sessionId)
        return tuple(expired)

    def disconnect_nodes(self, node_ids: Iterable[str]) -> tuple[str, ...]:
        at = self._clock()
        disconnected: list[str] = []
        for node_id in tuple(node_ids):
            node = self._repository.get_fabric_node(node_id)
            if node is None:
                continue
            updated = node.model_copy(
                update={
                    "connectionState": FabricNodeConnectionState.disconnected,
                    "healthState": FabricNodeHealthState.unknown,
                    "lastSeenAt": at,
                }
            )
            self._repository.upsert_fabric_node(
                updated,
                at=at,
                lease_ttl=_NODE_LEASE_TTL,
            )
            disconnected.append(node_id)
        self._disarm_sessions_for_nodes(disconnected, reason="adapter_disconnected")
        return tuple(disconnected)

    def list_nodes(
        self,
        *,
        site_id: str | None = None,
        room_id: str | None = None,
        capability: str | None = None,
    ) -> tuple[IntegrationNode, ...]:
        nodes = self._repository.list_fabric_nodes(site_id=site_id, room_id=room_id)
        if capability is None:
            return nodes
        return tuple(node for node in nodes if _node_has_capability(node, capability))

    def create_session(
        self,
        request: CreateInteractionSessionRequest,
        *,
        actor_id: str,
    ) -> InteractionSession:
        course_pack = self._repository.get_course_pack(
            request.coursePackId,
            request.coursePackVersion,
        )
        if course_pack is None:
            raise FabricNotFoundError(
                "COURSE_PACK_NOT_FOUND",
                "The exact course-pack version is not installed",
            )
        if request.mode is FabricSessionMode.physical and not self._allow_physical:
            raise FabricPolicyError(
                "PHYSICAL_EXECUTION_DISABLED",
                "Physical Fabric sessions are disabled in this reference slice",
            )
        at = self._clock()
        session = InteractionSession.model_validate(
            {
                "schemaVersion": "1.0",
                "sessionId": self._session_id_factory(),
                "coursePackId": request.coursePackId,
                "coursePackVersion": request.coursePackVersion,
                "siteId": request.siteId,
                "roomId": request.roomId,
                "mode": request.mode.value,
                "state": "draft",
                "armed": False,
                "disarmReason": "session_created",
                "participantIds": [
                    participant.root for participant in (request.participantIds or [])
                ],
                "roleBindings": [],
                "safetyProfile": course_pack.safetyProfile,
                "createdAt": at,
                "updatedAt": at,
                "createdBy": actor_id,
            }
        )
        return self._repository.create_interaction_session(session)

    def ensure_monitoring_session(
        self,
        course_pack: CoursePack,
        *,
        site_id: str,
        room_id: str,
        mode: FabricSessionMode,
        actor_id: str,
    ) -> tuple[InteractionSession, bool]:
        """Reuse one active-preferred monitoring session with dormant safe flows."""

        if not self._monitoring_flows_are_dormant_when_unarmed(course_pack):
            raise ValueError(
                "A monitoring session flow must target an optional role and include "
                "every deterministic unarmed-safety guard"
            )
        reusable_states = {
            FabricSessionState.active,
            FabricSessionState.paused,
            FabricSessionState.ready,
            FabricSessionState.draft,
        }
        state_order = {
            FabricSessionState.active: 0,
            FabricSessionState.paused: 1,
            FabricSessionState.ready: 2,
            FabricSessionState.draft: 3,
        }
        candidates = [
            session
            for session in self.list_sessions()
            if session.coursePackId == course_pack.coursePackId
            and session.coursePackVersion == course_pack.version
            and session.siteId == site_id
            and session.roomId == room_id
            and session.mode is mode
            and session.state in reusable_states
            and not session.armed
        ]
        if candidates:
            return min(candidates, key=lambda item: state_order[item.state]), True
        return (
            self.create_session(
                CreateInteractionSessionRequest.model_validate(
                    {
                        "coursePackId": course_pack.coursePackId,
                        "coursePackVersion": course_pack.version,
                        "siteId": site_id,
                        "roomId": room_id,
                        "mode": mode.value,
                    }
                ),
                actor_id=actor_id,
            ),
            False,
        )

    def assign_role(
        self,
        session_id: str,
        role: str,
        node_id: str,
        *,
        actor_id: str,
    ) -> InteractionSession:
        session = self._require_session(session_id)
        node = self._require_node(node_id)
        if node.siteId != session.siteId or node.roomId != session.roomId:
            raise FabricPolicyError(
                "NODE_SCOPE_MISMATCH",
                "The node is outside the interaction session's site or room",
            )
        course_pack = self._require_course_pack(session)
        requirement = next((item for item in course_pack.roles if item.role == role), None)
        if requirement is None:
            raise FabricNotFoundError("ROLE_NOT_FOUND", f"Course pack has no role {role!r}")
        required_options = [capability.root for capability in requirement.oneOfCapabilities]
        compatible = [
            capability for capability in required_options if _node_has_capability(node, capability)
        ]
        if not compatible:
            raise FabricConflictError(
                "CAPABILITY_MISMATCH",
                f"Node {node_id!r} does not satisfy role {role!r}",
            )
        ordinary_role_change_states = {
            FabricSessionState.draft,
            FabricSessionState.ready,
            FabricSessionState.paused,
        }
        active_monitoring_extension = (
            session.state is FabricSessionState.active
            and not session.armed
            and self._monitoring_flows_are_dormant_when_unarmed(course_pack)
            and requirement.optional
            and all(
                _capability_descriptor(node, capability).safetyClassification
                in {
                    FabricSafetyClassification.none,
                    FabricSafetyClassification.informational,
                }
                for capability in compatible
            )
        )
        if session.state not in ordinary_role_change_states and not active_monitoring_extension:
            raise FabricConflictError(
                "SESSION_ACTIVE",
                "Roles can be changed during an active session only for an unarmed, "
                "no-flow, optional informational monitoring role",
            )
        if session.mode is FabricSessionMode.simulation:
            unsafe_capabilities = [
                capability
                for capability in compatible
                if _capability_descriptor(node, capability).safetyClassification
                in {
                    FabricSafetyClassification.bounded_physical,
                    FabricSafetyClassification.flight,
                    FabricSafetyClassification.electrical,
                }
            ]
            if unsafe_capabilities and not node.simulated:
                raise FabricPolicyError(
                    "SIMULATOR_REQUIRED",
                    "A simulation session cannot bind a real physical-actuation capability",
                )
        if node.connectionState not in {
            FabricNodeConnectionState.connected,
            FabricNodeConnectionState.degraded,
        }:
            raise FabricConflictError("NODE_UNAVAILABLE", "Role target node is unavailable")
        at = self._clock()
        binding = RoleBinding.model_validate(
            {
                "role": role,
                "nodeId": node_id,
                "requiredCapability": compatible[0],
                "assignedAt": at,
                "assignedBy": actor_id,
            }
        )
        updated = self._repository.bind_interaction_role(session, binding)
        if active_monitoring_extension:
            return updated
        if self._required_roles_are_bound(updated, course_pack):
            updated = updated.model_copy(
                update={"state": FabricSessionState.ready, "updatedAt": at}
            )
            return self._repository.save_interaction_session(updated)
        return updated

    def transition_session(
        self,
        session_id: str,
        action: str,
        *,
        actor_id: str = "system.runtime",
    ) -> InteractionSession:
        session = self._require_session(session_id)
        at = self._clock()
        if action == "arm":
            if session.mode is not FabricSessionMode.physical:
                raise FabricPolicyError(
                    "SIMULATION_ARMING_DENIED",
                    "Simulation sessions do not arm physical outputs",
                )
            if not self._allow_physical:
                raise FabricPolicyError(
                    "PHYSICAL_EXECUTION_DISABLED",
                    "Physical Fabric sessions are disabled in this reference slice",
                )
            if session.state not in {FabricSessionState.ready, FabricSessionState.paused}:
                raise FabricConflictError(
                    "INVALID_SESSION_TRANSITION",
                    "Only a ready or paused physical session can be armed",
                )
            self._validate_bound_nodes(session)
            updated = session.model_copy(
                update={
                    "armed": True,
                    "armedAt": at,
                    "armedBy": actor_id,
                    "disarmReason": None,
                    "updatedAt": at,
                }
            )
        elif action == "disarm":
            return self._save_disarmed_session(
                session,
                at=at,
                reason="instructor_disarm",
            )
        elif action == "start":
            if session.state not in {FabricSessionState.ready, FabricSessionState.paused}:
                raise FabricConflictError(
                    "INVALID_SESSION_TRANSITION",
                    f"Cannot start a session from {session.state.value!r}",
                )
            self._validate_bound_nodes(session)
            if (
                session.mode is FabricSessionMode.physical
                and not session.armed
                and not self._is_unarmed_monitoring_session(session)
            ):
                raise FabricPolicyError(
                    "SESSION_NOT_ARMED",
                    "A physical session must be explicitly armed before start",
                )
            updated = session.model_copy(
                update={
                    "state": FabricSessionState.active,
                    "startedAt": session.startedAt or at,
                    "updatedAt": at,
                }
            )
        elif action == "pause":
            if session.state is not FabricSessionState.active:
                raise FabricConflictError(
                    "INVALID_SESSION_TRANSITION",
                    "Only an active session can be paused",
                )
            updated = session.model_copy(
                update={
                    "state": FabricSessionState.paused,
                    "armed": False,
                    "armedAt": None,
                    "armedBy": None,
                    "disarmReason": "session_paused",
                    "updatedAt": at,
                }
            )
            self._repository.release_fabric_session_leases(
                session_id,
                at=at,
                reason="session_paused",
            )
        elif action in {"stop", "emergency_stop"}:
            if session.state in {
                FabricSessionState.stopped,
                FabricSessionState.emergency_stopped,
                FabricSessionState.failed,
            }:
                return session
            state = (
                FabricSessionState.emergency_stopped
                if action == "emergency_stop"
                else FabricSessionState.stopped
            )
            updated = session.model_copy(
                update={
                    "state": state,
                    "armed": False,
                    "armedAt": None,
                    "armedBy": None,
                    "disarmReason": f"session_{action}",
                    "updatedAt": at,
                    "endedAt": at,
                }
            )
            self._repository.release_fabric_session_leases(
                session_id,
                at=at,
                reason=f"session_{action}",
            )
        else:
            raise ValueError(f"Unsupported session action {action!r}")
        return self._repository.save_interaction_session(updated)

    async def ingest_event(self, event: FabricEventEnvelope) -> FabricIngestResult:
        now = self._clock()
        timestamp = _aware_utc(event.timestamp, field_name="event.timestamp")
        if timestamp > now + _MAX_CLOCK_SKEW:
            raise FabricPolicyError("EVENT_FROM_FUTURE", "Event timestamp is too far in the future")
        if timestamp + timedelta(milliseconds=event.ttlMs) <= now:
            raise FabricPolicyError("EVENT_EXPIRED", "Event TTL has expired")
        session = self._require_session(event.sessionId)
        session_accepts_semantic_events = session.state in {
            FabricSessionState.active,
            FabricSessionState.paused,
        }
        inactive_safe_state_result = (
            not session_accepts_semantic_events
            and self._is_verified_inactive_safe_state_result(event)
        )
        if not session_accepts_semantic_events and not inactive_safe_state_result:
            raise FabricConflictError(
                "SESSION_NOT_ACTIVE",
                "Semantic events require an active or paused session",
            )
        node = self._require_node(event.sourceNodeId)
        if node.siteId != event.siteId or node.roomId != event.roomId:
            raise FabricPolicyError(
                "EVENT_SCOPE_MISMATCH",
                "Event site or room does not match its registered source node",
            )
        if event.siteId != session.siteId or event.roomId != session.roomId:
            raise FabricPolicyError(
                "SESSION_SCOPE_MISMATCH",
                "Event site or room does not match its interaction session",
            )
        if not any(binding.nodeId == node.nodeId for binding in session.roleBindings):
            raise FabricPolicyError(
                "NODE_NOT_ASSIGNED",
                "Event source is not assigned to an interaction-session role",
            )
        if not _node_publishes(node, event.sourceCapability):
            raise FabricPolicyError(
                "CAPABILITY_NOT_PUBLISHED",
                "Source node does not publish the declared capability",
            )
        if event.topic != event.sourceCapability:
            raise FabricPolicyError(
                "TOPIC_CAPABILITY_MISMATCH",
                "Event topic must equal the published source capability in version 1",
            )
        if event.dataClassification not in set(node.dataClassifications):
            raise FabricPolicyError(
                "DATA_CLASSIFICATION_MISMATCH",
                "Event data classification is not advertised by the source node",
            )
        if session.state is FabricSessionState.paused:
            # Keep the adapter transport healthy while a tutor pauses a lesson,
            # but do not persist, replay, or route observations made while paused.
            return FabricIngestResult(
                stored_event=None,
                duplicate=False,
                command_lifecycle=(),
            )
        try:
            stored = self._repository.append_fabric_event(event, received_at=now)
        except FabricSequenceConflict as error:
            raise FabricConflictError("EVENT_SEQUENCE_CONFLICT", str(error)) from error
        except ValueError as error:
            raise FabricPolicyError(
                "EVENT_DATA_POLICY_DENIED",
                "Event payload violates Fabric persistence policy",
            ) from error
        if stored is None:
            return FabricIngestResult(
                stored_event=None,
                duplicate=True,
                command_lifecycle=(),
            )
        if inactive_safe_state_result:
            # A safe-state command remains available before start and after a
            # stop. Record its verified result for UI/audit state, but never
            # route inactive-session output telemetry into lesson flows.
            return FabricIngestResult(
                stored_event=stored,
                duplicate=False,
                command_lifecycle=(),
            )
        course_pack = self._require_course_pack(session)
        lifecycles: list[FabricCommandLifecycleEvent] = []
        routed: list[tuple[FlowRecipe, FabricCommandRequest]] = []
        for flow in course_pack.flows:
            request = self._request_from_flow(flow, event, session, now=now)
            if request is None:
                continue
            routed.append((flow, request))

        completed_parallel_groups: set[str] = set()
        for flow, request in routed:
            parallel_group = flow.parallelGroup
            if parallel_group is None:
                lifecycles.extend(await self.submit_command(request))
                continue
            if parallel_group in completed_parallel_groups:
                continue
            completed_parallel_groups.add(parallel_group)
            group_requests = [
                candidate_request
                for candidate_flow, candidate_request in routed
                if candidate_flow.parallelGroup == parallel_group
            ]
            group_results = await asyncio.gather(
                *(self.submit_command(candidate) for candidate in group_requests)
            )
            for result in group_results:
                lifecycles.extend(result)
        return FabricIngestResult(
            stored_event=stored,
            duplicate=False,
            command_lifecycle=tuple(lifecycles),
        )

    async def submit_command(
        self,
        request: FabricCommandRequest,
    ) -> tuple[FabricCommandLifecycleEvent, ...]:
        now = self._clock()
        session = self._require_session(request.sessionId)
        binding = next(
            (item for item in session.roleBindings if item.role == request.target.role),
            None,
        )
        if binding is None:
            raise FabricConflictError(
                "ROLE_NOT_ASSIGNED",
                f"Role {request.target.role!r} is not assigned",
            )
        node = self._require_node(binding.nodeId)
        requested_at = _aware_utc(request.requestedAt, field_name="request.requestedAt")
        expires_at = requested_at + timedelta(milliseconds=request.ttlMs)
        resolved = FabricResolvedCommand.model_validate(
            {
                "commandId": self._command_id_factory(),
                "requestMessageId": request.messageId,
                "schemaVersion": "1.0",
                "sessionId": request.sessionId,
                "targetNodeId": binding.nodeId,
                "action": request.action,
                "parameters": request.parameters.model_dump(mode="json"),
                "priority": request.priority.value,
                "idempotencyKey": request.idempotencyKey,
                "requestedAt": requested_at,
                "expiresAt": expires_at,
                "safetyProfile": request.safetyProfile,
                "correlationId": request.correlationId,
                "causationId": request.causationId,
                "sourceNodeId": request.sourceNodeId,
            }
        )
        exact_command, is_new = self._repository.claim_fabric_command(resolved)
        if not is_new:
            return tuple(
                item.lifecycle
                for item in self._repository.list_fabric_lifecycle(
                    command_id=str(exact_command.commandId)
                )
            )
        lifecycle: list[FabricCommandLifecycleEvent] = []
        lifecycle.append(self._append_lifecycle(resolved, FabricCommandLifecycleStage.PROPOSED))
        denial = self._validate_command(resolved, session, node, now=now)
        if denial is not None:
            code, message = denial
            lifecycle.append(
                self._append_lifecycle(
                    resolved,
                    FabricCommandLifecycleStage.REJECTED,
                    code=code,
                    message=message,
                )
            )
            return tuple(lifecycle)
        lifecycle.append(self._append_lifecycle(resolved, FabricCommandLifecycleStage.VALIDATED))
        lease = self._repository.acquire_fabric_control_lease(resolved, at=now)
        if not lease.acquired:
            lifecycle.append(
                self._append_lifecycle(
                    resolved,
                    FabricCommandLifecycleStage.REJECTED,
                    code="CONTROL_LEASE_CONFLICT",
                    message="A higher or equal priority session owns this capability",
                    details={"holderSessionId": lease.holder_session_id or "unknown"},
                )
            )
            return tuple(lifecycle)
        lifecycle.append(
            self._append_lifecycle(
                resolved,
                FabricCommandLifecycleStage.AUTHORIZED,
                details={
                    "preemptedSessionId": lease.preempted_session_id,
                }
                if lease.preempted_session_id is not None
                else None,
            )
        )
        dispatcher = self._dispatcher
        if dispatcher is None:
            lifecycle.append(
                self._append_lifecycle(
                    resolved,
                    FabricCommandLifecycleStage.FAILED,
                    code="ADAPTER_TRANSPORT_UNAVAILABLE",
                    message="No adapter transport is available for the target node",
                )
            )
            return tuple(lifecycle)
        try:
            outcome = await dispatcher(resolved, node)
        except Exception:
            lifecycle.append(
                self._append_lifecycle(
                    resolved,
                    FabricCommandLifecycleStage.FAILED,
                    code="ADAPTER_DISPATCH_FAILED",
                    message="The adapter transport failed before accepting the command",
                )
            )
            return tuple(lifecycle)
        if not outcome.accepted:
            lifecycle.append(
                self._append_lifecycle(
                    resolved,
                    outcome.terminal_stage or FabricCommandLifecycleStage.REJECTED,
                    code=outcome.code or "ADAPTER_REJECTED",
                    message=outcome.message or "The adapter rejected the command",
                    details=outcome.details,
                )
            )
            return tuple(lifecycle)
        lifecycle.append(self._append_lifecycle(resolved, FabricCommandLifecycleStage.DISPATCHED))
        if outcome.terminal_stage is not None:
            lifecycle.append(
                self._append_lifecycle(
                    resolved,
                    outcome.terminal_stage,
                    code=outcome.code,
                    message=outcome.message,
                    details=outcome.details,
                )
            )
        return tuple(lifecycle)

    def accept_adapter_lifecycle(
        self,
        lifecycle: FabricCommandLifecycleEvent,
    ) -> StoredFabricLifecycle | None:
        command = self._repository.get_fabric_command(str(lifecycle.commandId))
        if command is None:
            raise FabricNotFoundError("COMMAND_NOT_FOUND", "Adapter command is unknown")
        if lifecycle.requestMessageId != command.requestMessageId:
            raise FabricPolicyError(
                "COMMAND_IDENTITY_MISMATCH",
                "Adapter lifecycle request identity does not match the command",
            )
        if lifecycle.targetNodeId != command.targetNodeId:
            raise FabricPolicyError(
                "COMMAND_TARGET_MISMATCH",
                "Adapter lifecycle target does not match the exact command target",
            )
        if (
            lifecycle.sessionId != command.sessionId
            or lifecycle.correlationId != command.correlationId
        ):
            raise FabricPolicyError(
                "COMMAND_CONTEXT_MISMATCH",
                "Adapter lifecycle context does not match the command",
            )
        existing = self._repository.list_fabric_lifecycle(command_id=str(command.commandId))
        if not existing:
            raise FabricConflictError("COMMAND_STATE_MISSING", "Command has no lifecycle state")
        current = existing[-1].lifecycle.stage
        if lifecycle.stage not in _COMMAND_TRANSITIONS[current]:
            raise FabricConflictError(
                "INVALID_COMMAND_TRANSITION",
                f"Command cannot transition from {current.value} to {lifecycle.stage.value}",
            )
        return self._repository.append_fabric_lifecycle(lifecycle)

    def list_events(
        self,
        *,
        session_id: str | None,
        after_sequence: int,
        limit: int,
        latest: bool = False,
    ) -> tuple[StoredFabricEvent, ...]:
        return self._repository.list_fabric_events(
            session_id=session_id,
            after_stream_sequence=after_sequence,
            limit=limit,
            latest=latest,
        )

    def list_lifecycle(
        self,
        *,
        command_id: str | None,
        after_sequence: int,
        limit: int,
    ) -> tuple[StoredFabricLifecycle, ...]:
        return self._repository.list_fabric_lifecycle(
            command_id=command_id,
            after_stream_sequence=after_sequence,
            limit=limit,
        )

    def _is_verified_inactive_safe_state_result(self, event: FabricEventEnvelope) -> bool:
        if (
            event.topic
            not in {
                "power.switch.state",
                "telemetry.power.electrical",
            }
            or event.causationId is None
        ):
            return False
        payload = event.payload.model_dump(mode="json")
        if payload.get("source") != "command":
            return False
        if event.topic == "power.switch.state" and payload.get("on") is not False:
            return False
        command = self._repository.get_fabric_command(event.causationId)
        if command is None or not _is_safe_state_command(command):
            return False
        if (
            command.action != "power.switch.set"
            or command.sessionId != event.sessionId
            or command.targetNodeId != event.sourceNodeId
            or str(command.correlationId) != str(event.correlationId)
        ):
            return False
        lifecycle = self._repository.list_fabric_lifecycle(
            command_id=str(command.commandId),
            limit=10,
        )
        return bool(
            lifecycle and lifecycle[-1].lifecycle.stage is FabricCommandLifecycleStage.SUCCEEDED
        )

    def get_session(self, session_id: str) -> InteractionSession:
        return self._require_session(session_id)

    def list_sessions(self) -> tuple[InteractionSession, ...]:
        return self._repository.list_interaction_sessions()

    def can_start_unarmed(self, session_id: str) -> bool:
        session = self._require_session(session_id)
        if session.mode is FabricSessionMode.simulation:
            return True
        return self._is_unarmed_monitoring_session(session)

    def _validate_command(
        self,
        command: FabricResolvedCommand,
        session: InteractionSession,
        node: IntegrationNode,
        *,
        now: datetime,
    ) -> tuple[str, str] | None:
        if command.requestedAt > now + _MAX_CLOCK_SKEW:
            return "COMMAND_FROM_FUTURE", "Command request time is too far in the future"
        if command.expiresAt <= now:
            return "COMMAND_EXPIRED", "Command TTL has expired"
        if session.state is not FabricSessionState.active and not _is_safe_state_command(command):
            return "SESSION_NOT_ACTIVE", "Only an active session can dispatch this command"
        if command.safetyProfile != session.safetyProfile:
            return "SAFETY_PROFILE_MISMATCH", "Command safety profile differs from the session"
        if node.connectionState is not FabricNodeConnectionState.connected:
            return "NODE_UNAVAILABLE", "Target node is not connected and healthy enough to command"
        capability = _consumed_capability(node, command.action)
        if capability is None:
            return "CAPABILITY_NOT_CONSUMED", "Target node does not consume the requested action"
        requires_physical_safety = (
            capability.safetyClassification
            in {
                FabricSafetyClassification.bounded_physical,
                FabricSafetyClassification.flight,
                FabricSafetyClassification.electrical,
            }
            and not node.simulated
        )
        if requires_physical_safety and not _is_safe_state_command(command):
            if not session.armed:
                return "SESSION_NOT_ARMED", "Physical outputs require an armed session"
            if not self._allow_physical:
                return "PHYSICAL_EXECUTION_DISABLED", "Physical command execution is disabled"
            if command.priority is FabricCommandPriority.autonomous_agent:
                return "AGENT_PHYSICAL_CONTROL_DENIED", "Autonomous agents cannot command hardware"
            if capability.safetyClassification is FabricSafetyClassification.flight:
                if not (
                    _is_bounded_brain_flight_demo_arm(command)
                    or _is_bounded_fleet_sequence_command(command)
                    or _is_bounded_manual_tello_command(command)
                ):
                    return (
                        "SAFETY_PROFILE_NOT_IMPLEMENTED",
                        "Only explicitly confirmed bounded flight workflows are enabled",
                    )
            if (
                capability.safetyClassification is FabricSafetyClassification.electrical
                and command.action != "power.switch.set"
            ):
                return (
                    "SAFETY_PROFILE_NOT_IMPLEMENTED",
                    "Only the exact boolean smart-plug electrical command is enabled",
                )
        parameter_error = _validate_command_parameters(command, capability)
        if parameter_error is not None:
            return "INVALID_COMMAND_PARAMETERS", parameter_error
        return None

    def _request_from_flow(
        self,
        flow: FlowRecipe,
        event: FabricEventEnvelope,
        session: InteractionSession,
        *,
        now: datetime,
    ) -> FabricCommandRequest | None:
        if not flow.enabled or flow.trigger.event != event.topic:
            return None
        if flow.trigger.minimumConfidence is not None and (
            event.confidence is None or event.confidence < flow.trigger.minimumConfidence
        ):
            return None
        payload = event.payload.model_dump(mode="json")
        expected = (
            flow.trigger.payloadEquals.model_dump(mode="json")
            if flow.trigger.payloadEquals is not None
            else {}
        )
        if any(payload.get(key) != value for key, value in expected.items()):
            return None
        debounce = timedelta(milliseconds=flow.trigger.debounceMs or 0)
        if debounce and not self._repository.claim_flow_debounce(
            session_id=session.sessionId,
            flow_id=flow.flowId,
            source_node_id=event.sourceNodeId,
            at=now,
            debounce=debounce,
        ):
            return None
        if "session_is_active" in {guard.value for guard in flow.guards} and (
            session.state is not FabricSessionState.active
        ):
            return None
        binding = next(
            (item for item in session.roleBindings if item.role == flow.target.role),
            None,
        )
        if binding is None:
            return None
        target = self._repository.get_fabric_node(binding.nodeId)
        if target is None:
            return None
        if "target_is_connected" in {guard.value for guard in flow.guards} and (
            target.connectionState is not FabricNodeConnectionState.connected
        ):
            return None
        if (
            "target_is_armed" in {guard.value for guard in flow.guards}
            and target.physical
            and not session.armed
        ):
            return None
        parameters = flow.command.fixedParameters.model_dump(mode="json")
        for parameter_binding in flow.command.parameterBindings:
            if parameter_binding.payloadField not in payload:
                return None
            parameters[parameter_binding.parameter] = payload[parameter_binding.payloadField]
        remaining = event.timestamp + timedelta(milliseconds=event.ttlMs) - now
        ttl = min(max(remaining, timedelta(milliseconds=1)), _MAX_FLOW_COMMAND_TTL)
        correlation_id = event.correlationId or str(event.messageId)
        return FabricCommandRequest.model_validate(
            {
                "messageId": str(uuid4()),
                "schemaVersion": "1.0",
                "messageType": "command.requested",
                "action": flow.command.action,
                "target": {"role": flow.target.role},
                "sessionId": session.sessionId,
                "parameters": parameters,
                "priority": "lesson_automation",
                "idempotencyKey": (f"flow:{session.sessionId}:{flow.flowId}:{event.messageId}"),
                "requestedAt": now,
                "ttlMs": max(1, int(ttl / timedelta(milliseconds=1))),
                "safetyProfile": flow.safetyProfile,
                "correlationId": correlation_id,
                "causationId": str(event.messageId),
                "sourceNodeId": event.sourceNodeId,
            }
        )

    def _append_lifecycle(
        self,
        command: FabricResolvedCommand,
        stage: FabricCommandLifecycleStage,
        *,
        code: str | None = None,
        message: str | None = None,
        details: dict[str, object] | None = None,
    ) -> FabricCommandLifecycleEvent:
        lifecycle = FabricCommandLifecycleEvent.model_validate(
            {
                "messageId": str(uuid4()),
                "schemaVersion": "1.0",
                "messageType": "command.lifecycle",
                "commandId": command.commandId,
                "requestMessageId": command.requestMessageId,
                "sessionId": command.sessionId,
                "targetNodeId": command.targetNodeId,
                "stage": stage.value,
                "occurredAt": self._clock(),
                "correlationId": command.correlationId,
                "code": code,
                "message": message,
                "details": details or {},
            }
        )
        self._repository.append_fabric_lifecycle(lifecycle)
        return lifecycle

    def _require_session(self, session_id: str) -> InteractionSession:
        session = self._repository.get_interaction_session(session_id)
        if session is None:
            raise FabricNotFoundError(
                "INTERACTION_SESSION_NOT_FOUND",
                f"Interaction session {session_id!r} does not exist",
            )
        return session

    def _require_node(self, node_id: str) -> IntegrationNode:
        node = self._repository.get_fabric_node(node_id)
        if node is None:
            raise FabricNotFoundError(
                "FABRIC_NODE_NOT_FOUND",
                f"Fabric node {node_id!r} does not exist",
            )
        return node

    def _require_course_pack(self, session: InteractionSession) -> CoursePack:
        course_pack = self._repository.get_course_pack(
            session.coursePackId,
            session.coursePackVersion,
        )
        if course_pack is None:
            raise FabricNotFoundError(
                "COURSE_PACK_NOT_FOUND",
                "Interaction session course pack is no longer installed",
            )
        return course_pack

    def _disarm_sessions_for_nodes(
        self,
        node_ids: Iterable[str],
        *,
        reason: str,
    ) -> None:
        exact_node_ids = frozenset(node_ids)
        if not exact_node_ids:
            return
        at = self._clock()
        for session in self._repository.list_interaction_sessions():
            if session.mode is not FabricSessionMode.physical or not session.armed:
                continue
            if not any(binding.nodeId in exact_node_ids for binding in session.roleBindings):
                continue
            state = (
                FabricSessionState.emergency_stopped
                if session.state is FabricSessionState.active
                else session.state
            )
            self._save_disarmed_session(
                session,
                at=at,
                reason=reason,
                state=state,
            )

    def _save_disarmed_session(
        self,
        session: InteractionSession,
        *,
        at: datetime,
        reason: str,
        state: FabricSessionState | None = None,
    ) -> InteractionSession:
        next_state = state or session.state
        updated = session.model_copy(
            update={
                "state": next_state,
                "armed": False,
                "armedAt": None,
                "armedBy": None,
                "disarmReason": reason,
                "updatedAt": at,
                "endedAt": (
                    at if next_state is FabricSessionState.emergency_stopped else session.endedAt
                ),
            }
        )
        self._repository.release_fabric_session_leases(
            session.sessionId,
            at=at,
            reason=reason,
        )
        return self._repository.save_interaction_session(updated)

    @staticmethod
    def _validate_manifest(manifest: PluginManifest) -> None:
        capabilities = [
            *(capability.name for capability in manifest.publishedCapabilities),
            *(capability.name for capability in manifest.consumedCapabilities),
        ]
        if not capabilities:
            raise ValueError("Plugin manifest must advertise at least one capability")
        if len(capabilities) != len(set(capabilities)):
            raise ValueError("Plugin manifest capability names must be unique")
        permissions = [permission.root for permission in manifest.requiredPermissions]
        if len(permissions) != len(set(permissions)):
            raise ValueError("Plugin required permissions must be unique")
        classifications = [item.value for item in manifest.dataClassifications]
        if len(classifications) != len(set(classifications)):
            raise ValueError("Plugin data classifications must be unique")

    @staticmethod
    def _validate_node_against_manifest(
        node: IntegrationNode,
        manifest: PluginManifest,
    ) -> None:
        if node.pluginId != manifest.pluginId or node.pluginVersion != manifest.pluginVersion:
            raise ValueError("Node plugin identity does not match its registration manifest")
        published = {(item.name, item.version) for item in manifest.publishedCapabilities}
        consumed = {(item.name, item.version) for item in manifest.consumedCapabilities}
        if any((item.name, item.version) not in published for item in node.publishedCapabilities):
            raise ValueError("Node publishes a capability absent from its plugin manifest")
        if any((item.name, item.version) not in consumed for item in node.consumedCapabilities):
            raise ValueError("Node consumes a capability absent from its plugin manifest")
        if not node.publishedCapabilities and not node.consumedCapabilities:
            raise ValueError("Node must publish or consume at least one capability")
        if node.physical and node.simulated:
            raise ValueError("A node instance cannot be both physical and simulated")
        has_real_actuation = any(
            item.safetyClassification
            in {
                FabricSafetyClassification.bounded_physical,
                FabricSafetyClassification.flight,
                FabricSafetyClassification.electrical,
            }
            for item in node.consumedCapabilities
        )
        if has_real_actuation and not node.physical and not node.simulated:
            raise ValueError(
                "A non-simulated node consuming physical capabilities must be marked physical"
            )
        classifications = [item.value for item in node.dataClassifications]
        if len(classifications) != len(set(classifications)):
            raise ValueError("Node data classifications must be unique")

    @staticmethod
    def _required_roles_are_bound(
        session: InteractionSession,
        course_pack: CoursePack,
    ) -> bool:
        assigned = {binding.role for binding in session.roleBindings}
        return all(
            requirement.optional or requirement.role in assigned
            for requirement in course_pack.roles
        )

    def _validate_bound_nodes(self, session: InteractionSession) -> None:
        course_pack = self._require_course_pack(session)
        if not self._required_roles_are_bound(session, course_pack):
            raise FabricConflictError(
                "REQUIRED_ROLES_UNASSIGNED",
                "All required course roles must be assigned before start",
            )
        for binding in session.roleBindings:
            node = self._require_node(binding.nodeId)
            if node.connectionState is not FabricNodeConnectionState.connected:
                raise FabricConflictError(
                    "NODE_UNAVAILABLE",
                    f"Role {binding.role!r} is assigned to an unavailable node",
                )
            if not _node_has_capability(node, binding.requiredCapability):
                raise FabricConflictError(
                    "CAPABILITY_MISMATCH",
                    f"Role {binding.role!r} no longer has its required capability",
                )

    def _is_unarmed_monitoring_session(self, session: InteractionSession) -> bool:
        """Allow observation without silently authorizing physical actuation.

        A physical session may run unarmed only when every assigned role uses an
        informational capability and every enabled flow is deterministically
        dormant until the target is armed. Safe-state commands such as land remain
        available through the ordinary command gate; takeoff, movement, and
        electrical activation remain denied.
        """

        course_pack = self._require_course_pack(session)
        if not session.roleBindings or not self._monitoring_flows_are_dormant_when_unarmed(
            course_pack
        ):
            return False
        for binding in session.roleBindings:
            node = self._require_node(binding.nodeId)
            descriptor = _capability_descriptor(node, binding.requiredCapability)
            if descriptor.safetyClassification not in {
                FabricSafetyClassification.none,
                FabricSafetyClassification.informational,
            }:
                return False
        return True

    @staticmethod
    def _monitoring_flows_are_dormant_when_unarmed(course_pack: CoursePack) -> bool:
        required_guards = {
            "session_is_active",
            "role_is_assigned",
            "target_is_connected",
            "target_is_armed",
            "instructor_override_is_clear",
        }
        roles = {requirement.role: requirement for requirement in course_pack.roles}
        for flow in course_pack.flows:
            if not flow.enabled:
                continue
            target = roles.get(flow.target.role)
            guards = {guard.value for guard in flow.guards}
            if target is None or not target.optional or not required_guards <= guards:
                return False
        return True


def legacy_simulation_manifest_and_nodes(
    descriptors: Iterable[DeviceDescriptor],
    *,
    at: datetime,
    host_id: str = "local-runtime",
    site_id: str = "local-site",
    room_id: str = "local-room",
) -> tuple[PluginManifest, tuple[IntegrationNode, ...]]:
    exact_descriptors = tuple(descriptors)
    published_by_name: dict[str, CapabilityDescriptor] = {}
    consumed_by_name: dict[str, CapabilityDescriptor] = {}
    node_capabilities: dict[str, tuple[list[CapabilityDescriptor], list[CapabilityDescriptor]]] = {}
    for descriptor in exact_descriptors:
        published: list[CapabilityDescriptor] = []
        consumed: list[CapabilityDescriptor] = []
        for capability_root in descriptor.capabilities:
            name = capability_root.root
            direction = "publish" if _legacy_capability_is_published(name) else "consume"
            capability = CapabilityDescriptor.model_validate(
                {
                    "name": name,
                    "version": "1.0",
                    "direction": direction,
                    "latencyClass": (
                        "interactive"
                        if name.startswith(("drive.", "motor.", "input."))
                        else "ui_feedback"
                    ),
                    "safetyClassification": "none",
                    "dataClassification": "operational",
                    "constraints": {},
                }
            )
            if direction == "publish":
                published.append(capability)
                published_by_name.setdefault(name, capability)
            else:
                consumed.append(capability)
                consumed_by_name.setdefault(name, capability)
        node_capabilities[descriptor.deviceId] = (published, consumed)
    manifest = PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": "cit.simulator.milestone1",
            "pluginVersion": "1.0.0",
            "runtimeVersion": "python-3.11",
            "displayName": "CIT Milestone 1 simulators",
            "adapterMode": "in_process",
            "configurationSchema": {},
            "publishedCapabilities": list(published_by_name.values()),
            "consumedCapabilities": list(consumed_by_name.values()),
            "requiredPermissions": [],
            "safetyClassification": "none",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "included",
            "description": "Compatibility nodes for existing in-memory fake adapters.",
        }
    )
    nodes: list[IntegrationNode] = []
    for descriptor in exact_descriptors:
        published, consumed = node_capabilities[descriptor.deviceId]
        nodes.append(
            IntegrationNode.model_validate(
                {
                    "schemaVersion": "1.0",
                    "nodeId": descriptor.deviceId,
                    "pluginId": manifest.pluginId,
                    "pluginVersion": manifest.pluginVersion,
                    "runtimeVersion": manifest.runtimeVersion,
                    "hostId": host_id,
                    "siteId": site_id,
                    "roomId": room_id,
                    "displayName": descriptor.displayName,
                    "connectionState": "connected",
                    "healthState": "healthy",
                    "physical": False,
                    "simulated": True,
                    "publishedCapabilities": published,
                    "consumedCapabilities": consumed,
                    "configurationSchema": {},
                    "safetyClassification": "none",
                    "dataClassifications": ["operational"],
                    "simulatorAvailable": True,
                    "requiredPermissions": [],
                    "lastSeenAt": at,
                    "metadata": {
                        "legacyDeviceId": descriptor.deviceId,
                        "model": descriptor.model,
                        "transport": "simulation",
                    },
                }
            )
        )
    return manifest, tuple(nodes)


def _node_has_capability(node: IntegrationNode, capability: str) -> bool:
    return _node_publishes(node, capability) or _consumed_capability(node, capability) is not None


def _node_publishes(node: IntegrationNode, capability: str) -> bool:
    return any(item.name == capability for item in node.publishedCapabilities)


def _consumed_capability(
    node: IntegrationNode,
    capability: str,
) -> CapabilityDescriptor | None:
    return next((item for item in node.consumedCapabilities if item.name == capability), None)


def _capability_descriptor(
    node: IntegrationNode,
    capability: str,
) -> CapabilityDescriptor:
    descriptor = next(
        (
            item
            for item in (*node.publishedCapabilities, *node.consumedCapabilities)
            if item.name == capability
        ),
        None,
    )
    if descriptor is None:
        raise ValueError(f"Node does not advertise capability {capability!r}")
    return descriptor


def _legacy_capability_is_published(capability: str) -> bool:
    return capability.startswith(("input.", "sensor.", "telemetry."))


def _is_stop_action(action: str) -> bool:
    return action.startswith("safety.") or action.endswith((".stop", ".land", ".disarm"))


def _is_safe_state_command(command: FabricResolvedCommand) -> bool:
    if _is_stop_action(command.action):
        return True
    parameters = command.parameters.model_dump(mode="json")
    return bool(command.action == "power.switch.set" and parameters == {"on": False})


def _is_bounded_brain_flight_demo_arm(command: FabricResolvedCommand) -> bool:
    if (
        command.action != _BRAIN_FLIGHT_DEMO_ARM
        or command.safetyProfile != _BRAIN_FLIGHT_DEMO_SAFETY_PROFILE
        or command.priority is not FabricCommandPriority.instructor_override
    ):
        return False
    parameters = command.parameters.model_dump(mode="json")
    return all(
        parameters.get(name) is True
        for name in ("instructorPresent", "flightAreaClear", "emergencyPlanReady")
    )


def _is_bounded_fleet_sequence_command(command: FabricResolvedCommand) -> bool:
    if command.safetyProfile != _FLEET_SEQUENCE_SAFETY_PROFILE:
        return False
    parameters = command.parameters.model_dump(mode="json")
    if command.action == _FLEET_SEQUENCE_START:
        return (
            not parameters
            and command.priority
            in {
                FabricCommandPriority.instructor_override,
                FabricCommandPriority.lesson_automation,
            }
            and (
                command.priority is FabricCommandPriority.instructor_override
                or command.sourceNodeId is not None
            )
        )
    if (
        command.action != _FLEET_SEQUENCE_ARM
        or command.priority is not FabricCommandPriority.instructor_override
    ):
        return False
    required = {
        "droneIds",
        "allowedSourceNodeIds",
        "launchIntervalSeconds",
        "minimumBatteryPercent",
        "instructorPresent",
        "flightAreaClear",
        "emergencyPlanReady",
        "independentRoutesConfirmed",
    }
    launch_interval = parameters.get("launchIntervalSeconds")
    minimum_battery = parameters.get("minimumBatteryPercent")
    return (
        set(parameters) == required
        and all(
            parameters.get(name) is True
            for name in (
                "instructorPresent",
                "flightAreaClear",
                "emergencyPlanReady",
                "independentRoutesConfirmed",
            )
        )
        and _is_bounded_identifier_list(parameters.get("droneIds"), minimum=1, maximum=8)
        and _is_bounded_identifier_list(
            parameters.get("allowedSourceNodeIds"), minimum=0, maximum=8
        )
        and not isinstance(launch_interval, bool)
        and isinstance(launch_interval, (int, float))
        and 1 <= launch_interval <= 15
        and not isinstance(minimum_battery, bool)
        and isinstance(minimum_battery, int)
        and 20 <= minimum_battery <= 100
    )


def _is_bounded_manual_tello_command(command: FabricResolvedCommand) -> bool:
    if (
        command.safetyProfile != _MANUAL_FLIGHT_SAFETY_PROFILE
        or command.priority is not FabricCommandPriority.instructor_override
    ):
        return False
    parameters = command.parameters.model_dump(mode="json")
    confirmations = {
        "instructorPresent",
        "flightAreaClear",
        "emergencyPlanReady",
    }
    if not all(parameters.get(name) is True for name in confirmations):
        return False
    if command.action == _MANUAL_FLIGHT_TAKEOFF:
        return set(parameters) == confirmations
    if command.action == _MANUAL_FLIGHT_MOVE:
        distance = parameters.get("distanceCentimeters")
        return (
            set(parameters) == confirmations | {"direction", "distanceCentimeters"}
            and parameters.get("direction") in {"forward", "back", "left", "right", "up", "down"}
            and type(distance) is int
            and 20 <= distance <= 50
        )
    if command.action == _MANUAL_FLIGHT_ROTATE:
        degrees = parameters.get("degrees")
        return (
            set(parameters) == confirmations | {"clockwise", "degrees"}
            and type(parameters.get("clockwise")) is bool
            and type(degrees) is int
            and 1 <= degrees <= 90
        )
    return False


def _is_bounded_identifier_list(
    value: object,
    *,
    minimum: int,
    maximum: int,
) -> bool:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        return False
    if len(value) != len(set(item for item in value if isinstance(item, str))):
        return False
    return all(
        isinstance(item, str)
        and 1 <= len(item) <= 128
        and item[0].isascii()
        and item[0].isalnum()
        and all(
            character.isascii() and (character.isalnum() or character in "._-")
            for character in item
        )
        for item in value
    )


def _validate_command_parameters(
    command: FabricResolvedCommand,
    capability: CapabilityDescriptor,
) -> str | None:
    parameters = command.parameters.model_dump(mode="json")
    if command.action == "agent.prompt.submit":
        if set(parameters) != {"prompt"}:
            return "Agent prompt command requires exactly one prompt parameter"
        prompt = parameters.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return "Agent prompt must be a non-empty string"
        if len(prompt.encode("utf-8")) > 32_768:
            return "Agent prompt exceeds the 32 KiB Fabric limit"
    if command.action == "display.text.render":
        if set(parameters) != {"text"}:
            return "Display command requires exactly one text parameter"
        text = parameters.get("text")
        if not isinstance(text, str) or not text.strip():
            return "Display text must be a non-empty string"
        if len(text.encode("utf-8")) > 4096:
            return "Display text exceeds the 4 KiB Fabric limit"
    if command.action == "power.switch.set":
        if set(parameters) != {"on"} or type(parameters.get("on")) is not bool:
            return "Smart-plug command requires exactly one boolean 'on' parameter"
    constraints = capability.constraints.model_dump(mode="json")
    argument_limits = constraints.get("arguments")
    if isinstance(argument_limits, dict):
        unknown = set(parameters) - set(argument_limits)
        if unknown:
            return f"Unsupported parameters: {', '.join(sorted(unknown))}"
        for name, bounds in argument_limits.items():
            if name not in parameters or not isinstance(bounds, dict):
                continue
            value = parameters[name]
            if bounds.get("type") == "boolean":
                if type(value) is not bool:
                    return f"Parameter {name!r} must be boolean"
                continue
            if bounds.get("type") == "string":
                if not isinstance(value, str):
                    return f"Parameter {name!r} must be a string"
                choices = bounds.get("enum")
                if isinstance(choices, list) and value not in choices:
                    return f"Parameter {name!r} is not an allowed value"
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return f"Parameter {name!r} must be numeric"
            minimum = bounds.get("minimum")
            maximum = bounds.get("maximum")
            if isinstance(minimum, (int, float)) and value < minimum:
                return f"Parameter {name!r} is below its minimum"
            if isinstance(maximum, (int, float)) and value > maximum:
                return f"Parameter {name!r} exceeds its maximum"
    return None


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a UTC offset")
    return value.astimezone(UTC)
