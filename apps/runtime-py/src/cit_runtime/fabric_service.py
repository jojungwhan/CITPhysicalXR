"""Standalone, local-first service boundary for the CIT Interaction Fabric.

This process layers capability-based interaction slices onto the current
classroom runtime without replacing it. It has a separate database, explicit
credentials, and an authenticated adapter dispatcher. Physical actuation is
still disabled unless the local operator explicitly enables it at startup.
"""

from __future__ import annotations

import asyncio
import mimetypes
import os
import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping
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
from .fabric_android import AndroidControllerService, configured_android_controller
from .fabric_android_api import install_fabric_android_api
from .fabric_api import install_fabric_api
from .fabric_auth import FABRIC_PERMISSIONS, FabricAuthService, FabricBootstrapIdentity
from .fabric_camera import (
    SonyCameraImportService,
    configured_dji_camera_import,
    configured_sony_camera_import,
    disabled_sony_camera_import,
)
from .fabric_camera_api import install_fabric_camera_api
from .fabric_camera_ftp import CAMERA_FTP_PORT, CameraFtpServer
from .fabric_course import load_builtin_course_packs
from .fabric_discovery import (
    FabricDiscoveryService,
    FabricRememberedConnection,
    PowerShellDiscoveryRunner,
    UnavailableDiscoveryRunner,
    remembered_connection_policy,
)
from .fabric_installation import FabricInstallationCatalog
from .fabric_lan_access import LanMacAccessMiddleware, LanMacAccessPolicy
from .fabric_lan_access_api import install_fabric_lan_access_api
from .fabric_media import (
    FabricMediaRegistry,
    VisionDetector,
    configured_vision_detector,
)
from .fabric_media_api import install_fabric_media_api
from .fabric_printer import (
    CrealityPrinterService,
    configured_creality_printer,
    disabled_creality_printer,
)
from .fabric_printer_api import install_fabric_printer_api
from .fabric_repository import SQLiteFabricRepository
from .fabric_unlock_automation import (
    UnlockAutomationService,
    UnlockPowerResult,
    toggle_configured_smart_plugs,
    turn_on_configured_smart_plugs,
)
from .fabric_unlock_automation_api import install_fabric_unlock_automation_api


