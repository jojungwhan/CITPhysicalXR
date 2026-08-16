"""The local runtime API.

The PRD forbids exposing robot control to the public internet, so the server
binds the loopback interface and refuses to start on any other host unless the
caller passes an explicit override that is recorded in the log. There is no
shell endpoint, no subprocess endpoint, and no eval: every route below maps to a
named runtime method with a typed body.

Events reach the Studio over a WebSocket on the same origin, which keeps the
whole system working with the network cable unplugged (FR-085).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from cit_protocol import DeviceCommandIntent, DeviceEvent
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .registry import DeviceAssignmentError
from .runtime import Runtime
from .sessions import AuthoringMode, ExecutionMode, SessionState, SessionTransitionError
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


class CreateSessionRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    authoring_mode: AuthoringMode = AuthoringMode.BLOCKS
    execution_mode: ExecutionMode = ExecutionMode.SIMULATION
    instructor_id: str | None = None
    safety_policy_id: str = "simulation-only"


class BindDevicesRequest(BaseModel):
    device_ids: list[str] = Field(min_length=1, max_length=32)


class ArmRequest(BaseModel):
    session_id: str
    device_id: str
    instructor_id: str = Field(min_length=1, max_length=128)
    ttl_seconds: float | None = Field(default=None, gt=0, le=3600)


class HeartbeatRequest(BaseModel):
    device_id: str
    kind: WatchdogKind


class StopRequest(BaseModel):
    actor_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="manual stop", min_length=1, max_length=200)
    device_id: str | None = None


class TransitionRequest(BaseModel):
    state: SessionState
    reason: str | None = Field(default=None, max_length=200)


class SimpleCommandRequest(BaseModel):
    """A Studio-shaped command. The runtime fills in every safety field."""

    session_id: str
    device_id: str
    capability: str
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    source: Literal[
        "student_blocks", "student_python", "quest", "leap", "instructor", "agent_mesh"
    ] = "student_blocks"
    deadman_active: bool = False
    input_confidence: float | None = Field(default=None, ge=0, le=1)
    ttl_seconds: float = Field(default=5.0, gt=0, le=60)


class EventBroadcaster:
    """Fans router events out to every connected WebSocket."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1024)

    def register(self, websocket: WebSocket) -> None:
        self._clients.add(websocket)

    def unregister(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    def on_event(self, event: DeviceEvent) -> None:
        """Called from the router. Never blocks; drops on backpressure."""

        payload = json.dumps(
            {"kind": "device_event", "event": json.loads(event.model_dump_json(exclude_none=True))}
        )
        with suppress(asyncio.QueueFull):
            self._queue.put_nowait(payload)

    async def pump(self) -> None:
        while True:
            payload = await self._queue.get()
            for client in list(self._clients):
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
        "deviceBindings": list(session.device_bindings),
        "startedAt": session.started_at.isoformat(),
        "lastActivityAt": session.last_activity_at.isoformat(),
        "endedAt": session.ended_at.isoformat() if session.ended_at else None,
    }


