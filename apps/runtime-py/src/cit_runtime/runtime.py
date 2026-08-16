"""The runtime facade the API and the tests both drive.

Everything the Studio can do goes through a method here, so the HTTP layer holds
no rules of its own. FR-062 is the default: a runtime starts in simulation mode
with the four fake adapters and no physical device.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import uuid4

from cit_device_simulator import (
    DeviceAdapter,
    create_fake_leap_adapter,
    create_fake_lego_adapter,
    create_fake_quest_adapter,
    create_fake_s1_adapter,
)
from cit_protocol import DeviceCommandIntent

from .audit import AuditAction, AuditLog, StructuredLogger
from .clock import Clock, SystemClock
from .events import EventRouter
from .pipeline import CommandPipeline, Dispatch
from .recorder import Recorder, Recording
from .registry import ConfiguredDiscoveryProvider, DeviceRegistry, DiscoveryProvider
from .sessions import (
    AuthoringMode,
    ExecutionMode,
    ProgramSession,
    SessionRepository,
    SessionState,
)
from .supervisor import ArmState, SafetyPolicy, SafetySupervisor, WatchdogKind


def default_simulation_adapters() -> tuple[DeviceAdapter, ...]:
    """The M1 fake fleet: one robot family each, one input, one XR client."""

    return (
        create_fake_s1_adapter(),
        create_fake_lego_adapter(),
        create_fake_leap_adapter(),
        create_fake_quest_adapter(),
    )


@dataclass(frozen=True, slots=True)
class RuntimeInfo:
    runtime_id: str
    protocol_version: int
    execution_mode: str
    physical_enabled: bool


class Runtime:
    """One classroom runtime. Local-first: it needs no network to work."""

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        adapters: Iterable[DeviceAdapter] | None = None,
        policies: Iterable[SafetyPolicy] = (),
        runtime_id: str = "cit-runtime-local",
        physical_enabled: bool = False,
    ) -> None:
        self.clock: Clock = clock or SystemClock()
        self.runtime_id = runtime_id
        self.physical_enabled = physical_enabled
        self.registry = DeviceRegistry()
        self.sessions = SessionRepository()
        self.router = EventRouter()
        self.audit = AuditLog()
        self.logger = StructuredLogger()
        self.supervisor = SafetySupervisor(clock=self.clock, policies=policies)
        self.pipeline = CommandPipeline(
            clock=self.clock,
            registry=self.registry,
            sessions=self.sessions,
            supervisor=self.supervisor,
            router=self.router,
            audit=self.audit,
            logger=self.logger,
        )
        self._provider: DiscoveryProvider = ConfiguredDiscoveryProvider(
            adapters if adapters is not None else default_simulation_adapters()
        )
        self._recorders: dict[str, Recorder] = {}
        self._recordings: dict[str, Recording] = {}

    def info(self) -> RuntimeInfo:
        return RuntimeInfo(
            runtime_id=self.runtime_id,
            protocol_version=1,
            execution_mode=(
                ExecutionMode.PHYSICAL.value
                if self.physical_enabled
                else ExecutionMode.SIMULATION.value
            ),
            physical_enabled=self.physical_enabled,
        )

    # ----------------------------------------------------------------- devices

    async def discover(self) -> tuple[str, ...]:
        return await self.registry.discover_from(self._provider, at=self.clock.now())

    async def connect_all(self) -> tuple[str, ...]:
        connected: list[str] = []
        for device in self.registry.list():
            await self.registry.connect(device.device_id, at=self.clock.now())
            self.audit.record(
                AuditAction.DEVICE_CONNECTED,
                actor_id="system",
                at=self.clock.now(),
                context={"deviceId": device.device_id},
            )
            connected.append(device.device_id)
        self.router.publish_all(self._drain_all())
        return tuple(connected)

    def _drain_all(self) -> tuple[Any, ...]:
        drained: list[Any] = []
        for device in self.registry.list():
            drained.extend(self.registry.adapter(device.device_id).drain_events())
        return tuple(drained)

    async def start(self) -> tuple[str, ...]:
        """Discover and connect. Safe to call on a cold runtime."""

        await self.discover()
        return await self.connect_all()

    # ---------------------------------------------------------------- sessions

    def create_session(
        self,
        *,
        project_id: str,
        user_id: str,
        authoring_mode: AuthoringMode = AuthoringMode.BLOCKS,
        execution_mode: ExecutionMode = ExecutionMode.SIMULATION,
        instructor_id: str | None = None,
        safety_policy_id: str = "simulation-only",
        session_id: str | None = None,
    ) -> ProgramSession:
        if execution_mode is ExecutionMode.PHYSICAL and not self.physical_enabled:
            raise PermissionError(
                "This runtime is configured for simulation only; physical mode is disabled"
            )
        now = self.clock.now()
        session = ProgramSession(
            session_id=session_id or f"session-{uuid4().hex[:12]}",
            project_id=project_id,
            authoring_mode=authoring_mode,
            execution_mode=execution_mode,
            user_id=user_id,
            instructor_id=instructor_id,
            safety_policy_id=safety_policy_id,
            started_at=now,
            last_activity_at=now,
        )
        self.sessions.add(session)
        self.audit.record(
            AuditAction.SESSION_CREATED,
            actor_id=user_id,
            at=now,
            context={
                "sessionId": session.session_id,
                "executionMode": execution_mode.value,
                "policyId": safety_policy_id,
            },
        )
        return session

    def bind_devices(self, session_id: str, device_ids: Sequence[str]) -> ProgramSession:
        now = self.clock.now()
        session = self.sessions.get(session_id)
        for device_id in device_ids:
            self.registry.assign(device_id, session_id=session_id)
            self.audit.record(
                AuditAction.DEVICE_ASSIGNED,
                actor_id=session.user_id,
                at=now,
                context={"deviceId": device_id, "sessionId": session_id},
            )
        return self.sessions.save(session.bind_devices(tuple(device_ids), at=now))

    def transition(
        self, session_id: str, state: SessionState, *, reason: str | None = None
    ) -> ProgramSession:
        now = self.clock.now()
        session = self.sessions.get(session_id).transition(state, at=now, reason=reason)
        self.audit.record(
            AuditAction.SESSION_STATE_CHANGED,
            actor_id=session.user_id,
            at=now,
            context={"sessionId": session_id, "state": state.value, "reason": reason},
        )
        saved = self.sessions.save(session)

        if saved.is_terminal:
            # A finished session must hand its devices back. Without this the
            # first lesson of the day holds every robot until the runtime
            # restarts, and the next class finds nothing it can bind.
            for device_id in self.registry.release_session(session_id):
                self.supervisor.disarm(device_id)
                self.audit.record(
                    AuditAction.DEVICE_RELEASED,
                    actor_id=saved.user_id,
                    at=now,
                    context={"deviceId": device_id, "sessionId": session_id},
                )
        return saved

    def advance_to_ready(self, session_id: str) -> ProgramSession:
        """The ordinary happy path: created -> validating -> ready."""

        self.transition(session_id, SessionState.VALIDATING)
        return self.transition(session_id, SessionState.READY)

    # ------------------------------------------------------------------ safety

    def arm(
        self, *, session_id: str, device_id: str, instructor_id: str, ttl: timedelta | None = None
    ) -> ArmState:
        session = self.sessions.get(session_id)
        if session.state not in {SessionState.READY, SessionState.WAITING_FOR_ARM}:
            raise PermissionError(
                f"Session {session_id!r} must validate before arming (state {session.state.value})"
            )
        if ttl is not None:
            policy = self.supervisor.policy(session.safety_policy_id)
            self.supervisor.register_policy(
                SafetyPolicy(
                    policy_id=policy.policy_id,
                    bounds=policy.bounds,
                    allowed_capabilities=policy.allowed_capabilities,
                    denied_capabilities=policy.denied_capabilities,
                    arm_ttl=ttl,
                    require_deadman=policy.require_deadman,
                )
            )
        state = self.supervisor.arm(
            device_id=device_id,
            session_id=session_id,
            instructor_id=instructor_id,
            policy_id=session.safety_policy_id,
            program_validated=True,
        )
        self.audit.record(
            AuditAction.DEVICE_ARMED,
            actor_id=instructor_id,
            at=self.clock.now(),
            context={"deviceId": device_id, "sessionId": session_id},
        )
        return state

    def disarm(self, device_id: str, *, actor_id: str = "instructor") -> None:
        self.supervisor.disarm(device_id)
        self.audit.record(
            AuditAction.DEVICE_DISARMED,
            actor_id=actor_id,
            at=self.clock.now(),
            context={"deviceId": device_id},
        )

    def heartbeat(self, *, device_id: str, kind: WatchdogKind) -> None:
        self.supervisor.heartbeat(device_id=device_id, kind=kind)

    async def submit(self, command: DeviceCommandIntent) -> Dispatch:
        return await self.pipeline.submit(command)

    async def stop_all(
        self, *, reason: str = "instructor stop-all", actor_id: str
    ) -> tuple[str, ...]:
        return await self.pipeline.stop_all(reason=reason, actor_id=actor_id)

    async def tick(self) -> int:
        """Drive watchdogs. A host loop or a test calls this."""

        expiries = await self.pipeline.enforce_watchdogs()
        return len(expiries)

    # --------------------------------------------------------------- recording

    def start_recording(self, session_id: str) -> str:
        recording_id = f"rec-{uuid4().hex[:12]}"
        recorder = Recorder(
            recording_id=recording_id,
            session_id=session_id,
            started_at=self.clock.now(),
        )
        recorder.attach(self.router, subscriber_id=f"recorder:{recording_id}")
        self._recorders[recording_id] = recorder
        return recording_id

    def stop_recording(self, recording_id: str) -> Recording:
        recorder = self._recorders.pop(recording_id)
        self.router.unsubscribe(f"recorder:{recording_id}")
        recording = recorder.finish()
        self._recordings[recording_id] = recording
        return recording

    def recording(self, recording_id: str) -> Recording:
        return self._recordings[recording_id]

    def recordings(self) -> tuple[str, ...]:
        return tuple(sorted(self._recordings))
