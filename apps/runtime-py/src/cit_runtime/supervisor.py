"""The physical safety supervisor.

FR-069 requires this to survive a student program crash, a closed browser, a
dropped Quest, lost Leap tracking, a disconnected Agent Mesh, and an adapter
restart. It therefore owns no transport and holds no reference to a client: it
is a pure decision surface plus a watchdog table, driven by an injected clock.
Every caller asks it, and it can only ever answer with a denial or a bound.

FR-066 arming, FR-070 watchdogs, FR-071 command bounds, FR-072 priorities, and
FR-074 AI policy all live here so that no adapter can be the place a rule is
enforced.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum, StrEnum

from cit_protocol import DeviceCommandIntent
from cit_safety import FoundationSafetyGate, SafetyDecision

from .clock import Clock


class CommandPriority(IntEnum):
    """FR-072. Lower value preempts higher value."""

    PHYSICAL_EMERGENCY_STOP = 1
    INSTRUCTOR_STOP_ALL = 2
    RUNTIME_SAFETY_STOP = 3
    DEVICE_WATCHDOG = 4
    PROGRAM_STOP = 5
    STUDENT_COMMAND = 6
    AI_OR_WEARABLE_PROPOSAL = 7


_SOURCE_PRIORITY: Mapping[str, CommandPriority] = {
    "system": CommandPriority.RUNTIME_SAFETY_STOP,
    # Deliberately not INSTRUCTOR_STOP_ALL. FR-072 ranks an instructor's
    # *stop-all* second, not everything an instructor sends: driving a robot is
    # driving a robot, and ranking it above the runtime's own safety stop would
    # let an ordinary command preempt the thing that exists to interrupt it. The
    # stop branch below still gives a real instructor stop its rank.
    "instructor": CommandPriority.STUDENT_COMMAND,
    "student_blocks": CommandPriority.STUDENT_COMMAND,
    "student_python": CommandPriority.STUDENT_COMMAND,
    "quest": CommandPriority.STUDENT_COMMAND,
    "leap": CommandPriority.STUDENT_COMMAND,
    "agent_mesh": CommandPriority.AI_OR_WEARABLE_PROPOSAL,
}

_STOP_ACTIONS: frozenset[str] = frozenset({"emergency_stop", "halt", "stop", "stop_all"})


def classify_priority(command: DeviceCommandIntent) -> CommandPriority:
    """Rank a command by what issued it and whether it is a stop."""

    if command.action in _STOP_ACTIONS:
        if command.source == "instructor":
            return CommandPriority.INSTRUCTOR_STOP_ALL
        if command.source == "system":
            return CommandPriority.RUNTIME_SAFETY_STOP
        return CommandPriority.PROGRAM_STOP
    return _SOURCE_PRIORITY.get(command.source, CommandPriority.AI_OR_WEARABLE_PROPOSAL)


class WatchdogKind(StrEnum):
    """FR-070. Each kind carries its own default timeout."""

    S1_CONTINUOUS_MOTION = "s1_continuous_motion"
    LEGO_CONTINUOUS_MOTION = "lego_continuous_motion"
    QUEST_DEADMAN_HEARTBEAT = "quest_deadman_heartbeat"
    LEAP_CONTINUOUS_INPUT = "leap_continuous_input"
    ADAPTER_PROCESS_HEARTBEAT = "adapter_process_heartbeat"


# FR-070 defaults. The S1 range is 300-500 ms; the tighter bound is the default.
DEFAULT_WATCHDOG_TIMEOUTS: Mapping[WatchdogKind, float] = {
    WatchdogKind.S1_CONTINUOUS_MOTION: 0.300,
    WatchdogKind.LEGO_CONTINUOUS_MOTION: 0.500,
    WatchdogKind.QUEST_DEADMAN_HEARTBEAT: 0.300,
    WatchdogKind.LEAP_CONTINUOUS_INPUT: 0.300,
    WatchdogKind.ADAPTER_PROCESS_HEARTBEAT: 1.000,
}


class WatchdogAction(StrEnum):
    STOP = "stop"
    DISARM = "disarm"


@dataclass(frozen=True, slots=True)
class WatchdogExpiry:
    """A timeout that has already fired, with what the runtime must now do."""

    device_id: str
    kind: WatchdogKind
    action: WatchdogAction
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class MotionBounds:
    """FR-071. The ceiling a student cannot raise (FR-068)."""

    max_speed: float = 0.5
    max_acceleration: float | None = None
    max_duration_seconds: float = 2.0
    min_input_confidence: float = 0.6
    geofence_radius_m: float | None = None

    def __post_init__(self) -> None:
        if self.max_speed <= 0:
            raise ValueError("max_speed must be positive")
        if self.max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be positive")
        if not 0.0 <= self.min_input_confidence <= 1.0:
            raise ValueError("min_input_confidence must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class SafetyPolicy:
    """A named, instructor-owned bundle of bounds and capability permissions."""

    policy_id: str
    bounds: MotionBounds = field(default_factory=MotionBounds)
    allowed_capabilities: frozenset[str] = frozenset()
    denied_capabilities: frozenset[str] = frozenset({"weapon.blaster"})
    arm_ttl: timedelta = timedelta(minutes=5)
    require_deadman: bool = True

    def permits(self, capability: str) -> bool:
        if capability in self.denied_capabilities:
            return False
        if not self.allowed_capabilities:
            return True
        return capability in self.allowed_capabilities


@dataclass(frozen=True, slots=True)
class ArmState:
    """FR-066. Arming is granted by an instructor and expires by itself."""

    device_id: str
    session_id: str
    armed_by: str
    armed_at: datetime
    expires_at: datetime

    def is_active(self, *, now: datetime) -> bool:
        return now < self.expires_at


class ArmingError(RuntimeError):
    pass


_MOVEMENT_PREFIXES = ("actuator.", "chassis.", "drive.", "gimbal.", "motion.", "motor.")


def is_movement(capability: str) -> bool:
    return capability.startswith(_MOVEMENT_PREFIXES)


@dataclass(frozen=True, slots=True)
class SupervisorVerdict:
    """The answer the pipeline acts on. ``bounded_arguments`` is authoritative."""

    allowed: bool
    priority: CommandPriority
    bounded_arguments: Mapping[str, object] = field(default_factory=dict)
    code: str | None = None
    reason: str | None = None
    recovery: str | None = None
    clamped_fields: tuple[str, ...] = ()


class SafetySupervisor:
    """Owns arm state, watchdogs, and policy. Dispatches nothing itself."""

    def __init__(
        self,
        *,
        clock: Clock,
        policies: Iterable[SafetyPolicy] = (),
        watchdog_timeouts: Mapping[WatchdogKind, float] | None = None,
    ) -> None:
        self._clock = clock
        self._policies: dict[str, SafetyPolicy] = {policy.policy_id: policy for policy in policies}
        self._policies.setdefault("simulation-only", SafetyPolicy(policy_id="simulation-only"))
        self._timeouts: dict[WatchdogKind, float] = dict(
            watchdog_timeouts if watchdog_timeouts is not None else DEFAULT_WATCHDOG_TIMEOUTS
        )
        self._arms: dict[str, ArmState] = {}
        self._heartbeats: dict[tuple[str, WatchdogKind], float] = {}
        self._gate = FoundationSafetyGate()
        self._stopped_all_at: datetime | None = None
        self._disabled_sources: set[str] = set()

    # ---------------------------------------------------------- input sources

    def set_source_enabled(self, source: str, *, enabled: bool) -> None:
        """FR-067. Cut one input source off without stopping the whole class.

        "Disable Leap input" and "disconnect Quest control" are the same act
        from the runtime's side: a named source stops being able to cause
        motion, while everything else in the room carries on.
        """

        if enabled:
            self._disabled_sources.discard(source)
        else:
            self._disabled_sources.add(source)

    def disabled_sources(self) -> frozenset[str]:
        return frozenset(self._disabled_sources)

    # ----------------------------------------------------------------- policy

    def register_policy(self, policy: SafetyPolicy) -> None:
        self._policies[policy.policy_id] = policy

    def policy(self, policy_id: str) -> SafetyPolicy:
        try:
            return self._policies[policy_id]
        except KeyError as error:
            raise KeyError(f"Unknown safety policy {policy_id!r}") from error

    # ------------------------------------------------------------------ arming

    def arm(
        self,
        *,
        device_id: str,
        session_id: str,
        instructor_id: str,
        policy_id: str,
        program_validated: bool,
    ) -> ArmState:
        """FR-066 steps 3-6. Instructor-only, validated-only, and expiring."""

        if not instructor_id:
            raise ArmingError("Only an instructor may arm a physical device")
        if not program_validated:
            raise ArmingError("A program must validate before its devices may be armed")
        policy = self.policy(policy_id)
        now = self._now()
        state = ArmState(
            device_id=device_id,
            session_id=session_id,
            armed_by=instructor_id,
            armed_at=now,
            expires_at=now + policy.arm_ttl,
        )
        self._arms[device_id] = state
        return state

    def disarm(self, device_id: str) -> None:
        """FR-066 step 7. Also called after any stop or disconnect."""

        self._arms.pop(device_id, None)

    def disarm_all(self) -> tuple[str, ...]:
        disarmed = tuple(self._arms)
        self._arms.clear()
        return disarmed

    def arm_state(self, device_id: str) -> ArmState | None:
        state = self._arms.get(device_id)
        if state is None:
            return None
        if not state.is_active(now=self._now()):
            del self._arms[device_id]
            return None
        return state

    def is_armed(self, device_id: str) -> bool:
        return self.arm_state(device_id) is not None

    # --------------------------------------------------------------- watchdogs

    def heartbeat(self, *, device_id: str, kind: WatchdogKind) -> None:
        self._heartbeats[(device_id, kind)] = self._monotonic()

    def clear_watchdog(self, *, device_id: str, kind: WatchdogKind) -> None:
        self._heartbeats.pop((device_id, kind), None)

    def deadman_attested(self, device_id: str) -> bool:
        """ADR-028. True only while a fresh dead-man heartbeat keeps arriving.

        FR-068 forbids a student bypassing the dead-man control, which is not
        enforceable while the claim travels in the student's own request body.
        The runtime asks this instead, so releasing the control and losing the
        browser are the same event as far as a moving robot is concerned.
        """

        last_seen = self._heartbeats.get((device_id, WatchdogKind.QUEST_DEADMAN_HEARTBEAT))
        if last_seen is None:
            return False
        timeout = self._timeouts[WatchdogKind.QUEST_DEADMAN_HEARTBEAT]
        return (self._monotonic() - last_seen) <= timeout

    def timeout(self, kind: WatchdogKind) -> float:
        return self._timeouts[kind]

    def heartbeat_ages(self, device_id: str) -> Mapping[WatchdogKind, float]:
        """FR-065. How long ago each watchdog for one device last heard anything."""

        now = self._monotonic()
        return {
            kind: now - last_seen
            for (held_device_id, kind), last_seen in self._heartbeats.items()
            if held_device_id == device_id
        }

    def expired_watchdogs(self) -> tuple[WatchdogExpiry, ...]:
        """Every watchdog whose deadline has passed, newest deadline first."""

        now = self._monotonic()
        expiries: list[WatchdogExpiry] = []
        for (device_id, kind), last_seen in sorted(self._heartbeats.items()):
            timeout = self._timeouts[kind]
            elapsed = now - last_seen
            if elapsed <= timeout:
                continue
            action = (
                WatchdogAction.DISARM
                if kind is WatchdogKind.QUEST_DEADMAN_HEARTBEAT
                else WatchdogAction.STOP
            )
            expiries.append(
                WatchdogExpiry(
                    device_id=device_id, kind=kind, action=action, elapsed_seconds=elapsed
                )
            )
        return tuple(expiries)

    # ------------------------------------------------------------------ verdict

    def evaluate(
        self,
        command: DeviceCommandIntent,
        *,
        session_device_ids: Iterable[str],
        physical: bool,
    ) -> SupervisorVerdict:
        """Answer one command. Fail closed: unknown means denied."""

        priority = classify_priority(command)
        now = self._now()

        if command.action in _STOP_ACTIONS:
            # A stop is never blocked by arm state, ownership, or bounds.
            return SupervisorVerdict(allowed=True, priority=priority)

        if command.source in self._disabled_sources:
            return self._deny(
                priority,
                "SAFETY_POLICY_DENIED",
                f"Input source {command.source!r} is disabled for this classroom",
                "An instructor turned this input off. Ask them to enable it again.",
            )

        if command.deviceId not in set(session_device_ids):
            return self._deny(
                priority,
                "DEVICE_NOT_ASSIGNED",
                f"Device {command.deviceId!r} is not bound to session {command.sessionId!r}",
                "Bind the device to this session before sending commands to it.",
            )

        policy = self._policies.get(command.safetyContext.policyId)
        if policy is None:
            return self._deny(
                priority,
                "SAFETY_POLICY_DENIED",
                f"Unknown safety policy {command.safetyContext.policyId!r}",
                "Select a registered safety profile for this session.",
            )

        if not policy.permits(command.capability):
            return self._deny(
                priority,
                "DEVICE_CAPABILITY_UNSUPPORTED",
                f"Policy {policy.policy_id!r} does not permit {command.capability!r}",
                "Ask an instructor to choose a profile that allows this capability.",
            )

        # FR-074 is about authority, not physics: an AI may not initiate motion
        # even in simulation, because the habit is what the rule protects.
        if is_movement(command.capability) and command.source == "agent_mesh":
            return self._deny(
                priority,
                "SAFETY_POLICY_DENIED",
                "Agent Mesh may propose but may not initiate movement",
                "Ask a person to review and issue the movement themselves.",
            )

        if physical:
            # The Milestone 0 gate is the floor for physical execution. It is
            # deliberately not consulted in simulation: its arm requirement is a
            # rule about moving hardware, and applying it to a virtual robot
            # would make the simulation-first default (FR-062) unusable without
            # an instructor in the room.
            foundation: SafetyDecision = self._gate.evaluate(command, now=now)
            if not foundation.allowed:
                return SupervisorVerdict(
                    allowed=False,
                    priority=priority,
                    code=foundation.code,
                    reason=foundation.reason,
                    recovery="An instructor must arm the device before it can move.",
                )
            if is_movement(command.capability):
                denial = self._physical_movement_denial(command, policy=policy, now=now)
                if denial is not None:
                    return denial

        bounded, clamped = self._bound_arguments(command, policy=policy)
        return SupervisorVerdict(
            allowed=True,
            priority=priority,
            bounded_arguments=bounded,
            clamped_fields=clamped,
        )

    def _physical_movement_denial(
        self,
        command: DeviceCommandIntent,
        *,
        policy: SafetyPolicy,
        now: datetime,
    ) -> SupervisorVerdict | None:
        priority = classify_priority(command)
        arm = self.arm_state(command.deviceId)
        if arm is None:
            return self._deny(
                priority,
                "DEVICE_NOT_ARMED",
                f"Device {command.deviceId!r} is not armed or its arm window expired",
                "An instructor must arm the device again before it can move.",
            )
        if arm.session_id != command.sessionId:
            return self._deny(
                priority,
                "DEVICE_LEASE_CONFLICT",
                f"Device {command.deviceId!r} is armed for session {arm.session_id!r}",
                "Wait for the other session to finish, or ask an instructor to reassign it.",
            )
        if policy.require_deadman and not self.deadman_attested(command.deviceId):
            # Deliberately not `command.safetyContext.deadmanActive`: that field
            # is filled in by whoever sent the command (ADR-028).
            return self._deny(
                priority,
                "SAFETY_POLICY_DENIED",
                "No dead-man heartbeat has arrived for this device within the last "
                f"{self._timeouts[WatchdogKind.QUEST_DEADMAN_HEARTBEAT] * 1000:.0f} ms",
                "Hold the dead-man control while the robot is moving.",
            )
        confidence = command.safetyContext.inputConfidence
        if confidence is not None and confidence < policy.bounds.min_input_confidence:
            return self._deny(
                priority,
                "SAFETY_POLICY_DENIED",
                (
                    f"Input confidence {confidence:.2f} is below the required "
                    f"{policy.bounds.min_input_confidence:.2f}"
                ),
                "Improve tracking or confirm the command before the robot moves.",
            )
        del now
        return None

    def _bound_arguments(
        self, command: DeviceCommandIntent, *, policy: SafetyPolicy
    ) -> tuple[dict[str, object], tuple[str, ...]]:
        """FR-071. Clamp rather than reject, so a lesson keeps moving."""

        arguments = dict(command.arguments)
        if not is_movement(command.capability):
            return arguments, ()

        clamped: list[str] = []
        bounds = policy.bounds
        for name, ceiling in (
            ("speed", bounds.max_speed),
            ("acceleration", bounds.max_acceleration),
            ("durationSeconds", bounds.max_duration_seconds),
        ):
            if ceiling is None:
                continue
            value = arguments.get(name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            if abs(value) > ceiling:
                arguments[name] = ceiling if value > 0 else -ceiling
                clamped.append(name)

        if "durationSeconds" not in arguments:
            # An unbounded movement is not permitted to exist (FR-071).
            arguments["durationSeconds"] = bounds.max_duration_seconds
            clamped.append("durationSeconds")

        return arguments, tuple(clamped)

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _deny(
        priority: CommandPriority, code: str, reason: str, recovery: str
    ) -> SupervisorVerdict:
        return SupervisorVerdict(
            allowed=False, priority=priority, code=code, reason=reason, recovery=recovery
        )

    def _now(self) -> datetime:
        return self._clock.now()

    def _monotonic(self) -> float:
        return self._clock.monotonic()