def create_app(runtime: Runtime | None = None) -> FastAPI:
    """Build the ASGI app. A caller may inject a runtime for testing."""

    active = runtime if runtime is not None else Runtime()
    broadcaster = EventBroadcaster()
    active.router.subscribe("websocket-broadcast", broadcaster.on_event)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        del app
        await active.start()
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
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )
    app.state.runtime = active

    @app.get("/api/health")
    async def health() -> Mapping[str, Any]:
        info = active.info()
        return {
            "status": "ok",
            "runtimeId": info.runtime_id,
            "protocolVersion": info.protocol_version,
            "executionMode": info.execution_mode,
            "physicalEnabled": info.physical_enabled,
        }

    @app.get("/api/devices")
    async def list_devices() -> Mapping[str, Any]:
        return {
            "devices": [
                _describe_device(active, device.device_id) for device in active.registry.list()
            ]
        }

    @app.post("/api/devices/discover")
    async def discover() -> Mapping[str, Any]:
        found = await active.discover()
        connected = await active.connect_all()
        return {"discovered": list(found), "connected": list(connected)}

    @app.get("/api/sessions")
    async def list_sessions() -> Mapping[str, Any]:
        return {
            "sessions": [
                _describe_session(active, session.session_id) for session in active.sessions.list()
            ]
        }

    @app.post("/api/sessions")
    async def create_session(request: CreateSessionRequest) -> Mapping[str, Any]:
        try:
            session = active.create_session(
                project_id=request.project_id,
                user_id=request.user_id,
                authoring_mode=request.authoring_mode,
                execution_mode=request.execution_mode,
                instructor_id=request.instructor_id,
                safety_policy_id=request.safety_policy_id,
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        return _describe_session(active, session.session_id)

    @app.post("/api/sessions/{session_id}/devices")
    async def bind_devices(session_id: str, request: BindDevicesRequest) -> Mapping[str, Any]:
        try:
            active.bind_devices(session_id, request.device_ids)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except DeviceAssignmentError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _describe_session(active, session_id)

    @app.post("/api/sessions/{session_id}/state")
    async def transition(session_id: str, request: TransitionRequest) -> Mapping[str, Any]:
        try:
            active.transition(session_id, request.state, reason=request.reason)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except SessionTransitionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _describe_session(active, session_id)

    @app.post("/api/sessions/{session_id}/validate")
    async def validate(session_id: str) -> Mapping[str, Any]:
        try:
            active.advance_to_ready(session_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except SessionTransitionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _describe_session(active, session_id)

    @app.post("/api/safety/arm")
    async def arm(request: ArmRequest) -> Mapping[str, Any]:
        ttl = timedelta(seconds=request.ttl_seconds) if request.ttl_seconds else None
        try:
            state = active.arm(
                session_id=request.session_id,
                device_id=request.device_id,
                instructor_id=request.instructor_id,
                ttl=ttl,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        return {
            "deviceId": state.device_id,
            "sessionId": state.session_id,
            "armedBy": state.armed_by,
            "expiresAt": state.expires_at.isoformat(),
        }

    @app.post("/api/safety/disarm")
    async def disarm(request: StopRequest) -> Mapping[str, Any]:
        if request.device_id is None:
            disarmed = active.supervisor.disarm_all()
            return {"disarmed": list(disarmed)}
        active.disarm(request.device_id, actor_id=request.actor_id)
        return {"disarmed": [request.device_id]}

    @app.post("/api/safety/heartbeat")
    async def heartbeat(request: HeartbeatRequest) -> Mapping[str, Any]:
        active.heartbeat(device_id=request.device_id, kind=request.kind)
        return {"deviceId": request.device_id, "kind": request.kind.value}

    @app.post("/api/safety/stop")
    async def stop(request: StopRequest) -> Mapping[str, Any]:
        if request.device_id is None:
            stopped = await active.stop_all(reason=request.reason, actor_id=request.actor_id)
            return {"stopped": list(stopped), "scope": "all"}
        try:
            cleared = await active.pipeline.stop_device(
                request.device_id, reason=request.reason, actor_id=request.actor_id
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"stopped": [request.device_id], "scope": "device", "clearedCommands": cleared}

    @app.post("/api/commands")
    async def submit_command(request: SimpleCommandRequest) -> Mapping[str, Any]:
        try:
            session = active.sessions.get(request.session_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        now = active.clock.now()
        intent = DeviceCommandIntent.model_validate(
            {
                "commandId": str(uuid4()),
                "sessionId": request.session_id,
                "deviceId": request.device_id,
                "capability": request.capability,
                "action": request.action,
                "arguments": request.arguments,
                "source": request.source,
                "issuedAt": now,
                "expiresAt": now + timedelta(seconds=request.ttl_seconds),
                "idempotencyKey": str(uuid4()),
                "safetyContext": {
                    "policyId": session.safety_policy_id,
                    "armed": active.supervisor.is_armed(request.device_id),
                    "deadmanActive": request.deadman_active,
                    "inputConfidence": request.input_confidence,
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
        return {
            "accepted": dispatch.accepted,
            "status": result.status if result else "unknown",
            "commandId": str(intent.commandId),
            "clampedFields": list(dispatch.clamped_fields),
        }

    @app.get("/api/audit")
    async def audit() -> Mapping[str, Any]:
        return {
            "entries": [
                {
                    "sequence": entry.sequence,
                    "recordedAt": entry.recorded_at.isoformat(),
                    "action": entry.action.value,
                    "actorId": entry.actor_id,
                    "context": dict(entry.context),
                }
                for entry in active.audit.entries()
            ]
        }

    @app.get("/api/events")
    async def recent_events(device_id: str | None = None) -> Mapping[str, Any]:
        return {
            "events": [
                json.loads(event.model_dump_json(exclude_none=True))
                for event in active.router.history(device_id=device_id)
            ]
        }

    @app.websocket("/ws/events")
    async def events_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        broadcaster.register(websocket)
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
) -> None:
    """Run the runtime. Refuses a non-loopback bind unless forced."""

    import uvicorn

    if host not in LOOPBACK_HOSTS and not allow_non_loopback:
        raise PermissionError(
            f"Refusing to bind {host!r}: the runtime controls physical devices and must not "
            "listen on a routable interface. Pass allow_non_loopback=True only on an isolated "
            "network you control."
        )
    uvicorn.run(create_app(), host=host, port=port, log_level="info")
