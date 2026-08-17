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

import asyncio
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
from .sessions import ExecutionMode, FailurePolicy, ProgramSession, SessionRepository, SessionState
from .status import DeviceStatusProjection
from .supervisor import (
    CommandPriority,
    SafetySupervisor,
    WatchdogAction,
    WatchdogExpiry,
    classify_priority,
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
    # The caller waiting for this command's outcome, when there is one. A
    # command pushed by a test has nobody waiting; a command pushed by
    # ``submit`` has exactly one caller, and discarding it without answering
    # them would leave that caller awaiting a result that can never arrive.
    waiter: asyncio.Future[Dispatch] | None = field(compare=False, default=None)

    def resolve(self, dispatch: Dispatch) -> None:
        if self.waiter is not None and not self.waiter.done():
            self.waiter.set_result(dispatch)

    def fail(self, error: BaseException) -> None:
        if self.waiter is not None and not self.waiter.done():
            self.waiter.set_exception(error)


@dataclass(slots=True)
class _DeviceLane:
    """One device's turn-taking. Held while that device's queue is drained.

    Per device rather than per runtime: a lease is per device and a robot
    executes one command at a time, so serializing a device is physics. Doing
    the same across the room would make one student's slow command the reason
    another student's robot stood still (FR-057).
    """

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


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

    def push(
        self,
        command: DeviceCommandIntent,
        *,
        priority: CommandPriority,
        waiter: asyncio.Future[Dispatch] | None = None,
    ) -> None:
        if len(self._heap) >= self._max_depth:
            raise OverflowError("Command queue is full; the runtime is shedding load")
        heapq.heappush(
            self._heap,
            _QueueItem(
                priority=int(priority),
                tiebreak=next(self._counter),
                command=command,
                waiter=waiter,
            ),
        )

    def pop(self) -> DeviceCommandIntent | None:
        if not self._heap:
            return None
        return heapq.heappop(self._heap).command

    def pop_for(self, device_id: str) -> _QueueItem | None:
        """The highest-priority queued item for one device (FR-072).

        A heap orders the whole room, and the room is drained one device at a
        time, so the item wanted here is not always the heap's root.
        """

        best: _QueueItem | None = None
        for item in self._heap:
            if item.command.deviceId != device_id:
                continue
            if best is None or item < best:
                best = item
        if best is None:
            return None
        self._heap.remove(best)
        heapq.heapify(self._heap)
        return best

    def take(self, *, device_id: str | None = None) -> tuple[_QueueItem, ...]:
        """Remove and return queued items, so a caller can answer their waiters."""

        if device_id is None:
            taken = tuple(sorted(self._heap))
            self._heap.clear()
            return taken
        taken = tuple(sorted(item for item in self._heap if item.command.deviceId == device_id))
        if taken:
            self._heap = [item for item in self._heap if item.command.deviceId != device_id]
            heapq.heapify(self._heap)
        return taken

    def clear(self, *, device_id: str | None = None) -> int:
        """FR-067. Returns how many queued commands were discarded.

        Nothing waiting on a discarded command is answered here: a caller that
        wants to answer them uses ``take``. The pipeline always does.
        """

        return len(self.take(device_id=device_id))

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
        status: DeviceStatusProjection | None = None,
        lease_ttl: timedelta = timedelta(seconds=30),
    ) -> None:
        self._clock = clock
        self._registry = registry
        self._sessions = sessions
        self._supervisor = supervisor
        self._router = router
        self._audit = audit
        self._logger = logger or StructuredLogger()
        self._status = status or DeviceStatusProjection()
        self._ledger = InMemoryCommandLedger()
        self._leases = InMemoryDeviceLeaseRegistry()
        self._lease_ttl = lease_ttl
        self.queue = CommandQueue()
        self._lanes: dict[str, _DeviceLane] = {}

    async def submit(self, command: DeviceCommandIntent) -> Dispatch:
        """FR-072. Every command enters the queue; a device drains its own.

        Until Milestone 6 the queue implemented ordering and clearing for
        nobody: ``submit`` dispatched straight to the adapter, so a queued
        instructor stop could not overtake a student command that had already
        been handed to a robot, and clearing a queue cleared something no
        command had ever been in. Both are now the same path.

        The caller still awaits its own outcome. What changed is that while it
        waits, the runtime is free to run somebody else's higher-priority
        command for that device first.
        """

        priority = classify_priority(command)
        waiter: asyncio.Future[Dispatch] = asyncio.get_running_loop().create_future()
        try:
            self.queue.push(command, priority=priority, waiter=waiter)
        except OverflowError:
            return self._reject(
                command,
                "SAFETY_POLICY_DENIED",
                "The command queue is full and the runtime is shedding load",
                "Wait for the class to catch up, then send this again.",
                now=self._clock.now(),
                priority=priority,
            )
        await self._drain(command.deviceId)
        return await waiter

    async def _drain(self, device_id: str) -> None:
        """Run this device's queued commands, highest priority first.

        Cooperative rather than a background task: whoever submits does the
        draining, so there is no worker to supervise, nothing to leak when a
        runtime stops, and no command sitting in a queue because its task was
        never started. A caller may drain somebody else's command and find its
        own already answered, which is the point.
        """

        lane = self._lanes.get(device_id)
        if lane is None:
            lane = self._lanes[device_id] = _DeviceLane()
        # Counted before the lock is awaited, so the lane cannot be dropped and
        # recreated while somebody is queued behind it -- two lanes for one
        # device would be two commands on one robot at once.
        lane.users += 1
        try:
            async with lane.lock:
                while True:
                    item = self.queue.pop_for(device_id)
                    if item is None:
                        return
                    try:
                        item.resolve(await self._dispatch(item.command))
                    except Exception as error:
                        # One command's failure belongs to whoever sent it, not
                        # to whoever happened to be draining the lane.
                        item.fail(error)
                    except BaseException as error:
                        item.fail(error)
                        raise
        finally:
            lane.users -= 1
            if lane.users == 0:
                self._lanes.pop(device_id, None)

    async def _dispatch(self, command: DeviceCommandIntent) -> Dispatch:
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
                actor_id=session.user_id,
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
        self._status.note_command(
            device_id=command.deviceId,
            capability=command.capability,
            action=command.action,
            result=result.status,
            at=now,
        )

        accepted = result.status in {"accepted", "completed"}
        if not accepted:
            # FR-058. The exact failed device is already named in the result;
            # what the policy decides is what happens to the rest of the group.
            await self._apply_failure_policy(session, failed_device_id=command.deviceId, now=now)

        self._audit.record(
            AuditAction.COMMAND_ACCEPTED,
            # The person, not the mechanism. `student_blocks` in this column
            # told an instructor reading the log that a block had moved a robot
            # and not which child's block it was (FR-083); the mechanism is
            # still recorded, one field along.
            actor_id=session.user_id,
            at=now,
            context={
                "commandId": str(command.commandId),
                "deviceId": command.deviceId,
                "sessionId": command.sessionId,
                "capability": command.capability,
                "action": command.action,
                "source": command.source,
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
            accepted=accepted,
            priority=verdict.priority,
            result=result,
            clamped_fields=verdict.clamped_fields,
            events=events,
        )

    async def _apply_failure_policy(
        self,
        session: ProgramSession,
        *,
        failed_device_id: str,
        now: datetime,
    ) -> tuple[str, ...]:
        """FR-058. Stop the rest of a coordinated physical group, or don't.

        Only physical sessions coordinate anything a failure can hurt, so a
        simulation is left alone: stopping four fake robots because one refused
        a command would teach a student that failure is contagious.
        """

        if session.execution_mode is not ExecutionMode.PHYSICAL:
            return ()
        if session.failure_policy is not FailurePolicy.STOP_COORDINATED:
            return ()

        stopped: list[str] = []
        for device_id in session.device_bindings:
            if device_id == failed_device_id:
                continue
            try:
                device = self._registry.get(device_id)
            except KeyError:
                continue
            if not device.physical:
                continue
            await self.stop_device(
                device_id,
                reason=f"failure policy: {failed_device_id} failed",
                actor_id="system",
            )
            stopped.append(device_id)

        self._audit.record(
            AuditAction.FAILURE_POLICY_APPLIED,
            actor_id="system",
            at=now,
            context={
                "sessionId": session.session_id,
                "deviceId": failed_device_id,
                "failurePolicy": session.failure_policy.value,
                "result": ",".join(stopped),
            },
        )
        return tuple(stopped)

    # ------------------------------------------------------- emergency controls

    async def stop_device(self, device_id: str, *, reason: str, actor_id: str) -> int:
        """Stop one device and clear anything queued for it (FR-067)."""

        now = self._clock.now()
        cleared = self._discard(device_id=device_id, reason=reason)
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
        self._discard(device_id=None, reason=reason)
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

    async def revoke_lease(self, device_id: str, *, actor_id: str) -> int:
        """FR-067. Take a device back from a session that will not let go.

        The device is stopped first. Handing a robot to the next student while
        it is still driving would be a strange way to recover from a stuck
        session, so revoking is stop-then-release and never release alone.
        """

        await self.stop_device(device_id, reason="lease revoked", actor_id=actor_id)
        revoked = self._leases.revoke(device_id)
        self._registry.release(device_id)
        self._audit.record(
            AuditAction.LEASE_REVOKED,
            actor_id=actor_id,
            at=self._clock.now(),
            context={"deviceId": device_id, "count": len(revoked)},
        )
        return len(revoked)

    def lease_holder(self, device_id: str) -> str | None:
        """Which session currently holds the write lease, if any (FR-065)."""

        lease = self._leases.holder(device_id, now=self._clock.now())
        return None if lease is None else lease.session_id

    def clear_queue(self, *, device_id: str | None, actor_id: str) -> int:
        """FR-067. Discard queued work without stopping anything else."""

        cleared = self._discard(device_id=device_id, reason=f"queue cleared by {actor_id}")
        self._audit.record(
            AuditAction.QUEUE_CLEARED,
            actor_id=actor_id,
            at=self._clock.now(),
            context={"deviceId": device_id, "count": cleared},
        )
        return cleared

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
        self._discard(device_id=device_id, reason=f"device disconnected: {reason}")
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

    def _discard(self, *, device_id: str | None, reason: str) -> int:
        """Drop queued commands and tell whoever sent them (FR-067, UI 11.6).

        A cleared queue is a refusal, not a silence. Every discarded command is
        answered with the reason it never ran and is recorded as denied, so a
        student whose robot did nothing after a stop-all can be told why rather
        than watching a page wait forever.
        """

        items = self.queue.take(device_id=device_id)
        if not items:
            return 0
        now = self._clock.now()
        for item in items:
            item.resolve(
                self._reject(
                    item.command,
                    "SAFETY_POLICY_DENIED",
                    f"Queued command discarded: {reason}",
                    "Nothing was sent to the device. Send it again when the class is running.",
                    now=now,
                    priority=CommandPriority(item.priority),
                )
            )
        return len(items)

    def _actor_for(self, command: DeviceCommandIntent) -> str:
        """Who issued this, when the session is still known (FR-083)."""

        try:
            return self._sessions.get(command.sessionId).user_id
        except KeyError:
            # A command naming a session that does not exist is exactly the case
            # where there is nobody to name. The source is what is left.
            return command.source

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
            actor_id=self._actor_for(command),
            at=now,
            context={
                "commandId": str(command.commandId),
                "deviceId": command.deviceId,
                "sessionId": command.sessionId,
                "source": command.source,
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
