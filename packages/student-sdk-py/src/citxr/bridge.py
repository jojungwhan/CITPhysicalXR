"""The constrained RPC boundary between student code and the runtime.

FR-013 is enforced by what this module does *not* contain. Student code holds a
``Bridge``; a bridge can send one of a fixed set of named calls and nothing else.
There is no filesystem handle, no socket, no subprocess, no environment access,
no adapter object, and no credential anywhere on this path. A student who
reaches for the bridge directly still cannot reach past the runtime's safety
supervisor, because the bridge only knows how to ask.

The transport is injected. In the browser it is a Pyodide worker posting to the
host page; in tests it is an in-memory fake. The SDK never opens a connection.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

# The complete set of calls student code may cause. Anything else is a bug in
# the SDK, not a capability a student can reach for.
ALLOWED_CALLS: frozenset[str] = frozenset(
    {
        "command",
        "read_sensor",
        "log",
        "sleep",
        "device_info",
    }
)


class TransportError(RuntimeError):
    """The runtime could not be reached, or refused to answer."""


class Transport(Protocol):
    """One async call out. Implementations must not add methods."""

    async def call(self, method: str, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


class CommandRejected(RuntimeError):
    """The runtime refused a command. Carries what a student should do next."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        recovery: str,
        device_id: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.recovery = recovery
        self.device_id = device_id
        super().__init__(f"{code}: {message} ({recovery})")


class Bridge:
    """Wraps a transport so only allowlisted calls can be made."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport
        self._cancelled = False

    def cancel(self) -> None:
        """FR-015. Flips the flag every checkpoint reads."""

        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    async def call(self, method: str, **payload: Any) -> Mapping[str, Any]:
        if method not in ALLOWED_CALLS:
            raise TransportError(
                f"{method!r} is not a permitted runtime call; "
                f"student code may only use {sorted(ALLOWED_CALLS)}"
            )
        result = await self._transport.call(method, payload)
        if result.get("accepted") is False:
            raise CommandRejected(
                code=str(result.get("code", "SAFETY_POLICY_DENIED")),
                message=str(result.get("message", "The runtime refused this command.")),
                recovery=str(result.get("recovery", "Ask an instructor for help.")),
                device_id=payload.get("device_id"),
            )
        return result


class CancelledError(RuntimeError):
    """Raised at a checkpoint after the session was stopped."""


_ACTIVE: list[Bridge] = []


def set_bridge(bridge: Bridge) -> None:
    """Install the bridge a program will use. The host calls this, not a student."""

    _ACTIVE.clear()
    _ACTIVE.append(bridge)


def active_bridge() -> Bridge:
    if not _ACTIVE:
        raise TransportError(
            "No runtime bridge is installed. A program must be started by the Studio."
        )
    return _ACTIVE[0]


def checkpoint() -> None:
    """FR-015. Every loop and handler passes through here."""

    if _ACTIVE and _ACTIVE[0].cancelled:
        raise CancelledError("The session was stopped.")


AsyncCallable = Callable[[], Awaitable[None]]
