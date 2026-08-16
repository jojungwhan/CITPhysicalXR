"""FR-018. Every declared state exists and illegal moves are refused."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from cit_runtime import (
    AuthoringMode,
    ExecutionMode,
    ProgramSession,
    SessionRepository,
    SessionState,
    SessionTransitionError,
    allowed_transitions,
)

PRD_STATES = {
    "created",
    "validating",
    "waiting_for_devices",
    "waiting_for_arm",
    "ready",
    "running",
    "paused",
    "stopping",
    "stopped",
    "completed",
    "failed",
    "disconnected",
    "emergency_stopped",
}


def make_session(**overrides: object) -> ProgramSession:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    defaults: dict[str, object] = {
        "session_id": "session-1",
        "project_id": "project-1",
        "authoring_mode": AuthoringMode.BLOCKS,
        "execution_mode": ExecutionMode.SIMULATION,
        "user_id": "student-1",
        "safety_policy_id": "simulation-only",
        "started_at": now,
        "last_activity_at": now,
    }
    defaults.update(overrides)
    return ProgramSession(**defaults)  # type: ignore[arg-type]


def test_state_names_match_the_prd_exactly() -> None:
    assert {state.value for state in SessionState} == PRD_STATES


def test_happy_path_reaches_completed() -> None:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    session = make_session()
    for state in (
        SessionState.VALIDATING,
        SessionState.READY,
        SessionState.RUNNING,
        SessionState.STOPPING,
        SessionState.COMPLETED,
    ):
        session = session.transition(state, at=at)
    assert session.state is SessionState.COMPLETED
    assert session.is_terminal
    assert session.ended_at == at


def test_illegal_transition_is_refused() -> None:
    session = make_session()
    with pytest.raises(SessionTransitionError):
        session.transition(SessionState.RUNNING, at=datetime(2026, 1, 1, tzinfo=UTC))


def test_every_non_terminal_state_can_reach_emergency_stopped() -> None:
    for state in SessionState:
        if state.value in {"stopped", "completed", "failed", "emergency_stopped"}:
            assert allowed_transitions(state) == frozenset()
            continue
        assert SessionState.EMERGENCY_STOPPED in allowed_transitions(state)


def test_terminal_session_cannot_be_revived() -> None:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    session = make_session().transition(SessionState.FAILED, at=at, reason="adapter crash")
    assert session.failure_reason == "adapter crash"
    with pytest.raises(SessionTransitionError):
        session.transition(SessionState.RUNNING, at=at)


def test_duplicate_device_binding_is_refused() -> None:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="same device twice"):
        make_session().bind_devices(("fake-s1-main", "fake-s1-main"), at=at)


def test_repository_finds_active_sessions_for_a_device() -> None:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    repository = SessionRepository()
    live = repository.add(make_session().bind_devices(("fake-s1-main",), at=at))
    dead = make_session(session_id="session-2").bind_devices(("fake-s1-main",), at=at)
    repository.add(dead.transition(SessionState.FAILED, at=at))

    active = repository.active_for_device("fake-s1-main")
    assert [session.session_id for session in active] == [live.session_id]


def test_adding_a_duplicate_session_id_is_refused() -> None:
    repository = SessionRepository()
    repository.add(make_session())
    with pytest.raises(ValueError, match="already exists"):
        repository.add(make_session())
