"""The runtime end of the student RPC bridge (FR-013).

The student worker can ask for exactly five things. This module turns each one
into an ordinary runtime call and nothing more. It is the only place student
input reaches the pipeline, so it is where aliases are resolved and where the
answer is shaped into something a student can act on.

A rejected command comes back as data, not an exception, carrying the code, the
reason, and what to do next -- FR-012's "suggested correction" for the runtime
half of the story.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any
from uuid import uuid4

from cit_protocol import DeviceCommandIntent
from pydantic import ValidationError

from .runtime import Runtime
from .sessions import ExecutionMode

STUDENT_SOURCES: frozenset[str] = frozenset({"student_blocks", "student_python"})


class StudentBridgeError(RuntimeError):
    """The request was malformed. Distinct from a command the runtime refused."""


def _plain(value: Any) -> str:
    """Unwrap a generated RootModel to the string a student should see."""

    root = getattr(value, "root", value)
    return str(root)


class StudentBridge:
    """Serves one session's student program."""

    def __init__(
        self,
        runtime: Runtime,
        *,
        session_id: str,
        source: str = "student_python",
        aliases: Mapping[str, str] | None = None,
        command_ttl: timedelta = timedelta(seconds=5),
    ) -> None:
        if source not in STUDENT_SOURCES:
            raise StudentBridgeError(f"A student program may only act as {sorted(STUDENT_SOURCES)}")
        self._runtime = runtime
        self._session_id = session_id
        self._source = source
        self._aliases = dict(aliases or {})
        self._command_ttl = command_ttl
        self.deadman_active = False
        self.input_confidence: float | None = None

    def bind_alias(self, alias: str, device_id: str) -> None:
        self._aliases[alias] = device_id

    def resolve(self, device_ref: str) -> str:
        """Alias or exact id. Never a family, a prefix, or a nearest match."""

        resolved = self._aliases.get(device_ref, device_ref)
        try:
            self._runtime.registry.get(resolved)
        except KeyError as error:
            known = ", ".join(sorted(self._aliases)) or "none"
            raise StudentBridgeError(
                f"There is no device called {device_ref!r}. Bound names in this project: {known}."
            ) from error
        return resolved

    async def call(self, method: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        handler = {
            "command": self._command,
            "read_sensor": self._read_sensor,
            "log": self._log,
            "device_info": self._device_info,
            "sleep": self._sleep,
        }.get(method)
        if handler is None:
            raise StudentBridgeError(f"{method!r} is not a permitted runtime call")
        return await handler(payload)

    # ------------------------------------------------------------------ methods

    async def _command(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        device_id = self.resolve(str(payload["device_id"]))
        capability = str(payload["capability"])
        action = str(payload["action"])
        arguments = dict(payload.get("arguments") or {})

        session = self._runtime.sessions.get(self._session_id)
        now = self._runtime.clock.now()
        try:
            intent = DeviceCommandIntent.model_validate(
                {
                    "commandId": str(uuid4()),
                    "sessionId": self._session_id,
                    "deviceId": device_id,
                    "capability": capability,
                    "action": action,
                    "arguments": arguments,
                    "source": self._source,
                    "issuedAt": now,
                    "expiresAt": now + self._command_ttl,
                    "idempotencyKey": str(uuid4()),
                    "safetyContext": {
                        "policyId": session.safety_policy_id,
                        "armed": self._runtime.supervisor.is_armed(device_id),
                        "deadmanActive": self.deadman_active,
                        "inputConfidence": self.input_confidence,
                    },
                }
            )
        except ValidationError as error:
            # Student code is untrusted input. A malformed command has to come
            # back as a readable refusal, not a 500 that reads "Internal Server
            # Error" in the console of a child trying to move a robot.
            raise StudentBridgeError(
                f"{capability!r} is not a valid capability and action pair. "
                "A capability looks like 'drive.velocity'."
            ) from error

        dispatch = await self._runtime.submit(intent)
        if dispatch.error is not None:
            return {
                "accepted": False,
                "code": dispatch.error.code,
                "message": dispatch.error.message,
                "recovery": dispatch.error.recoverySuggestion,
                "deviceId": device_id,
            }
        result = dispatch.result
        if result is not None and not dispatch.accepted:
            # The runtime let the command through and the device itself refused
            # it -- a port with no motor in it, a capability the hub does not
            # have. The device said something useful; a student who only sees
            # "rejected" has been told their robot is broken.
            details = dict(result.details.model_dump()) if result.details is not None else {}
            return {
                "accepted": False,
                "status": result.status,
                "code": str(details.get("code", "DEVICE_CAPABILITY_UNSUPPORTED")),
                "message": result.message or f"The device refused this command ({result.status}).",
                "recovery": "Fix what the device named above, then run the program again.",
                "deviceId": device_id,
            }
        return {
            "accepted": True,
            "status": result.status if result else "unknown",
            "clampedFields": list(dispatch.clamped_fields),
            "deviceId": device_id,
        }

    async def _read_sensor(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        device_id = self.resolve(str(payload["device_id"]))
        sensor = str(payload["sensor"])
        history = self._runtime.router.history(device_id=device_id)
        for event in reversed(history):
            if event.name == sensor or event.name.endswith(f".{sensor}"):
                return {"accepted": True, "values": dict(event.values)}
        return {
            "accepted": True,
            "values": {},
            "message": f"No reading from {sensor!r} yet.",
        }

    async def _log(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self._runtime.logger.info(
            "student log",
            sessionId=self._session_id,
            reason=str(payload.get("message", "")),
        )
        return {"accepted": True}

    async def _device_info(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        device_id = self.resolve(str(payload["device_id"]))
        registered = self._runtime.registry.get(device_id)
        session = self._runtime.sessions.get(self._session_id)
        return {
            "accepted": True,
            "deviceId": registered.device_id,
            "displayName": registered.descriptor.displayName,
            "model": _plain(registered.descriptor.model),
            # The generated protocol models wrap these in pydantic RootModel, so
            # `.root` is the actual string. A student must receive plain values,
            # not objects whose str() is "root='drive.velocity'".
            "capabilities": [
                _plain(capability) for capability in registered.descriptor.capabilities
            ],
            "physical": registered.physical,
            "state": registered.state.value,
            "armed": self._runtime.supervisor.is_armed(device_id),
            "executionMode": session.execution_mode.value,
        }

    async def _sleep(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        # Sleeping happens in the student's own event loop; the runtime is only
        # told so a long wait shows up in the console rather than looking hung.
        return {"accepted": True, "seconds": float(payload.get("seconds", 0.0))}

    # ------------------------------------------------------------------ helpers

    @property
    def is_physical(self) -> bool:
        session = self._runtime.sessions.get(self._session_id)
        return session.execution_mode is ExecutionMode.PHYSICAL
