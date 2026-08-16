"""The one path from an intent to an adapter.

Order matters and is fixed: identity is claimed before safety is asked, safety
is asked before a lease is taken, and a lease is held before an adapter is
touched. A command that fails any step never reaches hardware, and every outcome
is audited.

FR-067 emergency controls, FR-072 priority preemption, and FR-070 watchdog
enforcement are driven from here because they must be able to clear queued work
that has already been accepted.
"""

from __future__ import annotations

import heapq
import itertools
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from cit_protocol import CommandResult, DeviceCommandIntent, DeviceEvent, ProtocolError
from cit_safety import (
    CommandDisposition,
    DeviceLeaseConflict,
    InMemoryCommandLedger,
    InMemoryDeviceLeaseRegistry,
    LeaseMode,
)

from .audit import AuditAction, AuditLog, StructuredLogger
from .clock import Clock
from .events import EventRouter
from .registry import DeviceConnectionState, DeviceRegistry
from .sessions import ExecutionMode, SessionRepository, SessionState
from .supervisor import (
    CommandPriority,
    SafetySupervisor,
    WatchdogAction,
    WatchdogExpiry,
)


@dataclass(frozen=True, slots=True)
class Dispatch:
    """What the pipeline decided, and the result if it reached an adapter."""

    accepted: bool
    priority: CommandPriority
    result: CommandResult | None = None
    error: ProtocolError | None = None
    clamped_fields: tuple[str, ...] = ()
    events: tuple[DeviceEvent, ...] = ()


@dataclass(order=True, slots=True)
class _QueueItem:
    priority: int
    tiebreak: int
    command: DeviceCommandIntent = field(compare=False)


class CommandQueue:
    """Bounded priority queue. FR-072 ordering, FR-067 clearing."""

    def __init__(self, *, max_depth: int = 256) -> None:
        if max_depth <= 0:
            raise ValueError("max_depth must be positive")
        self._heap: list[_QueueItem] = []
        self._counter = itertools.count()
        self._max_depth = max_depth

    def __len__(self) -> int:
        return len(self._heap)

    def push(self, command: DeviceCommandIntent, *, priority: CommandPriority) -> None:
        if len(self._heap) >= self._max_depth:
            raise OverflowError("Command queue is full; the runtime is shedding load")
        heapq.heappush(
            self._heap,
            _QueueItem(priority=int(priority), tiebreak=next(self._counter), command=command),
        )

    def pop(self) -> DeviceCommandIntent | None:
        if not self._heap:
            return None
        return heapq.heappop(self._heap).command

    def clear(self, *, device_id: str | None = None) -> int:
        """FR-067. Returns how many queued commands were discarded."""

        if device_id is None:
            cleared = len(self._heap)
            self._heap.clear()
            return cleared
        kept = [item for item in self._heap if item.command.deviceId != device_id]
        cleared = len(self._heap) - len(kept)
        self._heap = kept
        heapq.heapify(self._heap)
        return cleared

    def peek_device_ids(self) -> tuple[str, ...]:
        return tuple(item.command.deviceId for item in sorted(self._heap))


