"""Standalone, local-first service boundary for the CIT Interaction Fabric.

This process layers the glasses/coding-agent vertical slice onto the current
classroom runtime without replacing it.  It has a separate database, explicit
credentials, and no physical-device dispatcher.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from cit_protocol import FabricCommandLifecycleStage, FabricResolvedCommand, IntegrationNode
from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .fabric import FabricDispatchOutcome, InteractionFabric
from .fabric_adapters import FabricAdapterConnections
from .fabric_api import install_fabric_api
from .fabric_auth import FABRIC_PERMISSIONS, FabricAuthService, FabricBootstrapIdentity
from .fabric_course import glasses_agent_course_pack
from .fabric_repository import SQLiteFabricRepository


def create_fabric_app(
    *,
    clock: Callable[[], datetime] | None = None,
    database_path: str | Path = ":memory:",
    fabric_bootstrap_identities: Iterable[FabricBootstrapIdentity] = (),
    fabric_allowed_origins: Iterable[str] = (
        "http://127.0.0.1:8766",
        "http://localhost:8766",
        "http://testserver",
    ),
    allowed_hosts: Iterable[str] = ("127.0.0.1", "localhost", "testserver"),
    allow_physical_fabric: bool = False,
    studio_directory: str | Path | None = None,
    maintenance_interval: float | None = 5.0,
) -> FastAPI:
    """Create one independently authenticated Interaction Fabric process."""

    if maintenance_interval is not None and maintenance_interval <= 0:
        raise ValueError("maintenance_interval must be positive or None")
    configured_hosts = tuple(allowed_hosts)
    if not configured_hosts:
        raise ValueError("allowed_hosts cannot be empty")
    configured_origins = frozenset(fabric_allowed_origins)
    configured_bootstrap_identities = tuple(fabric_bootstrap_identities)
    configured_studio = Path(studio_directory).resolve() if studio_directory else None
    wall_clock = clock or (lambda: datetime.now(UTC))

    repository: SQLiteFabricRepository | None = None
    fabric: InteractionFabric | None = None
    auth: FabricAuthService | None = None
    connections: FabricAdapterConnections | None = None

    def active_repository() -> SQLiteFabricRepository:
        if repository is None:
            raise RuntimeError("Fabric repository is unavailable outside application lifespan")
        return repository

    def active_fabric() -> InteractionFabric:
        if fabric is None:
            raise RuntimeError("Interaction Fabric is unavailable outside application lifespan")
        return fabric

    def active_auth() -> FabricAuthService:
        if auth is None:
            raise RuntimeError("Fabric authentication is unavailable outside application lifespan")
        return auth

    def active_connections() -> FabricAdapterConnections:
        if connections is None:
            raise RuntimeError(
                "Fabric adapter transport is unavailable outside application lifespan"
            )
        return connections

    async def dispatch(
        command: FabricResolvedCommand,
        node: IntegrationNode,
    ) -> FabricDispatchOutcome:
        """Dispatch only to authenticated adapters connected to this service."""

        active = connections
        if active is None:
            return FabricDispatchOutcome(
                accepted=False,
                terminal_stage=FabricCommandLifecycleStage.FAILED,
                code="ADAPTER_TRANSPORT_UNAVAILABLE",
                message="Adapter transport is not running",
            )
        return await active.dispatch(command, node)

    async def stop_all() -> dict[str, object]:
        active = active_fabric()
        stopped_sessions: list[str] = []
        failed_sessions: list[str] = []
        for session in active.list_sessions():
            if session.state.value in {"stopped", "emergency_stopped", "failed"}:
                continue
            try:
                active.transition_session(
                    session.sessionId,
                    "emergency_stop",
                    actor_id="system.emergency_stop",
                )
            except Exception:
                failed_sessions.append(session.sessionId)
            else:
                stopped_sessions.append(session.sessionId)
        external = await active_connections().stop_nodes(reason="instructor_emergency_stop")
        failed_nodes = list(external["failed"])
        return {
            "status": "partial" if failed_sessions or failed_nodes else "completed",
            "stoppedSessionIds": stopped_sessions,
            "failedSessionIds": failed_sessions,
            "stoppedNodeIds": list(external["stopped"]),
            "failedNodeIds": failed_nodes,
            "legacy": {"status": "not_configured"},
        }

    async def maintenance_loop(interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            active = fabric
            if active is not None:
                active.expire_nodes()
                active.expire_armed_sessions()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal auth, connections, fabric, repository
        repository = SQLiteFabricRepository(database_path)
        auth = FabricAuthService(repository)
        auth.install_bootstrap_identities(configured_bootstrap_identities, at=wall_clock())
        fabric = InteractionFabric(
            repository,
            clock=wall_clock,
            allow_physical=allow_physical_fabric,
        )
        fabric.install_course_pack(
            glasses_agent_course_pack(),
            actor_id="system.bootstrap",
        )
        connections = FabricAdapterConnections(
            fabric,
            auth,
            repository,
            clock=wall_clock,
            runtime_id="cit-interaction-fabric-local",
        )
        fabric.set_dispatcher(dispatch)
        maintenance_task = (
            asyncio.create_task(maintenance_loop(maintenance_interval))
            if maintenance_interval is not None
            else None
        )
        try:
            yield
        finally:
            if connections is not None:
                with suppress(Exception):
                    await connections.stop_nodes(reason="fabric_service_shutdown")
            if maintenance_task is not None:
                maintenance_task.cancel()
                with suppress(asyncio.CancelledError):
                    await maintenance_task
            if fabric is not None:
                fabric.set_dispatcher(None)
            connections = None
            auth = None
            fabric = None
            if repository is not None:
                repository.close()
            repository = None

    app = FastAPI(
        title="CIT Interaction Fabric",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(configured_hosts))

    @app.middleware("http")
    async def security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                body_size = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"code": "INVALID_CONTENT_LENGTH", "message": "Invalid request"},
                )
            if body_size > 1_048_576:
                return JSONResponse(
                    status_code=413,
                    content={"code": "REQUEST_TOO_LARGE", "message": "Request exceeds 1 MiB"},
                )
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; object-src 'none'; "
            "frame-ancestors 'none'; form-action 'self'; connect-src 'self'; "
            "img-src 'self' data:; style-src 'self'; script-src 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        if request.url.path.startswith("/api/v1/fabric"):
            response.headers["Cache-Control"] = "no-store"
        return response

    install_fabric_api(
        app,
        get_fabric=active_fabric,
        get_auth=active_auth,
        get_connections=active_connections,
        get_repository=active_repository,
        clock=wall_clock,
        allowed_origins=configured_origins,
        stop_all=stop_all,
    )

    @app.get("/api/v1/fabric/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok", "physicalActuation": "disabled"}

    if configured_studio is not None:
        index_path = configured_studio / "index.html"
        assets_path = configured_studio / "assets"
        if not index_path.is_file() or not assets_path.is_dir():
            raise ValueError("studio_directory must contain index.html and an assets directory")
        app.mount("/assets", StaticFiles(directory=assets_path), name="fabric-studio-assets")

        @app.get("/fabric", include_in_schema=False)
        async def fabric_console() -> FileResponse:
            return FileResponse(index_path, media_type="text/html")

    return app


def create_persistent_fabric_app() -> FastAPI:
    """Create the local persistent service used by the hardware launcher."""

    configured_directory = os.environ.get("CITXR_DATA_DIRECTORY")
    if configured_directory:
        data_directory = Path(configured_directory)
    elif local_app_data := os.environ.get("LOCALAPPDATA"):
        data_directory = Path(local_app_data) / "CITPhysicalXR"
    elif xdg_data_home := os.environ.get("XDG_DATA_HOME"):
        data_directory = Path(xdg_data_home) / "cit-physical-xr"
    else:
        data_directory = Path.home() / ".local" / "share" / "cit-physical-xr"
    if not data_directory.is_absolute():
        raise ValueError("CITXR_DATA_DIRECTORY must be an absolute path")
    data_directory.mkdir(parents=True, exist_ok=True)

    public_origin = os.environ.get("CITXR_PUBLIC_ORIGIN", "http://127.0.0.1:8766")
    parsed_origin = urlsplit(public_origin)
    if (
        parsed_origin.scheme not in {"http", "https"}
        or parsed_origin.hostname is None
        or parsed_origin.username is not None
        or parsed_origin.password is not None
        or parsed_origin.path not in {"", "/"}
        or parsed_origin.query
        or parsed_origin.fragment
    ):
        raise ValueError("CITXR_PUBLIC_ORIGIN must be an exact HTTP(S) origin")
    bootstrap_token = os.environ.get("CITXR_FABRIC_BOOTSTRAP_TOKEN")
    if bootstrap_token is None:
        raise ValueError("CITXR_FABRIC_BOOTSTRAP_TOKEN is required")
    bootstrap = FabricBootstrapIdentity(
        identity_id="local-administrator",
        token=bootstrap_token,
        actor_type="administrator",
        roles=("administrator",),
        permissions=tuple(sorted(FABRIC_PERMISSIONS)),
    )
    default_hosts = ",".join(
        dict.fromkeys((parsed_origin.hostname, "127.0.0.1", "localhost", "testserver"))
    )
    allowed_hosts = tuple(
        value.strip()
        for value in os.environ.get("CITXR_ALLOWED_HOSTS", default_hosts).split(",")
        if value.strip()
    )
    configured_studio = os.environ.get("CITXR_STUDIO_DIRECTORY")
    if configured_studio is not None:
        studio_directory: Path | None = Path(configured_studio)
    else:
        built_studio = Path(__file__).resolve().parents[4] / "apps" / "studio-web" / "dist"
        studio_directory = built_studio if built_studio.is_dir() else None
    return create_fabric_app(
        database_path=data_directory / "interaction-fabric.sqlite3",
        fabric_bootstrap_identities=(bootstrap,),
        fabric_allowed_origins=(public_origin.rstrip("/"),),
        allowed_hosts=allowed_hosts,
        studio_directory=studio_directory,
    )
