"""Program sessions and their explicit state machine.

FR-017 fixes the session fields; FR-018 fixes the state names. Transitions are
declared as data so an illegal move is a rejected value rather than a bug that
only shows up on hardware.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType


class SessionState(StrEnum):
    """FR-018. Every state a program session may occupy."""

    CREATED = "created"
    VALIDATING = "validating"
    WAITING_FOR_DEVICES = "waiting_for_devices"
    WAITING_FOR_ARM = "waiting_for_arm"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    DISCONNECTED = "disconnected"
    EMERGENCY_STOPPED = "emergency_stopped"


class AuthoringMode(StrEnum):
    BLOCKS = "blocks"
    PYTHON = "python"


class ExecutionMode(StrEnum):
    """FR-062. Simulation is the default; physical execution is opted into."""

    SIMULATION = "simulation"
    PHYSICAL = "physical"


class FailurePolicy(StrEnum):
    """FR-058. What the other devices do when one of them fails.

    The PRD names stopping coordinated movement as the physical default, and it
    is the right default for a reason a simulation does not have: two robots
    driving a shared route are only safe together while both are still under
    control. ``CONTINUE`` exists because a lesson where one hub is flat should
    not have to stop the rest of the room, and an instructor may say so.
    """

    STOP_COORDINATED = "stop_coordinated"
    CONTINUE = "continue"


TERMINAL_STATES: frozenset[SessionState] = frozenset(
    {
        SessionState.STOPPED,
        SessionState.COMPLETED,
        SessionState.FAILED,
        SessionState.EMERGENCY_STOPPED,
    }
)

# Any state may fall to a stop path, so the emergency and failure edges are
# added to every non-terminal state below rather than repeated here.
_PROGRESS_TRANSITIONS: Mapping[SessionState, frozenset[SessionState]] = MappingProxyType(
    {
        SessionState.CREATED: frozenset({SessionState.VALIDATING}),
        SessionState.VALIDATING: frozenset({SessionState.WAITING_FOR_DEVICES, SessionState.READY}),
        SessionState.WAITING_FOR_DEVICES: frozenset(
            {SessionState.WAITING_FOR_ARM, SessionState.READY}
        ),
        SessionState.WAITING_FOR_ARM: frozenset({SessionState.READY}),
        SessionState.READY: frozenset({SessionState.RUNNING, SessionState.WAITING_FOR_ARM}),
        SessionState.RUNNING: frozenset({SessionState.PAUSED, SessionState.STOPPING}),
        SessionState.PAUSED: frozenset({SessionState.RUNNING, SessionState.STOPPING}),
        SessionState.STOPPING: frozenset({SessionState.STOPPED, SessionState.COMPLETED}),
        SessionState.DISCONNECTED: frozenset({SessionState.WAITING_FOR_DEVICES}),
    }
)

_UNIVERSAL_ESCAPES: frozenset[SessionState] = frozenset(
    {
        SessionState.EMERGENCY_STOPPED,
        SessionState.FAILED,
        SessionState.STOPPING,
        SessionState.DISCONNECTED,
    }
)


def allowed_transitions(state: SessionState) -> frozenset[SessionState]:
    """Return every state reachable in one step from ``state``."""

    if state in TERMINAL_STATES:
        return frozenset()
    return _PROGRESS_TRANSITIONS.get(state, frozenset()) | _UNIVERSAL_ESCAPES


class SessionTransitionError(RuntimeError):
    def __init__(self, *, session_id: str, current: SessionState, requested: SessionState) -> None:
        self.session_id = session_id
        self.current = current
        self.requested = requested
        super().__init__(
            f"Session {session_id!r} cannot move from {current.value!r} to {requested.value!r}"
        )


@dataclass(frozen=True, slots=True)
class ProgramSession:
    """FR-017. Immutable; every transition produces a new value."""

    session_id: str
    project_id: str
    authoring_mode: AuthoringMode
    execution_mode: ExecutionMode
    user_id: str
    safety_policy_id: str
    started_at: datetime
    last_activity_at: datetime
    state: SessionState = SessionState.CREATED
    instructor_id: str | None = None
    quest_client_id: str | None = None
    device_bindings: tuple[str, ...] = field(default=())
    ended_at: datetime | None = None
    failure_reason: str | None = None
    failure_policy: FailurePolicy = FailurePolicy.STOP_COORDINATED

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def transition(
        self,
        requested: SessionState,
        *,
        at: datetime,
        reason: str | None = None,
    ) -> ProgramSession:
        if requested not in allowed_transitions(self.state):
            raise SessionTransitionError(
                session_id=self.session_id, current=self.state, requested=requested
            )
        ended = at if requested in TERMINAL_STATES else None
        return replace(
            self,
            state=requested,
            last_activity_at=at,
            ended_at=ended,
            failure_reason=reason if reason is not None else self.failure_reason,
        )

    def touch(self, *, at: datetime) -> ProgramSession:
        return replace(self, last_activity_at=at)

    def bind_devices(self, device_ids: tuple[str, ...], *, at: datetime) -> ProgramSession:
        if self.is_terminal:
            raise SessionTransitionError(
                session_id=self.session_id, current=self.state, requested=self.state
            )
        if len(set(device_ids)) != len(device_ids):
            raise ValueError("A session cannot bind the same device twice")
        return replace(self, device_bindings=device_ids, last_activity_at=at)


class SessionRepository:
    """Process-local session storage. One runtime owns one repository."""

    def __init__(self) -> None:
        self._sessions: dict[str, ProgramSession] = {}

    def add(self, session: ProgramSession) -> ProgramSession:
        if session.session_id in self._sessions:
            raise ValueError(f"Session {session.session_id!r} already exists")
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> ProgramSession:
        try:
            return self._sessions[session_id]
        except KeyError as error:
            raise KeyError(f"Unknown session {session_id!r}") from error

    def save(self, session: ProgramSession) -> ProgramSession:
        if session.session_id not in self._sessions:
            raise KeyError(f"Unknown session {session.session_id!r}")
        self._sessions[session.session_id] = session
        return session

    def list(self) -> tuple[ProgramSession, ...]:
        return tuple(self._sessions.values())

    def active_for_device(self, device_id: str) -> tuple[ProgramSession, ...]:
        return tuple(
            session
            for session in self._sessions.values()
            if device_id in session.device_bindings and not session.is_terminal
        )
