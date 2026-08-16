"""In-memory command identity claims used before any adapter dispatch."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from cit_protocol import DeviceCommandIntent


class CommandDisposition(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    EXPIRED = "expired"


class InMemoryCommandLedger:
    """Claim fresh command identities exactly once for the process lifetime."""

    def __init__(self) -> None:
        self._claims: dict[str, datetime] = {}

    def claim(self, command: DeviceCommandIntent, *, now: datetime) -> CommandDisposition:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Command claim time must include a UTC offset")
        if command.expiresAt <= now:
            return CommandDisposition.EXPIRED
        active_expiry = self._claims.get(command.idempotencyKey)
        if active_expiry is not None and active_expiry > now:
            return CommandDisposition.DUPLICATE
        self._claims[command.idempotencyKey] = command.expiresAt
        return CommandDisposition.ACCEPTED
