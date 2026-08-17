"""The local runtime API.

The PRD forbids exposing robot control to the public internet, so the server
binds the loopback interface and refuses to start on any other host unless the
caller passes an explicit override that is recorded in the log. There is no
shell endpoint, no subprocess endpoint, and no eval: every route below maps to a
named runtime method with a typed body.

Since Milestone 6 every route that changes anything also needs a token the
runtime issued (ADR-027). This module does not decide who may do what --
``cit_runtime.roles`` does, and the only thing that happens here is turning its
refusal into a status code. A route that looks safe because the Studio hides its
button is not safe; a route that calls ``authorize`` is.

Events reach the Studio over a WebSocket on the same origin, which keeps the
whole system working with the network cable unplugged (FR-085). A student's
socket carries only their own devices' events: one classroom, several browsers,
no shared console (FR-068).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from cit_protocol import DeviceCommandIntent, DeviceEvent
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .audit import AuditAction, audit_entries_to_jsonl
from .projects import ProjectStoreError
from .registry import DeviceAssignmentError
from .retention import RetentionPolicy, replay_package
from .roles import (
    Action,
    AuthenticationError,
    Authority,
    AuthorizationError,
    Principal,
    Role,
    authorize,
    require_session_owner,
    resolve_source,
)
from .runtime import Runtime
from .sessions import (
    AuthoringMode,
    ExecutionMode,
    FailurePolicy,
    SessionState,
    SessionTransitionError,
)
from .student_bridge import StudentBridge, StudentBridgeError
from .supervisor import WatchdogKind

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

# The Studio dev server and the built bundle are the only browser origins that
# may drive a robot. A wildcard here would let any page on the machine's browser
# reach the runtime.
DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
)


class JoinRequest(BaseModel):
    actor_id: str = Field(min_length=1, max_length=128)
    role: Role = Role.STUDENT
    display_name: str | None = Field(default=None, max_length=128)
    passcode: str | None = Field(default=None, max_length=128)


class CreateSessionRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    authoring_mode: AuthoringMode = AuthoringMode.BLOCKS
    execution_mode: ExecutionMode = ExecutionMode.SIMULATION
    instructor_id: str | None = None
    safety_policy_id: str = "simulation-only"


class BindDevicesRequest(BaseModel):
    device_ids: list[str] = Field(min_length=1, max_length=32)


class ArmRequest(BaseModel):
    session_id: str
    device_id: str
    ttl_seconds: float | None = Field(default=None, gt=0, le=3600)


class HeartbeatRequest(BaseModel):
    device_id: str
    kind: WatchdogKind


class StopRequest(BaseModel):
    reason: str = Field(default="manual stop", min_length=1, max_length=200)
    device_id: str | None = None


class DeviceRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="instructor action", min_length=1, max_length=200)


class ClearQueueRequest(BaseModel):
    device_id: str | None = None


class InputSourceRequest(BaseModel):
    source: Literal["quest", "leap", "agent_mesh", "student_blocks", "student_python"]
    enabled: bool


class FailurePolicyRequest(BaseModel):
    policy: FailurePolicy


class RetentionRequest(BaseModel):
    max_recordings: int = Field(gt=0, le=10000)
    retention_days: int = Field(gt=0, le=3650)


class RecordingRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)


class ProjectRequest(BaseModel):
    project: dict[str, Any]


class StudentRpcRequest(BaseModel):
    """One call from a student program, relayed by the Studio's worker host."""

    session_id: str
    method: Literal["command", "read_sensor", "log", "device_info", "sleep"]
    payload: dict[str, Any] = Field(default_factory=dict)
    aliases: dict[str, str] = Field(default_factory=dict)
    input_confidence: float | None = Field(default=None, ge=0, le=1)


class TransitionRequest(BaseModel):
    state: SessionState
    reason: str | None = Field(default=None, max_length=200)


class SimpleCommandRequest(BaseModel):
    """A Studio-shaped command. The runtime fills in every safety field.

    ``source`` is a request, not a fact: it is checked against the caller's role
    and replaced by what they are actually allowed to claim (ADR-027). There is
    no ``deadman_active`` field, because a dead-man control that a caller can
    assert is not a dead-man control (ADR-028).
    """

    session_id: str
    device_id: str
    capability: str
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    source: Literal["student_blocks", "student_python", "instructor"] | None = None
    input_confidence: float | None = Field(default=None, ge=0, le=1)
    ttl_seconds: float = Field(default=5.0, gt=0, le=60)


