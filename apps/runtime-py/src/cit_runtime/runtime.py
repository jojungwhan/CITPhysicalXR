"""The runtime facade the API and the tests both drive.

Everything the Studio can do goes through a method here, so the HTTP layer holds
no rules of its own. FR-062 is the default: a runtime starts in simulation mode
with the four fake adapters and no physical device.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
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
from .projects import ProjectStore
from .recorder import Recorder, Recording, Replayer
from .registry import ConfiguredDiscoveryProvider, DeviceRegistry, DiscoveryProvider
from .retention import RecordingStore, RetentionPolicy
from .roles import Authority
from .sessions import (
    AuthoringMode,
    ExecutionMode,
    FailurePolicy,
    ProgramSession,
    SessionRepository,
    SessionState,
)
from .status import DeviceStatusProjection, derive_warnings
from .supervisor import ArmState, SafetyPolicy, SafetySupervisor, WatchdogKind


def default_simulation_adapters() -> tuple[DeviceAdapter, ...]:
    """The M1 fake fleet: one robot family each, one input, one XR client."""

    return (
        create_fake_s1_adapter(),
        create_fake_lego_adapter(),
        create_fake_leap_adapter(),
        create_fake_quest_adapter(),
    )


def default_data_dir() -> Path:
    """Where projects and recordings live when nobody says otherwise.

    Local-first means the classroom's work is on the classroom's machine, in a
    place an instructor can find, back up, and delete. ``CITXR_DATA_DIR``
    overrides it, which is what the tests use so a run never touches a real one.
    """

    override = os.environ.get("CITXR_DATA_DIR")
    if override:
        return Path(override)
    return Path.home() / ".citxr"


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
        providers: Iterable[DiscoveryProvider] = (),
        policies: Iterable[SafetyPolicy] = (),
        runtime_id: str = "cit-runtime-local",
        physical_enabled: bool = False,
        data_dir: Path | None = None,
        instructor_passcode: str | None = None,
        join_passcode: str | None = None,
        retention: RetentionPolicy | None = None,
    ) -> None:
        self.clock: Clock = clock or SystemClock()
        self.runtime_id = runtime_id
        self.physical_enabled = physical_enabled
        self.registry = DeviceRegistry()
        self.sessions = SessionRepository()
        self.router = EventRouter()
        self.audit = AuditLog()
        self.logger = StructuredLogger()
        self.authority = Authority(
            instructor_passcode=instructor_passcode, join_passcode=join_passcode
        )
        self.supervisor = SafetySupervisor(clock=self.clock, policies=policies)
        self.status = DeviceStatusProjection()
        # FR-065 is fed by the event stream rather than by polling adapters, so
        # the console shows what a device actually reported and nothing else.
        self.router.subscribe("device-status", self.status.observe)
        self.pipeline = CommandPipeline(
            clock=self.clock,
            registry=self.registry,
            sessions=self.sessions,
            supervisor=self.supervisor,
            router=self.router,
            audit=self.audit,
            logger=self.logger,
            status=self.status,
        )
        self.data_dir = data_dir if data_dir is not None else default_data_dir()
        self.projects = ProjectStore(self.data_dir / "projects")
        self.recording_store = RecordingStore(
            self.data_dir / "recordings", policy=retention or RetentionPolicy()
        )
        # The fake fleet is always present (FR-062 simulation-first). A hardware
        # provider is added beside it, never instead of it, so a class whose hub
        # is flat can still run the lesson against a simulated one.
        self._providers: tuple[DiscoveryProvider, ...] = (
            ConfiguredDiscoveryProvider(
                adapters if adapters is not None else default_simulation_adapters()
            ),
            *providers,
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
        found: list[str] = []
        for provider in self._providers:
            found.extend(await self.registry.discover_from(provider, at=self.clock.now()))
        return tuple(found)

    async def connect_all(self) -> tuple[str, ...]:
        """Connect every discovered device. A hub that refuses is not fatal.

        One flat hub must not stop a class from starting. The failure is
        recorded on the device, where the instructor console shows it, and the
        rest of the room comes up.
        """

        connected: list[str] = []
        for device in self.registry.list():
            try:
                await self.registry.connect(device.device_id, at=self.clock.now())
            except Exception as error:
                self.logger.warning(
                    "device connect failed",
                    deviceId=device.device_id,
                    reason=str(error),
                )
                continue
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
        failure_policy: FailurePolicy = FailurePolicy.STOP_COORDINATED,
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
            failure_policy=failure_policy,
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

    def set_input_enabled(self, source: str, *, enabled: bool, actor_id: str) -> None:
        """FR-067. Disable Leap input, or disconnect Quest control, by name."""

        self.supervisor.set_source_enabled(source, enabled=enabled)
        self.audit.record(
            AuditAction.INPUT_SOURCE_CHANGED,
            actor_id=actor_id,
            at=self.clock.now(),
            context={"source": source, "state": "enabled" if enabled else "disabled"},
        )

    async def revoke_lease(self, device_id: str, *, actor_id: str) -> int:
        """FR-067. Stop the device, drop its lease, and free it for reassignment."""

        revoked = await self.pipeline.revoke_lease(device_id, actor_id=actor_id)
        self.supervisor.disarm(device_id)
        return revoked

    def clear_queue(self, *, device_id: str | None, actor_id: str) -> int:
        return self.pipeline.clear_queue(device_id=device_id, actor_id=actor_id)

    async def disconnect_device(self, device_id: str, *, reason: str, actor_id: str) -> None:
        """FR-067. Take one device off the floor without stopping the class."""

        await self.pipeline.stop_device(device_id, reason=reason, actor_id=actor_id)
        await self.registry.disconnect(device_id, at=self.clock.now())
        await self.pipeline.handle_disconnect(device_id, reason=reason)

    def set_failure_policy(self, session_id: str, policy: FailurePolicy) -> ProgramSession:
        """FR-058. Instructor-owned: what the group does when one device fails."""

        session = self.sessions.get(session_id)
        return self.sessions.save(replace(session, failure_policy=policy))

    async def submit(self, command: DeviceCommandIntent) -> Dispatch:
        return await self.pipeline.submit(command)

    async def stop_all(
        self, *, reason: str = "instructor stop-all", actor_id: str
    ) -> tuple[str, ...]:
        return await self.pipeline.stop_all(reason=reason, actor_id=actor_id)

    async def tick(self) -> int:
        """Drive watchdogs and give every adapter its slice of the same loop.

        An adapter that has to keep a link alive -- a LEGO hub stops on its own
        after 500 ms of silence (FR-049) -- gets its heartbeat from here rather
        than from a task of its own. A background task would happily keep
        feeding a hub after the loop that supervises it had died.
        """

        expiries = await self.pipeline.enforce_watchdogs()
        for device in self.registry.list():
            adapter = self.registry.adapter(device.device_id)
            tick = getattr(adapter, "tick", None)
            if tick is None:
                continue
            events = await tick(at=self.clock.now())
            self.router.publish_all(events)
        return len(expiries)

    # --------------------------------------------------------------- recording

    def start_recording(self, session_id: str, *, actor_id: str = "system") -> str:
        recording_id = f"rec-{uuid4().hex[:12]}"
        recorder = Recorder(
            recording_id=recording_id,
            session_id=session_id,
            started_at=self.clock.now(),
        )
        recorder.attach(self.router, subscriber_id=f"recorder:{recording_id}")
        self._recorders[recording_id] = recorder
        self.audit.record(
            AuditAction.RECORDING_STARTED,
            actor_id=actor_id,
            at=self.clock.now(),
            context={"recordingId": recording_id, "sessionId": session_id},
        )
        return recording_id

    def stop_recording(self, recording_id: str, *, actor_id: str = "system") -> Recording:
        recorder = self._recorders.pop(recording_id)
        self.router.unsubscribe(f"recorder:{recording_id}")
        recording = recorder.finish()
        self._recordings[recording_id] = recording
        now = self.clock.now()
        # Persisting here is what makes a recording survive the tab that made
        # it (FR-064), and the store prunes to the retention policy as it
        # writes (FR-084).
        pruned: tuple[str, ...] = ()
        try:
            self.recording_store.save(recording, now=now)
            pruned = self.recording_store.prune(now=now)
        except OSError as error:
            self.logger.warning(
                "recording not persisted", recordingId=recording_id, reason=str(error)
            )
        self.audit.record(
            AuditAction.RECORDING_STOPPED,
            actor_id=actor_id,
            at=now,
            context={
                "recordingId": recording_id,
                "sessionId": recording.session_id,
                "count": len(recording.events),
            },
        )
        if pruned:
            self.audit.record(
                AuditAction.RETENTION_PRUNED,
                actor_id="system",
                at=now,
                context={"count": len(pruned), "result": ",".join(pruned)},
            )
        return recording

    def recording(self, recording_id: str) -> Recording:
        """In-memory first, then disk: a recording outlives the runtime that made it."""

        found = self._recordings.get(recording_id)
        if found is not None:
            return found
        return self.recording_store.get(recording_id)

    def recordings(self) -> tuple[str, ...]:
        stored = {item.recording_id for item in self.recording_store.list()}
        return tuple(sorted(stored | set(self._recordings)))

    def replay(self, recording_id: str, *, actor_id: str) -> int:
        """FR-064. Publish a recording to subscribers. Reaches no adapter, ever.

        ``Replayer`` holds no registry and no pipeline, so this cannot move a
        robot even if someone later wants it to. Every event it publishes is
        marked historical.
        """

        delivered = Replayer(self.recording(recording_id)).replay_to(self.router)
        self.audit.record(
            AuditAction.REPLAY_STARTED,
            actor_id=actor_id,
            at=self.clock.now(),
            context={"recordingId": recording_id, "count": delivered},
        )
        return delivered

    # ----------------------------------------------------------------- console

    def device_overview(self) -> tuple[Mapping[str, Any], ...]:
        """FR-065 and UI 11.3: everything one device card shows, observed."""

        now = self.clock.now()
        cards: list[Mapping[str, Any]] = []
        for device in self.registry.list():
            device_id = device.device_id
            arm = self.supervisor.arm_state(device_id)
            arm_remaining = (arm.expires_at - now).total_seconds() if arm is not None else None
            session = None
            if device.assigned_session_id is not None:
                try:
                    session = self.sessions.get(device.assigned_session_id)
                except KeyError:
                    session = None
            observed = self.status.get(device_id)
            ages = self.supervisor.heartbeat_ages(device_id)
            stale = {
                kind.value: age for kind, age in ages.items() if age > self.supervisor.timeout(kind)
            }
            cards.append(
                {
                    "deviceId": device_id,
                    "displayName": device.descriptor.displayName,
                    "deviceType": device.descriptor.deviceType,
                    "model": device.descriptor.model,
                    "adapterId": device.descriptor.adapterId,
                    "adapterVersion": device.descriptor.adapterVersion,
                    "firmware": observed.firmware,
                    "physical": device.physical,
                    "state": device.state.value,
                    "capabilities": list(device.descriptor.capabilities),
                    "batteryPercent": observed.battery_percent,
                    "activeStudentId": session.user_id if session is not None else None,
                    "activeSessionId": device.assigned_session_id,
                    "safetyPolicyId": session.safety_policy_id if session is not None else None,
                    "armed": arm is not None,
                    "armedBy": arm.armed_by if arm is not None else None,
                    "armExpiresAt": arm.expires_at.isoformat() if arm is not None else None,
                    "leaseSessionId": self.pipeline.lease_holder(device_id),
                    "lastCommand": (
                        None
                        if observed.last_command_capability is None
                        else {
                            "capability": observed.last_command_capability,
                            "action": observed.last_command_action,
                            "result": observed.last_command_result,
                            "at": (
                                observed.last_command_at.isoformat()
                                if observed.last_command_at is not None
                                else None
                            ),
                            "ageMs": (
                                (now - observed.last_command_at).total_seconds() * 1000
                                if observed.last_command_at is not None
                                else None
                            ),
                        }
                    ),
                    "lastTelemetry": (
                        None
                        if observed.last_telemetry_name is None
                        else {
                            "name": observed.last_telemetry_name,
                            "at": (
                                observed.last_telemetry_at.isoformat()
                                if observed.last_telemetry_at is not None
                                else None
                            ),
                        }
                    ),
                    "heartbeatAges": {kind.value: age for kind, age in ages.items()},
                    "failureReason": device.failure_reason,
                    "warnings": list(
                        derive_warnings(
                            observed,
                            device_state=device.state.value,
                            failure_reason=device.failure_reason,
                            arm_seconds_remaining=arm_remaining,
                            stale_watchdogs=stale,
                        )
                    ),
                }
            )
        return tuple(cards)
