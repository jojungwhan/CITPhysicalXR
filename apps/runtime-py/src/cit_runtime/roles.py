"""Who is asking, and what that lets them do.

FR-068 is a list of things a student must not be able to do. None of it can be
enforced while identity is a field in the request body, so identity here is a
token the runtime issued and nothing else (ADR-027). The runtime holds only the
SHA-256 digest of a token, so a memory dump or an accidental log line cannot
yield a working one.

Authorization lives here rather than in ``api.py`` because a safety rule that
can only be tested through a web server is a safety rule nobody tests. Every
privileged action is named in :class:`Action`, and :func:`authorize` is the only
place that answers.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

DEFAULT_TOKEN_TTL = timedelta(hours=12)

# Long enough that guessing it over loopback is pointless, short enough that an
# instructor can read it off the runtime log and type it. The runtime does not
# listen on a routable interface (ADR-002), so this defends against the other
# tab on the same machine, not against the network.
_PASSCODE_BYTES = 4


class Role(StrEnum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"


class Action(StrEnum):
    """Every action that is not simply "a student working on their own program".

    Anything absent from this enum is permitted to any authenticated principal
    acting on their own session. Anything present is instructor-only.
    """

    DISCOVER_DEVICES = "devices.discover"
    DISCONNECT_DEVICE = "devices.disconnect"
    REASSIGN_DEVICE = "devices.reassign"
    ARM_DEVICE = "safety.arm"
    DISARM_DEVICE = "safety.disarm"
    STOP_ALL = "safety.stop_all"
    REVOKE_LEASE = "safety.revoke_lease"
    CLEAR_QUEUE = "safety.clear_queue"
    SET_INPUT_ENABLED = "safety.set_input_enabled"
    SET_SAFETY_POLICY = "safety.set_policy"
    SET_FAILURE_POLICY = "session.set_failure_policy"
    CREATE_PHYSICAL_SESSION = "session.create_physical"
    ISSUE_INSTRUCTOR_COMMAND = "command.instructor_source"
    READ_CLASSROOM = "classroom.read"
    EXPORT_AUDIT = "audit.export"
    MANAGE_RETENTION = "retention.manage"
    REPLAY_TO_LIVE = "replay.to_live"


# FR-068, stated positively. An action reaches this table or it is not privileged.
_REQUIRED_ROLE: Mapping[Action, Role] = {action: Role.INSTRUCTOR for action in Action}

# FR-074 and ADR-027. A source is what the runtime knows about the caller, not
# what the caller claims: `agent_mesh`, `quest`, and `leap` arrive through their
# own adapters in later milestones and are never accepted from a browser.
_ALLOWED_SOURCES: Mapping[Role, frozenset[str]] = {
    Role.STUDENT: frozenset({"student_blocks", "student_python"}),
    Role.INSTRUCTOR: frozenset({"student_blocks", "student_python", "instructor"}),
}


class AuthenticationError(RuntimeError):
    """No token, an unknown token, or an expired one. Maps to HTTP 401."""


class AuthorizationError(RuntimeError):
    """A known principal who may not do this. Maps to HTTP 403."""


@dataclass(frozen=True, slots=True)
class Principal:
    """One authenticated actor. Immutable for the life of its token."""

    actor_id: str
    role: Role
    display_name: str
    issued_at: datetime
    expires_at: datetime

    @property
    def is_instructor(self) -> bool:
        return self.role is Role.INSTRUCTOR

    def is_active(self, *, now: datetime) -> bool:
        return now < self.expires_at


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Authority:
    """Issues, validates, and revokes local scoped tokens (NFR 12.5)."""

    def __init__(
        self,
        *,
        instructor_passcode: str | None = None,
        token_ttl: timedelta = DEFAULT_TOKEN_TTL,
    ) -> None:
        self.instructor_passcode = instructor_passcode or secrets.token_hex(_PASSCODE_BYTES)
        self._ttl = token_ttl
        self._principals: dict[str, Principal] = {}

    def join(
        self,
        *,
        actor_id: str,
        role: Role,
        now: datetime,
        passcode: str | None = None,
        display_name: str | None = None,
    ) -> tuple[str, Principal]:
        """Issue a token. The instructor role costs a passcode; a student joins."""

        if not actor_id.strip():
            raise AuthenticationError("An actor id is required to join")
        if role is Role.INSTRUCTOR and not secrets.compare_digest(
            passcode or "", self.instructor_passcode
        ):
            raise AuthorizationError(
                "The instructor passcode does not match. It is printed once in the runtime log "
                "when the runtime starts."
            )
        token = secrets.token_urlsafe(32)
        principal = Principal(
            actor_id=actor_id,
            role=role,
            display_name=display_name or actor_id,
            issued_at=now,
            expires_at=now + self._ttl,
        )
        self._principals[_digest(token)] = principal
        return token, principal

    def principal(self, token: str | None, *, now: datetime) -> Principal:
        """Resolve a token, or refuse. An expired token is dropped as it is read."""

        if not token:
            raise AuthenticationError(
                "This request needs a runtime token. Join the classroom first."
            )
        key = _digest(token)
        found = self._principals.get(key)
        if found is None:
            raise AuthenticationError("Unknown or revoked token. Join the classroom again.")
        if not found.is_active(now=now):
            del self._principals[key]
            raise AuthenticationError("This token has expired. Join the classroom again.")
        return found

    def revoke(self, token: str) -> bool:
        return self._principals.pop(_digest(token), None) is not None

    def revoke_actor(self, actor_id: str) -> int:
        """Drop every token held by one actor. Used when a class ends."""

        doomed = [key for key, held in self._principals.items() if held.actor_id == actor_id]
        for key in doomed:
            del self._principals[key]
        return len(doomed)

    def principals(self) -> tuple[Principal, ...]:
        return tuple(self._principals.values())


def authorize(principal: Principal, action: Action) -> None:
    """Raise unless ``principal`` may perform ``action``. Fail closed."""

    required = _REQUIRED_ROLE.get(action)
    if required is None:
        return
    if principal.role is not required:
        raise AuthorizationError(
            f"{action.value!r} is an instructor action. "
            f"{principal.display_name} is signed in as a {principal.role.value}."
        )


def require_session_owner(principal: Principal, *, session_user_id: str) -> None:
    """A student may only act on their own session; an instructor on any."""

    if principal.is_instructor or principal.actor_id == session_user_id:
        return
    raise AuthorizationError(
        f"This session belongs to {session_user_id!r}. Ask an instructor to act on it."
    )


def resolve_source(principal: Principal, requested: str | None) -> str:
    """Turn a claimed command source into one this principal may actually use."""

    allowed: Iterable[str] = _ALLOWED_SOURCES[principal.role]
    if requested is None:
        return "instructor" if principal.is_instructor else "student_blocks"
    if requested not in allowed:
        raise AuthorizationError(
            f"A {principal.role.value} may not issue commands with source {requested!r}."
        )
    return requested