EventFilter = Callable[[DeviceEvent], bool]


class EventBroadcaster:
    """Fans router events out to connected sockets, each with its own filter.

    The filter is asked per event rather than fixed at connect time, so a
    student who binds a device mid-lesson starts seeing it without reconnecting,
    and one who loses it stops.
    """

    def __init__(self) -> None:
        self._clients: dict[WebSocket, EventFilter] = {}
        self._queue: asyncio.Queue[DeviceEvent] = asyncio.Queue(maxsize=1024)

    def register(self, websocket: WebSocket, wants: EventFilter) -> None:
        self._clients[websocket] = wants

    def unregister(self, websocket: WebSocket) -> None:
        self._clients.pop(websocket, None)

    def on_event(self, event: DeviceEvent) -> None:
        """Called from the router. Never blocks; drops on backpressure."""

        with suppress(asyncio.QueueFull):
            self._queue.put_nowait(event)

    async def pump(self) -> None:
        while True:
            event = await self._queue.get()
            payload = json.dumps(
                {
                    "kind": "device_event",
                    "event": json.loads(event.model_dump_json(exclude_none=True)),
                }
            )
            for client, wants in list(self._clients.items()):
                if not wants(event):
                    continue
                try:
                    await client.send_text(payload)
                except Exception:
                    self.unregister(client)


def _describe_device(runtime: Runtime, device_id: str) -> dict[str, Any]:
    device = runtime.registry.get(device_id)
    arm = runtime.supervisor.arm_state(device_id)
    return {
        "deviceId": device.device_id,
        "displayName": device.descriptor.displayName,
        "deviceType": device.descriptor.deviceType,
        "model": device.descriptor.model,
        "physical": device.physical,
        "state": device.state.value,
        "capabilities": list(device.descriptor.capabilities),
        "assignedSessionId": device.assigned_session_id,
        "armed": arm is not None,
        "armExpiresAt": arm.expires_at.isoformat() if arm is not None else None,
        "failureReason": device.failure_reason,
    }


def _describe_session(runtime: Runtime, session_id: str) -> dict[str, Any]:
    session = runtime.sessions.get(session_id)
    return {
        "sessionId": session.session_id,
        "projectId": session.project_id,
        "state": session.state.value,
        "authoringMode": session.authoring_mode.value,
        "executionMode": session.execution_mode.value,
        "userId": session.user_id,
        "instructorId": session.instructor_id,
        "safetyPolicyId": session.safety_policy_id,
        "failurePolicy": session.failure_policy.value,
        "deviceBindings": list(session.device_bindings),
        "startedAt": session.started_at.isoformat(),
        "lastActivityAt": session.last_activity_at.isoformat(),
        "endedAt": session.ended_at.isoformat() if session.ended_at else None,
    }


def _visible_device_ids(runtime: Runtime, principal: Principal) -> frozenset[str] | None:
    """Which devices this principal may see. ``None`` means all of them."""

    if principal.is_instructor:
        return None
    owned = {
        session.session_id
        for session in runtime.sessions.list()
        if session.user_id == principal.actor_id
    }
    return frozenset(
        device.device_id
        for device in runtime.registry.list()
        # An unassigned device is visible to everyone: a student has to be able
        # to see a free robot in order to ask for it.
        if device.assigned_session_id is None or device.assigned_session_id in owned
    )