async def supervise_remembered_reconnects(
    fabric: InteractionFabric,
    repository: SQLiteFabricRepository,
    discovery: FabricDiscoveryService,
    clock: Callable[[], datetime] | None = None,
) -> None:
    """Retry remembered adapters that opted into unattended reconnection.

    Runs without a principal, so it uses the unscoped system node view and
    never confirms grounded aircraft.
    """

    def nodes() -> tuple[IntegrationNode, ...]:
        return fabric.list_nodes()

    report = discovery.current(nodes())
    records = repository.list_fabric_remembered_connections(host_id=report.hostId)
    connections = tuple(
        FabricRememberedConnection(
            actionId=record.reconnect_action_id,
            requiresGroundedConfirmation=record.requires_grounded_confirmation,
            rememberedAt=record.remembered_at,
        )
        for record in records
        if remembered_connection_policy(record.reconnect_action_id) is not None
    )
    if not connections:
        return

    def record_transition(action_id: str, status: str) -> None:
        repository.record_fabric_audit(
            actor_id="system.reconnect-supervisor",
            action="fabric.discovery.reconnect_remembered",
            resource_type="host",
            resource_id=report.hostId,
            outcome="succeeded" if status != "failed" else "failed",
            correlation_id=None,
            occurred_at=(clock or (lambda: datetime.now(UTC)))(),
            details={"actionId": action_id, "status": status, "unattended": True},
        )

    await discovery.supervise_remembered_reconnects(
        connections,
        nodes=nodes,
        on_transition=record_transition,
    )


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
    discovery_service: FabricDiscoveryService | None = None,
    media_registry: FabricMediaRegistry | None = None,
    vision_detector: VisionDetector | None = None,
    media_ingress_origin: str | None = None,
    installation_directory: str | Path | None = None,
    printer_service: CrealityPrinterService | None = None,
    camera_import_service: SonyCameraImportService | None = None,
    camera_import_services: Mapping[str, SonyCameraImportService] | None = None,
    android_controller_service: AndroidControllerService | None = None,
    lan_access_policy: LanMacAccessPolicy | None = None,
    unlock_automation_service: UnlockAutomationService | None = None,
    camera_ftp_server: CameraFtpServer | None = None,
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
    configured_discovery = discovery_service or FabricDiscoveryService(
        UnavailableDiscoveryRunner(clock=wall_clock),
        clock=wall_clock,
        physical_actuation_enabled=allow_physical_fabric,
    )
    configured_media = media_registry or FabricMediaRegistry()
    configured_detector = vision_detector or configured_vision_detector()
    configured_installation = FabricInstallationCatalog.load(installation_directory)
    configured_printer = printer_service or disabled_creality_printer(
        (Path.cwd() / ".cit-printer-staging").resolve()
    )
    if camera_import_service is not None and camera_import_services is not None:
        raise ValueError("camera_import_service and camera_import_services are mutually exclusive")
    if camera_import_services is not None:
        configured_camera_imports = dict(camera_import_services)
    elif camera_import_service is not None:
        configured_camera_imports = {camera_import_service.camera_id: camera_import_service}
    else:
        fallback_camera = disabled_sony_camera_import(
            (Path.cwd() / ".cit-sony-camera-imports").resolve()
        )
        configured_camera_imports = {fallback_camera.camera_id: fallback_camera}
    if not configured_camera_imports:
        raise ValueError("camera_import_services cannot be empty")
    if any(
        camera_id != service.camera_id for camera_id, service in configured_camera_imports.items()
    ):
        raise ValueError("camera_import_services keys must match service camera_id")
    configured_camera_import = next(iter(configured_camera_imports.values()))
    configured_android_controller_service = android_controller_service
    configured_lan_access = lan_access_policy
    configured_unlock_automation = unlock_automation_service
    configured_camera_ftp = camera_ftp_server

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

    def active_discovery() -> FabricDiscoveryService:
        return configured_discovery

    def active_printer() -> CrealityPrinterService:
        return configured_printer

    def active_camera_import() -> SonyCameraImportService:
        return configured_camera_import

    def active_camera_imports() -> Mapping[str, SonyCameraImportService]:
        return configured_camera_imports

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

    async def run_unlock_automation(
        node_ids: tuple[str, ...],
        actor_id: str,
        event_id: str,
    ) -> UnlockPowerResult:
        return await turn_on_configured_smart_plugs(
            active_fabric(),
            node_ids,
            actor_id,
            event_id,
            clock=wall_clock,
        )

    async def run_phone_smart_plug_toggle(
        node_ids: tuple[str, ...],
        actor_id: str,
        event_id: str,
    ) -> UnlockPowerResult:
        return await toggle_configured_smart_plugs(
            active_fabric(),
            node_ids,
            actor_id,
            event_id,
            clock=wall_clock,
        )

    async def maintenance_loop(interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            active = fabric
            if active is not None:
                active.expire_nodes()
                active.expire_armed_sessions()
            active_repo = repository
            if active is not None and active_repo is not None:
                with suppress(Exception):
                    await supervise_remembered_reconnects(
                        active,
                        active_repo,
                        configured_discovery,
                        wall_clock,
                    )

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
        for course_pack in load_builtin_course_packs():
            fabric.install_course_pack(
                course_pack,
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
        if configured_camera_ftp is not None:
            await asyncio.to_thread(configured_camera_ftp.start)
        for camera_service in configured_camera_imports.values():
            await camera_service.start_automatic_imports()
        if configured_android_controller_service is not None:
            await configured_android_controller_service.start()
        maintenance_task = (
            asyncio.create_task(maintenance_loop(maintenance_interval))
            if maintenance_interval is not None
            else None
        )
        try:
            yield
        finally:
            if configured_camera_ftp is not None:
                with suppress(Exception):
                    await asyncio.to_thread(configured_camera_ftp.stop)
            if configured_android_controller_service is not None:
                with suppress(Exception):
                    await configured_android_controller_service.stop()
            for camera_service in configured_camera_imports.values():
                with suppress(Exception):
                    await camera_service.stop_automatic_imports()
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
    if configured_lan_access is not None:
        app.add_middleware(LanMacAccessMiddleware, policy=configured_lan_access)

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
            request_limit = (
                64 * 1024 * 1024
                if request.url.path == "/api/v1/fabric/printer/sources"
                else 1_048_576
            )
            if body_size > request_limit:
                return JSONResponse(
                    status_code=413,
                    content={
                        "code": "REQUEST_TOO_LARGE",
                        "message": (
                            "Printer model exceeds 64 MiB"
                            if request_limit > 1_048_576
                            else "Request exceeds 1 MiB"
                        ),
                    },
                )
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; object-src 'none'; "
            "frame-ancestors 'none'; form-action 'self'; connect-src 'self'; "
            "img-src 'self' data: blob:; style-src 'self'; script-src 'self'"
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
        get_discovery=active_discovery,
        clock=wall_clock,
        allowed_origins=configured_origins,
        stop_all=stop_all,
        installation_catalog=configured_installation,
    )
    install_fabric_media_api(
        app,
        registry=configured_media,
        detector=configured_detector,
        get_auth=active_auth,
        get_repository=active_repository,
        clock=wall_clock,
        media_ingress_origin=media_ingress_origin,
    )
    install_fabric_printer_api(
        app,
        get_printer=active_printer,
        get_auth=active_auth,
        get_repository=active_repository,
        clock=wall_clock,
    )
    install_fabric_camera_api(
        app,
        get_camera_import=active_camera_import,
        get_camera_imports=active_camera_imports,
        get_auth=active_auth,
        get_repository=active_repository,
        clock=wall_clock,
    )
    if configured_android_controller_service is not None:
        install_fabric_android_api(
            app,
            get_android_controller=lambda: configured_android_controller_service,
            get_auth=active_auth,
            get_repository=active_repository,
            clock=wall_clock,
        )
    if configured_lan_access is not None:
        install_fabric_lan_access_api(
            app,
            policy=configured_lan_access,
            get_auth=active_auth,
            get_repository=active_repository,
            clock=wall_clock,
            android_controller=configured_android_controller_service,
        )
    if configured_unlock_automation is not None:
        install_fabric_unlock_automation_api(
            app,
            service=configured_unlock_automation,
            get_fabric=active_fabric,
            get_auth=active_auth,
            get_repository=active_repository,
            clock=wall_clock,
            command_runner=run_unlock_automation,
            toggle_command_runner=run_phone_smart_plug_toggle,
            android_controller=configured_android_controller_service,
            lan_access=configured_lan_access,
        )

    @app.get("/api/v1/fabric/healthz")
    async def health() -> dict[str, str | bool | None]:
        result: dict[str, str | bool | None] = {
            "status": "ok",
            "physicalActuation": "enabled" if allow_physical_fabric else "disabled",
            "mediaIngress": "enabled" if media_ingress_origin is not None else "disabled",
            "mediaIngressOrigin": media_ingress_origin,
        }
        if configured_lan_access is not None:
            result["lanMacAccess"] = configured_lan_access.enabled
        return result

    if configured_studio is not None:
        # Python 3.11 on Windows does not include WebP in its built-in MIME map.
        mimetypes.add_type("image/webp", ".webp")

        index_path = configured_studio / "index.html"
        assets_path = configured_studio / "assets"
        if not index_path.is_file() or not assets_path.is_dir():
            raise ValueError("studio_directory must contain index.html and an assets directory")
        app.mount("/assets", StaticFiles(directory=assets_path), name="fabric-studio-assets")

        device_images_path = configured_studio / "device-images"
        if device_images_path.is_dir():
            app.mount(
                "/device-images",
                StaticFiles(directory=device_images_path),
                name="fabric-device-images",
            )

        icons_path = configured_studio / "icons"
        if icons_path.is_dir():
            app.mount(
                "/icons",
                StaticFiles(directory=icons_path),
                name="fabric-pwa-icons",
            )

        favicon_path = configured_studio / "favicon.svg"
        if favicon_path.is_file():

            @app.get("/favicon.svg", include_in_schema=False)
            async def fabric_favicon() -> FileResponse:
                return FileResponse(favicon_path, media_type="image/svg+xml")

        manifest_path = configured_studio / "fabric.webmanifest"
        if manifest_path.is_file():

            @app.get("/fabric.webmanifest", include_in_schema=False)
            async def fabric_manifest() -> FileResponse:
                return FileResponse(
                    manifest_path,
                    media_type="application/manifest+json",
                )

        service_worker_path = configured_studio / "fabric-sw.js"
        if service_worker_path.is_file():

            @app.get("/fabric-sw.js", include_in_schema=False)
            async def fabric_service_worker() -> FileResponse:
                return FileResponse(
                    service_worker_path,
                    media_type="text/javascript",
                    headers={
                        "Cache-Control": "no-cache",
                        "Service-Worker-Allowed": "/",
                    },
                )

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
    configured_installation_directory = os.environ.get("CITXR_INSTALLATION_DIRECTORY")
    installation_directory = (
        Path(configured_installation_directory)
        if configured_installation_directory
        else Path(__file__).resolve().parents[4] / "artifacts" / "windows-transfer"
    )
    if not installation_directory.is_absolute():
        raise ValueError("CITXR_INSTALLATION_DIRECTORY must be an absolute path")
    physical_setting = os.environ.get("CITXR_ALLOW_PHYSICAL_FABRIC", "false").casefold()
    if physical_setting not in {"true", "false"}:
        raise ValueError("CITXR_ALLOW_PHYSICAL_FABRIC must be 'true' or 'false'")
    configured_media_ingress = os.environ.get("CITXR_MEDIA_INGRESS_ORIGIN")
    if configured_media_ingress is not None:
        parsed_media_ingress = urlsplit(configured_media_ingress)
        if (
            parsed_media_ingress.scheme not in {"http", "https"}
            or parsed_media_ingress.hostname is None
            or parsed_media_ingress.username is not None
            or parsed_media_ingress.password is not None
            or parsed_media_ingress.path not in {"", "/"}
            or parsed_media_ingress.query
            or parsed_media_ingress.fragment
        ):
            raise ValueError("CITXR_MEDIA_INGRESS_ORIGIN must be an exact HTTP(S) origin")
        configured_media_ingress = configured_media_ingress.rstrip("/")
    lan_access_setting = os.environ.get(
        "CITXR_LAN_MAC_ACCESS",
        "true" if configured_media_ingress is not None else "false",
    ).casefold()
    if lan_access_setting not in {"true", "false"}:
        raise ValueError("CITXR_LAN_MAC_ACCESS must be 'true' or 'false'")
    repository_root = Path(__file__).resolve().parents[4]
    configured_discovery_root = os.environ.get("CITXR_DISCOVERY_STATE_ROOT")
    discovery_root = (
        Path(configured_discovery_root)
        if configured_discovery_root
        else (
            data_directory.parent
            if data_directory.name.casefold() == "runtime"
            else data_directory / "interaction-fabric"
        )
    )
    if not discovery_root.is_absolute():
        raise ValueError("CITXR_DISCOVERY_STATE_ROOT must be an absolute path")
    workspace_root = repository_root.parent
    discovery = FabricDiscoveryService(
        PowerShellDiscoveryRunner(
            script_path=repository_root / "tools" / "hardware" / "find-classroom-devices.ps1",
            state_root=discovery_root,
            brain2devices_root=Path(
                os.environ.get(
                    "CITXR_BRAIN2DEVICES_ROOT",
                    str(workspace_root / "brain2devices"),
                )
            ),
            robomaster_root=Path(
                os.environ.get(
                    "CITXR_ROBOMASTER_ROOT",
                    str(workspace_root / "robomaster-gesture-control-reference"),
                )
            ),
            agent_mesh_root=Path(
                os.environ.get(
                    "CITXR_AGENT_MESH_ROOT",
                    str(workspace_root / "glasses2CLI"),
                )
            ),
            fabric_port=parsed_origin.port or (443 if parsed_origin.scheme == "https" else 80),
        ),
        physical_actuation_enabled=physical_setting == "true",
    )
    printer = configured_creality_printer(
        data_directory,
        allow_physical=physical_setting == "true",
    )
    android_controller = configured_android_controller(
        parsed_origin.port or (443 if parsed_origin.scheme == "https" else 80)
    )
    lan_access = LanMacAccessPolicy(
        state_path=data_directory / "lan-access.json",
        enabled=lan_access_setting == "true",
        lan_origin=configured_media_ingress,
    )
    companion_apk_setting = os.environ.get("CITXR_UNLOCK_COMPANION_APK")
    companion_apk_path = (
        Path(companion_apk_setting)
        if companion_apk_setting
        else repository_root
        / "apps"
        / "control-tower-companion"
        / "app"
        / "build"
        / "outputs"
        / "apk"
        / "debug"
        / "app-debug.apk"
    )
    if not companion_apk_path.is_absolute():
        raise ValueError("CITXR_UNLOCK_COMPANION_APK must be an absolute path")
    unlock_automation = UnlockAutomationService(
        state_path=data_directory / "unlock-automation.json",
        lan_origin=configured_media_ingress,
        companion_apk_path=companion_apk_path,
    )
    camera_operation_lock = threading.Lock()
    camera_imports = {
        camera.camera_id: camera
        for camera in (
            configured_sony_camera_import(
                operation_lock=camera_operation_lock,
                after_import=android_controller.restore_controller_foreground,
            ),
            configured_dji_camera_import(
                operation_lock=camera_operation_lock,
                after_import=android_controller.restore_controller_foreground,
            ),
        )
    }
    camera_ftp: CameraFtpServer | None = None
    if configured_media_ingress is not None:
        ftp_port_setting = os.environ.get("CITXR_CAMERA_FTP_PORT", str(CAMERA_FTP_PORT))
        try:
            ftp_port = int(ftp_port_setting)
        except ValueError as error:
            raise ValueError("CITXR_CAMERA_FTP_PORT must be an integer") from error
        if not 1024 <= ftp_port <= 65_535:
            raise ValueError("CITXR_CAMERA_FTP_PORT must be between 1024 and 65535")
        media_host = urlsplit(configured_media_ingress).hostname
        assert media_host is not None
        camera_ftp = CameraFtpServer(
            camera_imports["sony-zve10-android"].destination,
            bind_host=media_host,
            port=ftp_port,
            credentials=unlock_automation.camera_ftp_credentials,
        )
    return create_fabric_app(
        database_path=data_directory / "interaction-fabric.sqlite3",
        fabric_bootstrap_identities=(bootstrap,),
        fabric_allowed_origins=(public_origin.rstrip("/"),),
        allowed_hosts=allowed_hosts,
        allow_physical_fabric=physical_setting == "true",
        studio_directory=studio_directory,
        discovery_service=discovery,
        media_ingress_origin=configured_media_ingress,
        installation_directory=installation_directory,
        printer_service=printer,
        camera_import_services=camera_imports,
        android_controller_service=android_controller,
        lan_access_policy=lan_access,
        unlock_automation_service=unlock_automation,
        camera_ftp_server=camera_ftp,
    )