class CommandPipeline:
    """Owns nothing that talks to hardware except through the registry."""

    def __init__(
        self,
        *,
        clock: Clock,
        registry: DeviceRegistry,
        sessions: SessionRepository,
        supervisor: SafetySupervisor,
        router: EventRouter,
        audit: AuditLog,
        logger: StructuredLogger | None = None,
        lease_ttl: timedelta = timedelta(seconds=30),
    ) -> None:
        self._clock = clock
        self._registry = registry
        self._sessions = sessions
        self._supervisor = supervisor
        self._router = router
        self._audit = audit
        self._logger = logger or StructuredLogger()
        self._ledger = InMemoryCommandLedger()
        self._leases = InMemoryDeviceLeaseRegistry()
        self._lease_ttl = lease_ttl
        self.queue = CommandQueue()

    async def submit(self, command: DeviceCommandIntent) -> Dispatch:
        """Run one command through every gate, in order."""

        now = self._clock.now()

        try:
            session = self._sessions.get(command.sessionId)
        except KeyError:
            return self._reject(
                command,
                "DEVICE_NOT_ASSIGNED",
                f"Unknown session {command.sessionId!r}",
                "Start a session before sending commands.",
                now=now,
            )

        if session.is_terminal:
            return self._reject(
                command,
                "SAFETY_POLICY_DENIED",
                f"Session {command.sessionId!r} is {session.state.value}",
                "Start a new session; this one has ended.",
                now=now,
            )

        try:
            device = self._registry.get(command.deviceId)
        except KeyError:
            return self._reject(
                command,
                "DEVICE_NOT_FOUND",
                f"Unknown device {command.deviceId!r}",
                "Run discovery, then bind the device to this session.",
                now=now,
            )

        if device.state is not DeviceConnectionState.CONNECTED:
            return self._reject(
                command,
                "DEVICE_OFFLINE",
                f"Device {command.deviceId!r} is {device.state.value}",
                "Reconnect the device, then arm it again before sending commands.",
                now=now,
            )

        # Identity before safety: an expired or replayed command must not even
        # be evaluated, so a reconnect cannot resurrect old motion (FR-071).
        disposition = self._ledger.claim(command, now=now)
        if disposition is CommandDisposition.EXPIRED:
            return self._reject(
                command,
                "COMMAND_EXPIRED",
                "Command expiry time has passed",
                "Issue a fresh command; expired motion is never replayed.",
                now=now,
            )
        if disposition is CommandDisposition.DUPLICATE:
            return self._reject(
                command,
                "COMMAND_DUPLICATE",
                "Command identity was already claimed",
                "This command already ran; no second execution was performed.",
                now=now,
            )

        physical = session.execution_mode is ExecutionMode.PHYSICAL and device.physical
        verdict = self._supervisor.evaluate(
            command,
            session_device_ids=session.device_bindings,
            physical=physical,
        )
        if not verdict.allowed:
            return self._reject(
                command,
                verdict.code or "SAFETY_POLICY_DENIED",
                verdict.reason or "Denied by the safety supervisor",
                verdict.recovery or "Ask an instructor for help.",
                now=now,
                priority=verdict.priority,
            )

        try:
            self._leases.acquire(
                device_id=command.deviceId,
                session_id=command.sessionId,
                mode=LeaseMode.WRITE,
                now=now,
                ttl=self._lease_ttl,
            )
        except DeviceLeaseConflict as conflict:
            return self._reject(
                command,
                "DEVICE_LEASE_CONFLICT",
                str(conflict),
                "Another session holds this device; ask an instructor to reassign it.",
                now=now,
                priority=verdict.priority,
            )

        bounded = command.model_copy(update={"arguments": dict(verdict.bounded_arguments)})
        if verdict.clamped_fields:
            self._audit.record(
                AuditAction.COMMAND_CLAMPED,
                actor_id=command.source,
                at=now,
                context={
                    "commandId": str(command.commandId),
                    "deviceId": command.deviceId,
                    "clampedFields": list(verdict.clamped_fields),
                    "capability": command.capability,
                },
            )

        adapter = self._registry.adapter(command.deviceId)
        result = await adapter.execute(bounded, now=now)
        events = adapter.drain_events()
        self._router.publish_all(events)

        self._audit.record(
            AuditAction.COMMAND_ACCEPTED,
            actor_id=command.source,
            at=now,
            context={
                "commandId": str(command.commandId),
                "deviceId": command.deviceId,
                "sessionId": command.sessionId,
                "capability": command.capability,
                "action": command.action,
                "priority": int(verdict.priority),
                "result": result.status,
                "executionMode": session.execution_mode.value,
            },
        )
        self._logger.info(
            "command dispatched",
            commandId=str(command.commandId),
            deviceId=command.deviceId,
            result=result.status,
        )

        return Dispatch(
            accepted=result.status in {"accepted", "completed"},
            priority=verdict.priority,
            result=result,
            clamped_fields=verdict.clamped_fields,
            events=events,
        )

    # ------------------------------------------------------- emergency controls

    async def stop_device(self, device_id: str, *, reason: str, actor_id: str) -> int:
        """Stop one device and clear anything queued for it (FR-067)."""

        now = self._clock.now()
        cleared = self.queue.clear(device_id=device_id)
        adapter = self._registry.adapter(device_id)
        await adapter.stop(reason=reason, at=now)
        self._router.publish_all(adapter.drain_events())
        self._supervisor.disarm(device_id)
        self._audit.record(
            AuditAction.EMERGENCY_STOP,
            actor_id=actor_id,
            at=now,
            context={"deviceId": device_id, "reason": reason, "result": str(cleared)},
        )
        return cleared

    async def stop_all(self, *, reason: str, actor_id: str) -> tuple[str, ...]:
        """FR-067 stop-all: every device stops, every queue empties, all disarm."""

        now = self._clock.now()
        self.queue.clear()
        stopped: list[str] = []
        for device in self._registry.list():
            adapter = self._registry.adapter(device.device_id)
            await adapter.stop(reason=reason, at=now)
            self._router.publish_all(adapter.drain_events())
            stopped.append(device.device_id)
        self._supervisor.disarm_all()
        self._audit.record(
            AuditAction.STOP_ALL,
            actor_id=actor_id,
            at=now,
            context={"reason": reason, "result": ",".join(stopped)},
        )
        self._logger.warning("stop-all issued", reason=reason, actorId=actor_id)
        return tuple(stopped)

    async def enforce_watchdogs(self) -> tuple[WatchdogExpiry, ...]:
        """FR-070. A fired watchdog stops or disarms without asking anyone."""

        expiries = self._supervisor.expired_watchdogs()
        now = self._clock.now()
        for expiry in expiries:
            self._audit.record(
                AuditAction.WATCHDOG_FIRED,
                actor_id="system",
                at=now,
                context={
                    "deviceId": expiry.device_id,
                    "watchdog": expiry.kind.value,
                    "action": expiry.action.value,
                    "elapsedSeconds": round(expiry.elapsed_seconds, 4),
                },
            )
            self._supervisor.clear_watchdog(device_id=expiry.device_id, kind=expiry.kind)
            if expiry.action is WatchdogAction.STOP:
                await self.stop_device(
                    expiry.device_id,
                    reason=f"watchdog:{expiry.kind.value}",
                    actor_id="system",
                )
            else:
                self._supervisor.disarm(expiry.device_id)
        return expiries

    async def handle_disconnect(self, device_id: str, *, reason: str) -> None:
        """FR-066 step 7 and FR-087: a disconnect disarms and clears the queue."""

        now = self._clock.now()
        self.queue.clear(device_id=device_id)
        self._supervisor.disarm(device_id)
        self._registry.mark_failed(device_id, reason=reason, at=now)
        for session in self._sessions.active_for_device(device_id):
            if session.state is not SessionState.DISCONNECTED:
                self._sessions.save(
                    session.transition(SessionState.DISCONNECTED, at=now, reason=reason)
                )
        self._audit.record(
            AuditAction.DEVICE_DISCONNECTED,
            actor_id="system",
            at=now,
            context={"deviceId": device_id, "reason": reason},
        )

    # ------------------------------------------------------------------ helpers

    def _reject(
        self,
        command: DeviceCommandIntent,
        code: str,
        message: str,
        recovery: str,
        *,
        now: datetime,
        priority: CommandPriority = CommandPriority.STUDENT_COMMAND,
    ) -> Dispatch:
        error = ProtocolError.model_validate(
            {
                "code": code,
                "message": message,
                "deviceId": command.deviceId,
                "sessionId": command.sessionId,
                "correlationId": str(command.commandId),
                "recoverySuggestion": recovery,
            }
        )
        self._audit.record(
            AuditAction.COMMAND_DENIED,
            actor_id=command.source,
            at=now,
            context={
                "commandId": str(command.commandId),
                "deviceId": command.deviceId,
                "sessionId": command.sessionId,
                "code": code,
                "reason": message,
                "capability": command.capability,
            },
        )
        self._logger.warning("command denied", code=code, deviceId=command.deviceId)
        return Dispatch(accepted=False, priority=priority, error=error)


def command_summary(dispatches: Iterable[Dispatch]) -> Mapping[str, Any]:
    """Small helper the API and tests both use to describe a batch."""

    items = tuple(dispatches)
    return {
        "total": len(items),
        "accepted": sum(1 for item in items if item.accepted),
        "denied": sum(1 for item in items if not item.accepted),
        "codes": sorted({item.error.code for item in items if item.error is not None}),
    }
