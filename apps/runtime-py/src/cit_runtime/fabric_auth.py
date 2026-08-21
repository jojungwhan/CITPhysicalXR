"""Independent, least-authority authentication for CIT Fabric operations."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .fabric_persistence import FabricIdentityRecord
from .fabric_repository import SQLiteFabricRepository

FABRIC_PERMISSIONS = frozenset(
    {
        "fabric.adapters.connect",
        "fabric.audit.read",
        "fabric.auth.issue",
        "fabric.auth.revoke",
        "fabric.commands.read",
        "fabric.commands.submit",
        "fabric.course.manage",
        "fabric.course.read",
        "fabric.events.publish",
        "fabric.events.read",
        "fabric.nodes.read",
        "fabric.nodes.write",
        "fabric.roles.assign",
        "fabric.sessions.manage",
        "fabric.sessions.read",
        "fabric.stop_all",
    }
)
INSTRUCTOR_PERMISSIONS = frozenset(
    {
        "fabric.audit.read",
        "fabric.commands.read",
        "fabric.commands.submit",
        "fabric.course.read",
        "fabric.events.read",
        "fabric.nodes.read",
        "fabric.roles.assign",
        "fabric.sessions.manage",
        "fabric.sessions.read",
        "fabric.stop_all",
    }
)
OBSERVER_PERMISSIONS = frozenset(
    {
        "fabric.commands.read",
        "fabric.course.read",
        "fabric.events.read",
        "fabric.nodes.read",
        "fabric.sessions.read",
    }
)
ADAPTER_PERMISSIONS = frozenset(
    {
        "fabric.adapters.connect",
        "fabric.events.publish",
        "fabric.nodes.write",
    }
)

_TOKEN_DOMAIN = b"cit-interaction-fabric-token-v1\x00"
_CONSOLE_TICKET_DOMAIN = b"cit-interaction-fabric-console-ticket-v1\x00"
_MIN_TOKEN_LENGTH = 32
_MAX_TOKEN_LENGTH = 512


@dataclass(frozen=True, slots=True)
class FabricBootstrapIdentity:
    identity_id: str
    token: str
    actor_type: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    site_id: str | None = None
    room_id: str | None = None
    session_id: str | None = None
    ttl: timedelta = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class FabricPrincipal:
    identity_id: str
    actor_type: str
    roles: tuple[str, ...]
    permissions: frozenset[str]
    site_id: str | None
    room_id: str | None
    session_id: str | None
    expires_at: datetime

    def permits(
        self,
        permission: str,
        *,
        site_id: str | None = None,
        room_id: str | None = None,
        session_id: str | None = None,
    ) -> bool:
        if permission not in self.permissions:
            return False
        if self.site_id is not None and site_id is not None and self.site_id != site_id:
            return False
        if self.room_id is not None and room_id is not None and self.room_id != room_id:
            return False
        return not (
            self.session_id is not None and session_id is not None and self.session_id != session_id
        )


@dataclass(frozen=True, slots=True)
class FabricConsoleGrant:
    identity_id: str
    permissions: tuple[str, ...]
    site_id: str | None
    room_id: str | None
    ticket_expires_at: datetime


class FabricAuthenticationError(PermissionError):
    """Raised when a credential is absent, invalid, expired, or revoked."""


class FabricAuthorizationError(PermissionError):
    """Raised when a valid identity lacks the requested scope."""


class FabricAuthService:
    def __init__(self, repository: SQLiteFabricRepository) -> None:
        self._repository = repository
        self._console_tickets: dict[str, FabricConsoleGrant] = {}

    def install_bootstrap_identities(
        self,
        identities: tuple[FabricBootstrapIdentity, ...],
        *,
        at: datetime,
    ) -> None:
        timestamp = _aware_utc(at)
        for identity in identities:
            self._validate_identity_values(
                roles=identity.roles,
                permissions=identity.permissions,
            )
            token_hash = self.hash_token(identity.token)
            self._repository.upsert_fabric_identity(
                FabricIdentityRecord(
                    identity_id=identity.identity_id,
                    actor_type=identity.actor_type,
                    roles=identity.roles,
                    permissions=identity.permissions,
                    site_id=identity.site_id,
                    room_id=identity.room_id,
                    session_id=identity.session_id,
                    token_hash=token_hash,
                    created_at=timestamp,
                    expires_at=timestamp + identity.ttl,
                    revoked_at=None,
                )
            )

    def authenticate(self, token: str, *, at: datetime) -> FabricPrincipal:
        timestamp = _aware_utc(at)
        token_hash = self.hash_token(token)
        record = self._repository.find_fabric_identity_by_hash(token_hash)
        if record is None or not hmac.compare_digest(record.token_hash, token_hash):
            raise FabricAuthenticationError("Fabric credential is invalid")
        if record.revoked_at is not None:
            raise FabricAuthenticationError("Fabric credential is revoked")
        if record.expires_at <= timestamp:
            raise FabricAuthenticationError("Fabric credential is expired")
        return _principal(record)

    def require(
        self,
        principal: FabricPrincipal,
        permission: str,
        *,
        site_id: str | None = None,
        room_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        if permission not in FABRIC_PERMISSIONS:
            raise ValueError(f"Unknown Fabric permission {permission!r}")
        if not principal.permits(
            permission,
            site_id=site_id,
            room_id=room_id,
            session_id=session_id,
        ):
            raise FabricAuthorizationError(
                f"Identity {principal.identity_id!r} lacks {permission!r} for this scope"
            )

    def issue(
        self,
        *,
        identity_id: str,
        actor_type: str,
        roles: tuple[str, ...],
        permissions: tuple[str, ...],
        site_id: str | None,
        room_id: str | None,
        session_id: str | None,
        ttl: timedelta,
        at: datetime,
    ) -> tuple[FabricIdentityRecord, str]:
        if ttl < timedelta(minutes=1) or ttl > timedelta(days=90):
            raise ValueError("Fabric identity TTL must be between one minute and 90 days")
        self._validate_identity_values(roles=roles, permissions=permissions)
        token = secrets.token_urlsafe(32)
        timestamp = _aware_utc(at)
        record = FabricIdentityRecord(
            identity_id=identity_id,
            actor_type=actor_type,
            roles=roles,
            permissions=permissions,
            site_id=site_id,
            room_id=room_id,
            session_id=session_id,
            token_hash=self.hash_token(token),
            created_at=timestamp,
            expires_at=timestamp + ttl,
            revoked_at=None,
        )
        return self._repository.upsert_fabric_identity(record), token

    def revoke(self, identity_id: str, *, at: datetime) -> bool:
        return self._repository.revoke_fabric_identity(identity_id, at=_aware_utc(at))

    def create_console_ticket(
        self,
        *,
        identity_id: str,
        permissions: tuple[str, ...],
        site_id: str | None,
        room_id: str | None,
        at: datetime,
        ttl: timedelta = timedelta(seconds=90),
    ) -> tuple[str, datetime]:
        """Create a short-lived, one-use handoff from the local launcher."""

        if ttl < timedelta(seconds=15) or ttl > timedelta(minutes=5):
            raise ValueError("Console ticket TTL must be between 15 seconds and five minutes")
        timestamp = _aware_utc(at)
        self._validate_identity_values(roles=("instructor",), permissions=permissions)
        self._drop_expired_console_tickets(at=timestamp)
        ticket = secrets.token_urlsafe(32)
        ticket_expires_at = timestamp + ttl
        self._console_tickets[self._hash_console_ticket(ticket)] = FabricConsoleGrant(
            identity_id=identity_id,
            permissions=permissions,
            site_id=site_id,
            room_id=room_id,
            ticket_expires_at=ticket_expires_at,
        )
        return ticket, ticket_expires_at

    def redeem_console_ticket(self, ticket: str, *, at: datetime) -> FabricConsoleGrant:
        """Consume a launcher ticket exactly once and return its tutor grant."""

        timestamp = _aware_utc(at)
        ticket_hash = self._hash_console_ticket(ticket)
        grant = self._console_tickets.pop(ticket_hash, None)
        self._drop_expired_console_tickets(at=timestamp)
        if grant is None or grant.ticket_expires_at <= timestamp:
            raise FabricAuthenticationError("Console access link is invalid or expired")
        return grant

    @staticmethod
    def hash_token(token: str) -> str:
        if not isinstance(token, str):
            raise FabricAuthenticationError("Fabric credential must be a string")
        if not _MIN_TOKEN_LENGTH <= len(token) <= _MAX_TOKEN_LENGTH:
            raise FabricAuthenticationError("Fabric credential length is invalid")
        if token != token.strip() or any(character.isspace() for character in token):
            raise FabricAuthenticationError("Fabric credential format is invalid")
        return hashlib.sha256(_TOKEN_DOMAIN + token.encode("utf-8")).hexdigest()

    @staticmethod
    def _hash_console_ticket(ticket: str) -> str:
        if not isinstance(ticket, str):
            raise FabricAuthenticationError("Console access link is invalid")
        if not _MIN_TOKEN_LENGTH <= len(ticket) <= 128:
            raise FabricAuthenticationError("Console access link is invalid")
        if ticket != ticket.strip() or any(character.isspace() for character in ticket):
            raise FabricAuthenticationError("Console access link is invalid")
        return hashlib.sha256(_CONSOLE_TICKET_DOMAIN + ticket.encode("utf-8")).hexdigest()

    def _drop_expired_console_tickets(self, *, at: datetime) -> None:
        expired = [
            ticket_hash
            for ticket_hash, grant in self._console_tickets.items()
            if grant.ticket_expires_at <= at
        ]
        for ticket_hash in expired:
            self._console_tickets.pop(ticket_hash, None)

    @staticmethod
    def _validate_identity_values(
        *,
        roles: tuple[str, ...],
        permissions: tuple[str, ...],
    ) -> None:
        if not roles or len(roles) != len(set(roles)):
            raise ValueError("Fabric identity roles must be non-empty and unique")
        if not permissions or len(permissions) != len(set(permissions)):
            raise ValueError("Fabric identity permissions must be non-empty and unique")
        unknown = set(permissions) - FABRIC_PERMISSIONS
        if unknown:
            raise ValueError(f"Unknown Fabric permissions: {', '.join(sorted(unknown))}")


def _principal(record: FabricIdentityRecord) -> FabricPrincipal:
    return FabricPrincipal(
        identity_id=record.identity_id,
        actor_type=record.actor_type,
        roles=record.roles,
        permissions=frozenset(record.permissions),
        site_id=record.site_id,
        room_id=record.room_id,
        session_id=record.session_id,
        expires_at=record.expires_at,
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Fabric authentication time must include a UTC offset")
    return value.astimezone(UTC)