def create_app(runtime: Runtime | None = None) -> FastAPI:
    """Build the ASGI app. A caller may inject a runtime for testing."""

    active = runtime if runtime is not None else Runtime()
    broadcaster = EventBroadcaster()
    active.router.subscribe("websocket-broadcast", broadcaster.on_event)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        del app
        await active.start()
        # Deliberately not the structured logger: that one redacts, and this
        # line exists to be read. It is printed once, to the runtime's own
        # console, on a process that listens on loopback only.
        logging.getLogger("cit_runtime").warning(
            "Instructor passcode for this run: %s", active.authority.instructor_passcode
        )
        pump = asyncio.create_task(broadcaster.pump())
        watchdog = asyncio.create_task(_watchdog_loop(active))
        try:
            yield
        finally:
            for task in (pump, watchdog):
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        title="CIT Physical XR local runtime",
        version="1.0.0",
        summary="Local-first runtime. Not for public exposure.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEFAULT_ALLOWED_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["authorization", "content-type"],
    )
    app.state.runtime = active

    # ------------------------------------------------------------------- auth

    def _token_from(request: Request) -> str | None:
        header = request.headers.get("authorization")
        if header and header.lower().startswith("bearer "):
            return header[7:].strip()
        return request.headers.get("x-cit-token")

    def _principal(request: Request) -> Principal:
        return active.authority.principal(_token_from(request), now=active.clock.now())

    def _instructor(request: Request, action: Action) -> Principal:
        principal = _principal(request)
        try:
            authorize(principal, action)
        except AuthorizationError:
            active.audit.record(
                AuditAction.AUTHORIZATION_DENIED,
                actor_id=principal.actor_id,
                at=active.clock.now(),
                context={"action": action.value, "role": principal.role.value},
            )
            raise
        return principal

    @app.exception_handler(AuthenticationError)
    async def _unauthenticated(request: Request, error: Exception) -> JSONResponse:
        del request
        return JSONResponse(status_code=401, content={"detail": str(error)})

    @app.exception_handler(AuthorizationError)
    async def _unauthorized(request: Request, error: Exception) -> JSONResponse:
        del request
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.post("/api/auth/join")
    async def join(request: JoinRequest) -> Mapping[str, Any]:
        """Issue a scoped token. The instructor role costs the runtime passcode."""

        now = active.clock.now()
        token, principal = active.authority.join(
            actor_id=request.actor_id,
            role=request.role,
            now=now,
            passcode=request.passcode,
            display_name=request.display_name,
        )
        active.audit.record(
            AuditAction.PRINCIPAL_JOINED,
            actor_id=principal.actor_id,
            at=now,
            context={"role": principal.role.value},
        )
        return {
            "token": token,
            "actorId": principal.actor_id,
            "role": principal.role.value,
            "displayName": principal.display_name,
            "expiresAt": principal.expires_at.isoformat(),
        }

    @app.get("/api/auth/me")
    async def whoami(request: Request) -> Mapping[str, Any]:
        principal = _principal(request)
        return {
            "actorId": principal.actor_id,
            "role": principal.role.value,
            "displayName": principal.display_name,
            "expiresAt": principal.expires_at.isoformat(),
        }

    @app.post("/api/auth/leave")
    async def leave(request: Request) -> Mapping[str, Any]:
        token = _token_from(request)
        return {"released": bool(token) and active.authority.revoke(token or "")}

    # ---------------------------------------------------------------- runtime

    @app.get("/api/health")
    async def health() -> Mapping[str, Any]:
        """Open on purpose: the Studio has to find the runtime before joining."""

        info = active.info()
        return {
            "status": "ok",
            "runtimeId": info.runtime_id,
            "protocolVersion": info.protocol_version,
            "executionMode": info.execution_mode,
            "physicalEnabled": info.physical_enabled,
        }

    @app.get("/api/devices")
    async def list_devices(request: Request) -> Mapping[str, Any]:
        principal = _principal(request)
        visible = _visible_device_ids(active, principal)
        return {
            "devices": [
                _describe_device(active, device.device_id)
                for device in active.registry.list()
                if visible is None or device.device_id in visible
            ]
        }

    @app.get("/api/devices/overview")
    async def device_overview(request: Request) -> Mapping[str, Any]:
        """FR-065. The instructor console's view of the whole room."""

        _instructor(request, Action.READ_CLASSROOM)
        return {"devices": list(active.device_overview())}

    @app.post("/api/devices/discover")
    async def discover(request: Request) -> Mapping[str, Any]:
        _instructor(request, Action.DISCOVER_DEVICES)
        found = await active.discover()
        connected = await active.connect_all()
        return {"discovered": list(found), "connected": list(connected)}

    @app.post("/api/devices/disconnect")
    async def disconnect_device(request: Request, body: DeviceRequest) -> Mapping[str, Any]:
        principal = _instructor(request, Action.DISCONNECT_DEVICE)
        try:
            await active.disconnect_device(
                body.device_id, reason=body.reason, actor_id=principal.actor_id
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return _describe_device(active, body.device_id)

    # --------------------------------------------------------------- sessions

    @app.get("/api/sessions")
    async def list_sessions(request: Request) -> Mapping[str, Any]:
        principal = _principal(request)
        return {
            "sessions": [
                _describe_session(active, session.session_id)
                for session in active.sessions.list()
                if principal.is_instructor or session.user_id == principal.actor_id
            ]
        }

    @app.post("/api/sessions")
    async def create_session(request: Request, body: CreateSessionRequest) -> Mapping[str, Any]:
        principal = _principal(request)
        if body.execution_mode is ExecutionMode.PHYSICAL:
            # FR-062 and FR-068: moving a real robot is an instructor's decision.
            _instructor(request, Action.CREATE_PHYSICAL_SESSION)
        try:
            session = active.create_session(
                project_id=body.project_id,
                # The owner is who is signed in, never who the body names.
                user_id=principal.actor_id,
                authoring_mode=body.authoring_mode,
                execution_mode=body.execution_mode,
                instructor_id=body.instructor_id,
                safety_policy_id=body.safety_policy_id,
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        return _describe_session(active, session.session_id)

    @app.post("/api/sessions/{session_id}/devices")
    async def bind_devices(
        request: Request, session_id: str, body: BindDevicesRequest
    ) -> Mapping[str, Any]:
        principal = _principal(request)
        try:
            require_session_owner(
                principal, session_user_id=active.sessions.get(session_id).user_id
            )
            active.bind_devices(session_id, body.device_ids)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except DeviceAssignmentError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _describe_session(active, session_id)

    @app.post("/api/sessions/{session_id}/state")
    async def transition(
        request: Request, session_id: str, body: TransitionRequest
    ) -> Mapping[str, Any]:
        principal = _principal(request)
        try:
            require_session_owner(
                principal, session_user_id=active.sessions.get(session_id).user_id
            )
            active.transition(session_id, body.state, reason=body.reason)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except SessionTransitionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _describe_session(active, session_id)

    @app.post("/api/sessions/{session_id}/validate")
    async def validate(request: Request, session_id: str) -> Mapping[str, Any]:
        principal = _principal(request)
        try:
            require_session_owner(
                principal, session_user_id=active.sessions.get(session_id).user_id
            )
            active.advance_to_ready(session_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except SessionTransitionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _describe_session(active, session_id)

    @app.post("/api/sessions/{session_id}/failure-policy")
    async def set_failure_policy(
        request: Request, session_id: str, body: FailurePolicyRequest
    ) -> Mapping[str, Any]:
        """FR-058. What the rest of a coordinated group does when one fails."""

        _instructor(request, Action.SET_FAILURE_POLICY)
        try:
            active.set_failure_policy(session_id, body.policy)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return _describe_session(active, session_id)

    # ----------------------------------------------------------------- safety

    @app.post("/api/safety/arm")
    async def arm(request: Request, body: ArmRequest) -> Mapping[str, Any]:
        principal = _instructor(request, Action.ARM_DEVICE)
        ttl = timedelta(seconds=body.ttl_seconds) if body.ttl_seconds else None
        try:
            state = active.arm(
                session_id=body.session_id,
                device_id=body.device_id,
                instructor_id=principal.actor_id,
                ttl=ttl,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {
            "deviceId": state.device_id,
            "sessionId": state.session_id,
            "armedBy": state.armed_by,
            "expiresAt": state.expires_at.isoformat(),
        }

    @app.post("/api/safety/disarm")
    async def disarm(request: Request, body: StopRequest) -> Mapping[str, Any]:
        principal = _instructor(request, Action.DISARM_DEVICE)
        if body.device_id is None:
            return {"disarmed": list(active.supervisor.disarm_all())}
        active.disarm(body.device_id, actor_id=principal.actor_id)
        return {"disarmed": [body.device_id]}

    @app.post("/api/safety/heartbeat")
    async def heartbeat(request: Request, body: HeartbeatRequest) -> Mapping[str, Any]:
        """ADR-028. Holding a dead-man control is this route, repeatedly.

        Any signed-in principal may send one, because holding the control is
        what a student does; what they cannot do is claim it without sending.
        """

        _principal(request)
        active.heartbeat(device_id=body.device_id, kind=body.kind)
        return {"deviceId": body.device_id, "kind": body.kind.value}

    @app.post("/api/safety/stop")
    async def stop(request: Request, body: StopRequest) -> Mapping[str, Any]:
        """A student may stop their own device; only an instructor stops the room."""

        if body.device_id is None:
            principal = _instructor(request, Action.STOP_ALL)
            stopped = await active.stop_all(reason=body.reason, actor_id=principal.actor_id)
            return {"stopped": list(stopped), "scope": "all"}
        principal = _principal(request)
        try:
            device = active.registry.get(body.device_id)
            if device.assigned_session_id is not None:
                require_session_owner(
                    principal,
                    session_user_id=active.sessions.get(device.assigned_session_id).user_id,
                )
            cleared = await active.pipeline.stop_device(
                body.device_id, reason=body.reason, actor_id=principal.actor_id
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"stopped": [body.device_id], "scope": "device", "clearedCommands": cleared}

    @app.post("/api/safety/revoke-lease")
    async def revoke_lease(request: Request, body: DeviceRequest) -> Mapping[str, Any]:
        """FR-067. Stop the device, then take it back for the next session."""

        principal = _instructor(request, Action.REVOKE_LEASE)
        try:
            revoked = await active.revoke_lease(body.device_id, actor_id=principal.actor_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"deviceId": body.device_id, "revoked": revoked}

    @app.post("/api/safety/clear-queue")
    async def clear_queue(request: Request, body: ClearQueueRequest) -> Mapping[str, Any]:
        principal = _instructor(request, Action.CLEAR_QUEUE)
        cleared = active.clear_queue(device_id=body.device_id, actor_id=principal.actor_id)
        return {"deviceId": body.device_id, "clearedCommands": cleared}

    @app.post("/api/safety/inputs")
    async def set_input(request: Request, body: InputSourceRequest) -> Mapping[str, Any]:
        """FR-067. Disable Leap input, or disconnect Quest control, by name."""

        principal = _instructor(request, Action.SET_INPUT_ENABLED)
        active.set_input_enabled(body.source, enabled=body.enabled, actor_id=principal.actor_id)
        return {"disabledSources": sorted(active.supervisor.disabled_sources())}

    @app.get("/api/safety/inputs")
    async def read_inputs(request: Request) -> Mapping[str, Any]:
        _principal(request)
        return {"disabledSources": sorted(active.supervisor.disabled_sources())}

    # --------------------------------------------------------------- commands

    @app.post("/api/commands")
    async def submit_command(request: Request, body: SimpleCommandRequest) -> Mapping[str, Any]:
        principal = _principal(request)
        try:
            session = active.sessions.get(body.session_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        require_session_owner(principal, session_user_id=session.user_id)
        source = resolve_source(principal, body.source)
        if source == "instructor":
            authorize(principal, Action.ISSUE_INSTRUCTOR_COMMAND)

        now = active.clock.now()
        intent = DeviceCommandIntent.model_validate(
            {
                "commandId": str(uuid4()),
                "sessionId": body.session_id,
                "deviceId": body.device_id,
                "capability": body.capability,
                "action": body.action,
                "arguments": body.arguments,
                "source": source,
                "issuedAt": now,
                "expiresAt": now + timedelta(seconds=body.ttl_seconds),
                "idempotencyKey": str(uuid4()),
                "safetyContext": {
                    "policyId": session.safety_policy_id,
                    "armed": active.supervisor.is_armed(body.device_id),
                    # Observed, not claimed (ADR-028). The supervisor checks its
                    # own attestation regardless of what is recorded here.
                    "deadmanActive": active.supervisor.deadman_attested(body.device_id),
                    "inputConfidence": body.input_confidence,
                },
            }
        )
        dispatch = await active.submit(intent)
        if dispatch.error is not None:
            return {
                "accepted": False,
                "code": dispatch.error.code,
                "message": dispatch.error.message,
                "recovery": dispatch.error.recoverySuggestion,
            }
        result = dispatch.result
        response: dict[str, Any] = {
            "accepted": dispatch.accepted,
            "status": result.status if result else "unknown",
            "commandId": str(intent.commandId),
            "clampedFields": list(dispatch.clamped_fields),
        }
        if result is not None and not dispatch.accepted:
            # A device-level refusal carries its own reason. Dropping it here
            # leaves the console saying "rejected" and nothing else.
            details = dict(result.details.model_dump()) if result.details is not None else {}
            response["code"] = str(details.get("code", "DEVICE_CAPABILITY_UNSUPPORTED"))
            if result.message:
                response["message"] = result.message
        return response

    @app.post("/api/student/rpc")
    async def student_rpc(request: Request, body: StudentRpcRequest) -> Mapping[str, Any]:
        """The only route a student program can cause (FR-013).

        The method is checked against the bridge's allowlist, the session is
        checked here, and everything past this point is the ordinary pipeline
        with the safety supervisor still in front of it.
        """

        principal = _principal(request)
        try:
            session = active.sessions.get(body.session_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        require_session_owner(principal, session_user_id=session.user_id)

        bridge = StudentBridge(
            active,
            session_id=body.session_id,
            source=(
                "student_python"
                if session.authoring_mode is AuthoringMode.PYTHON
                else "student_blocks"
            ),
            aliases=body.aliases,
        )
        bridge.input_confidence = body.input_confidence
        try:
            return await bridge.call(body.method, body.payload)
        except StudentBridgeError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    # ---------------------------------------------------------------- history

    @app.get("/api/audit")
    async def audit(request: Request) -> Mapping[str, Any]:
        principal = _principal(request)
        entries = active.audit.entries()
        if not principal.is_instructor:
            owned = {
                session.session_id
                for session in active.sessions.list()
                if session.user_id == principal.actor_id
            }
            entries = tuple(
                entry
                for entry in entries
                if entry.actor_id == principal.actor_id or entry.context.get("sessionId") in owned
            )
        return {
            "entries": [
                {
                    "sequence": entry.sequence,
                    "recordedAt": entry.recorded_at.isoformat(),
                    "action": entry.action.value,
                    "actorId": entry.actor_id,
                    "context": dict(entry.context),
                }
                for entry in entries
            ]
        }

    @app.get("/api/audit/export", response_class=PlainTextResponse)
    async def export_audit(request: Request) -> str:
        """FR-084. The whole redacted log as JSON lines, for one instructor."""

        _instructor(request, Action.EXPORT_AUDIT)
        return audit_entries_to_jsonl(active.audit.entries())

    @app.get("/api/events")
    async def recent_events(request: Request, device_id: str | None = None) -> Mapping[str, Any]:
        principal = _principal(request)
        visible = _visible_device_ids(active, principal)
        return {
            "events": [
                json.loads(event.model_dump_json(exclude_none=True))
                for event in active.router.history(device_id=device_id)
                if visible is None or event.deviceId in visible
            ]
        }

    # ------------------------------------------------------------- recordings

    @app.get("/api/recordings")
    async def list_recordings(request: Request) -> Mapping[str, Any]:
        _principal(request)
        return {
            "recordings": [
                {
                    "recordingId": item.recording_id,
                    "sessionId": item.session_id,
                    "startedAt": item.started_at.isoformat(),
                    "eventCount": item.event_count,
                    "durationSeconds": item.duration_seconds,
                }
                for item in active.recording_store.list()
            ],
            "policy": {
                "maxRecordings": active.recording_store.policy.max_recordings,
                "retentionDays": active.recording_store.policy.retention_days,
            },
        }

    @app.post("/api/recordings/start")
    async def start_recording(request: Request, body: RecordingRequest) -> Mapping[str, Any]:
        principal = _principal(request)
        try:
            require_session_owner(
                principal, session_user_id=active.sessions.get(body.session_id).user_id
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        recording_id = active.start_recording(body.session_id, actor_id=principal.actor_id)
        return {"recordingId": recording_id, "sessionId": body.session_id}

    @app.post("/api/recordings/{recording_id}/stop")
    async def stop_recording(request: Request, recording_id: str) -> Mapping[str, Any]:
        principal = _principal(request)
        try:
            recording = active.stop_recording(recording_id, actor_id=principal.actor_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {
            "recordingId": recording.recording_id,
            "sessionId": recording.session_id,
            "eventCount": len(recording.events),
            "durationSeconds": recording.duration_seconds,
        }

    @app.post("/api/recordings/{recording_id}/replay")
    async def replay(request: Request, recording_id: str) -> Mapping[str, Any]:
        """FR-064. Publishes historical events. Reaches no adapter, by design."""

        principal = _principal(request)
        try:
            delivered = active.replay(recording_id, actor_id=principal.actor_id)
        except (KeyError, FileNotFoundError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"recordingId": recording_id, "delivered": delivered, "physicalOutput": False}

    @app.get("/api/recordings/{recording_id}/export", response_class=PlainTextResponse)
    async def export_recording(request: Request, recording_id: str) -> str:
        """FR-084. The recording plus its redacted audit slice, as one document."""

        principal = _principal(request)
        try:
            recording = active.recording(recording_id)
        except (KeyError, FileNotFoundError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        active.audit.record(
            AuditAction.RECORDING_EXPORTED,
            actor_id=principal.actor_id,
            at=active.clock.now(),
            context={"recordingId": recording_id},
        )
        return replay_package(
            recording,
            audit_entries=active.audit.entries(),
            exported_at=active.clock.now(),
        )

    @app.delete("/api/recordings/{recording_id}")
    async def delete_recording(request: Request, recording_id: str) -> Mapping[str, Any]:
        """NFR 12.6. Deletion is a thing a person can actually do."""

        principal = _principal(request)
        deleted = active.recording_store.delete(recording_id)
        active.audit.record(
            AuditAction.RECORDING_DELETED,
            actor_id=principal.actor_id,
            at=active.clock.now(),
            context={"recordingId": recording_id, "result": str(deleted)},
        )
        return {"recordingId": recording_id, "deleted": deleted}

    @app.get("/api/retention")
    async def read_retention(request: Request) -> Mapping[str, Any]:
        _principal(request)
        policy = active.recording_store.policy
        return {
            "maxRecordings": policy.max_recordings,
            "retentionDays": policy.retention_days,
        }

    @app.post("/api/retention")
    async def set_retention(request: Request, body: RetentionRequest) -> Mapping[str, Any]:
        _instructor(request, Action.MANAGE_RETENTION)
        active.recording_store.set_policy(
            RetentionPolicy(
                max_recordings=body.max_recordings,
                retention_days=body.retention_days,
            )
        )
        pruned = active.recording_store.prune(now=active.clock.now())
        return {
            "maxRecordings": body.max_recordings,
            "retentionDays": body.retention_days,
            "pruned": list(pruned),
        }

    # --------------------------------------------------------------- projects

    @app.get("/api/projects")
    async def list_projects(request: Request) -> Mapping[str, Any]:
        principal = _principal(request)
        owner = None if principal.is_instructor else principal.actor_id
        return {
            "projects": [
                {
                    "projectId": item.project_id,
                    "name": item.name,
                    "authoringMode": item.authoring_mode,
                    "updatedAt": item.updated_at,
                    "ownerId": item.owner_id,
                }
                for item in active.projects.list(owner_id=owner)
            ]
        }

    @app.get("/api/projects/{project_id}")
    async def read_project(request: Request, project_id: str) -> Mapping[str, Any]:
        principal = _principal(request)
        try:
            document = active.projects.get(project_id)
        except ProjectStoreError as error:
            raise HTTPException(status_code=404, detail=f"{error} {error.recovery}") from error
        owner = active.projects.owner_of(project_id)
        if owner is not None:
            require_session_owner(principal, session_user_id=owner)
        return document

    @app.put("/api/projects/{project_id}")
    async def save_project(
        request: Request, project_id: str, body: ProjectRequest
    ) -> Mapping[str, Any]:
        """FR-001 autosave. The Studio calls this as the student works."""

        principal = _principal(request)
        if str(body.project.get("projectId")) != project_id:
            raise HTTPException(
                status_code=400,
                detail="The project id in the body must match the one in the path.",
            )
        owner = active.projects.owner_of(project_id)
        if owner is not None:
            require_session_owner(principal, session_user_id=owner)
        try:
            stored = active.projects.save(
                body.project, owner_id=principal.actor_id, at=active.clock.now()
            )
        except ProjectStoreError as error:
            raise HTTPException(status_code=422, detail=f"{error} {error.recovery}") from error
        except OSError as error:
            raise HTTPException(status_code=507, detail=str(error)) from error
        active.audit.record(
            AuditAction.PROJECT_SAVED,
            actor_id=principal.actor_id,
            at=active.clock.now(),
            context={"projectId": project_id},
        )
        return stored

    @app.delete("/api/projects/{project_id}")
    async def delete_project(request: Request, project_id: str) -> Mapping[str, Any]:
        principal = _principal(request)
        owner = active.projects.owner_of(project_id)
        if owner is not None:
            require_session_owner(principal, session_user_id=owner)
        try:
            deleted = active.projects.delete(project_id)
        except ProjectStoreError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        active.audit.record(
            AuditAction.PROJECT_DELETED,
            actor_id=principal.actor_id,
            at=active.clock.now(),
            context={"projectId": project_id},
        )
        return {"projectId": project_id, "deleted": deleted}

    # -------------------------------------------------------------- classroom

    @app.get("/api/classroom")
    async def classroom(request: Request) -> Mapping[str, Any]:
        """FR-065 and FR-068. Who is in the room, on what, holding what."""

        _instructor(request, Action.READ_CLASSROOM)
        return {
            "people": [
                {
                    "actorId": person.actor_id,
                    "role": person.role.value,
                    "displayName": person.display_name,
                    "expiresAt": person.expires_at.isoformat(),
                }
                for person in active.authority.principals()
            ],
            "sessions": [
                _describe_session(active, session.session_id) for session in active.sessions.list()
            ],
            "devices": list(active.device_overview()),
            "disabledSources": sorted(active.supervisor.disabled_sources()),
            "queueDepth": len(active.pipeline.queue),
        }

    # ------------------------------------------------------------------ stream

    @app.websocket("/ws/events")
    async def events_socket(websocket: WebSocket, token: str | None = None) -> None:
        """The token rides in the query string: a browser cannot set a WebSocket
        header. It never leaves this machine, and the runtime refuses every
        remote origin anyway."""

        try:
            principal = active.authority.principal(token, now=active.clock.now())
        except AuthenticationError:
            await websocket.close(code=4401, reason="join the classroom first")
            return

        await websocket.accept()

        def wants(event: DeviceEvent) -> bool:
            visible = _visible_device_ids(active, principal)
            return visible is None or event.deviceId in visible

        broadcaster.register(websocket, wants)
        try:
            while True:
                # The Studio does not send commands over this socket; reading
                # keeps the connection alive and surfaces a clean disconnect.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            broadcaster.unregister(websocket)

    _mount_studio(app)
    return app


def studio_dist() -> Path:
    """Where `pnpm --filter @citxr/studio-web build` leaves its bundle."""

    return Path(__file__).resolve().parents[4] / "apps" / "studio-web" / "dist"


class PathPrefix:
    """Serve the whole runtime under a path, for a proxy that cannot rewrite one.

    A Cloudflare Tunnel routes a hostname and path to a local service and
    forwards the path as it arrived: a rule for ``/citxr`` delivers
    ``/citxr/api/health``, not ``/api/health``. Rather than teaching every route
    about a prefix, this strips it once, at the edge of the ASGI app.

    Anything outside the prefix is refused rather than served. If the proxy is
    ever pointed at this process for a path it was not given, that has to be a
    404 and not an unintended way in.
    """

    def __init__(self, app: Any, prefix: str) -> None:
        normalized = "/" + prefix.strip("/")
        if normalized == "/":
            raise ValueError("A path prefix of '/' is the same as no prefix")
        self._app = app
        self._prefix = normalized

    @property
    def prefix(self) -> str:
        return self._prefix

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self._app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if path == self._prefix or path.startswith(f"{self._prefix}/"):
            scope = dict(scope)
            scope["path"] = path[len(self._prefix) :] or "/"
            scope["root_path"] = self._prefix
            await self._app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(
                    {"detail": f"This runtime is served under {self._prefix}"}
                ).encode(),
            }
        )


def _mount_studio(app: FastAPI) -> None:
    """Serve the built Studio from the runtime itself, when it exists.

    Same origin is the point. The CORS allowlist above deliberately excludes
    every remote host, so a Studio served from anywhere else cannot drive this
    runtime. Mounting the bundle here means the working console is
    http://127.0.0.1:<port>/ with no cross-origin hole to open.

    A missing bundle is normal (nobody has run the build yet) and must not stop
    the API from serving.
    """

    dist = studio_dist()
    if not (dist / "index.html").is_file():
        return
    app.mount("/", StaticFiles(directory=dist, html=True), name="studio")


async def _watchdog_loop(runtime: Runtime, *, interval_seconds: float = 0.1) -> None:
    """FR-069. Keeps firing even when every client has gone away."""

    while True:
        await asyncio.sleep(interval_seconds)
        with suppress(Exception):
            await runtime.tick()


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8791,
    allow_non_loopback: bool = False,
    config_path: str | None = None,
    url_prefix: str | None = None,
) -> None:
    """Run the runtime. Refuses a non-loopback bind unless forced."""

    import uvicorn

    if host not in LOOPBACK_HOSTS and not allow_non_loopback:
        raise PermissionError(
            f"Refusing to bind {host!r}: the runtime controls physical devices and must not "
            "listen on a routable interface. Pass allow_non_loopback=True only on an isolated "
            "network you control."
        )
    runtime: Runtime | None = None
    if config_path is not None:
        from .physical_devices import runtime_from_config

        runtime = runtime_from_config(config_path)

    # A passcode that survives a restart, for a runtime supervised by something
    # that restarts it. Without this the instructor role changes identity every
    # time the service flaps, and the only record of it is a log line.
    passcode = os.environ.get("CITXR_INSTRUCTOR_PASSCODE")
    if passcode:
        if runtime is None:
            runtime = Runtime(instructor_passcode=passcode)
        else:
            runtime.authority = Authority(instructor_passcode=passcode)

    app: Any = create_app(runtime)
    if url_prefix is not None:
        app = PathPrefix(app, url_prefix)
    uvicorn.run(app, host=host, port=port, log_level="info")
