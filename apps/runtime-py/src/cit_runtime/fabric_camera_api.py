"""Authenticated routes for Android-backed automatic camera imports."""

from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse

from .fabric_auth import (
    FabricAuthenticationError,
    FabricAuthService,
    FabricPrincipal,
)
from .fabric_camera import (
    CameraDestinationActionResult,
    CameraImportActionResult,
    CameraImportSnapshot,
    SonyCameraImportService,
)
from .fabric_repository import SQLiteFabricRepository
from .sony_camera_import import SonyCameraImportError

CameraGetter = Callable[[], SonyCameraImportService]
CameraCollectionGetter = Callable[[], Mapping[str, SonyCameraImportService]]
AuthGetter = Callable[[], FabricAuthService]
RepositoryGetter = Callable[[], SQLiteFabricRepository]


def install_fabric_camera_api(
    app: FastAPI,
    *,
    get_camera_import: CameraGetter,
    get_camera_imports: CameraCollectionGetter | None = None,
    get_auth: AuthGetter,
    get_repository: RepositoryGetter,
    clock: Callable[[], datetime],
) -> None:
    def camera_imports() -> Mapping[str, SonyCameraImportService]:
        if get_camera_imports is not None:
            return get_camera_imports()
        camera = get_camera_import()
        return {camera.camera_id: camera}

    def camera_import(camera_id: str) -> SonyCameraImportService:
        camera = camera_imports().get(camera_id)
        if camera is None:
            raise SonyCameraImportError(
                "CAMERA_IMPORT_NOT_FOUND",
                "The requested camera import is not configured.",
            )
        return camera

    async def principal_from_header(
        authorization: Annotated[str | None, Header()] = None,
    ) -> FabricPrincipal:
        if authorization is None or not authorization.startswith("Bearer "):
            raise FabricAuthenticationError("A Fabric bearer credential is required")
        return get_auth().authenticate(authorization.removeprefix("Bearer "), at=clock())

    def require(permission: str) -> Callable[..., Awaitable[FabricPrincipal]]:
        async def dependency(
            principal: Annotated[FabricPrincipal, Depends(principal_from_header)],
        ) -> FabricPrincipal:
            get_auth().require(principal, permission)
            return principal

        return dependency

    @app.exception_handler(SonyCameraImportError)
    async def sony_camera_error_handler(
        _request: Request,
        error: SonyCameraImportError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "code": error.code,
                "message": str(error),
                "correlationId": str(uuid4()),
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.get(
        "/api/v1/fabric/camera-import",
        response_model=CameraImportSnapshot,
        response_model_exclude_none=True,
    )
    async def camera_import_status(
        _principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.nodes.read")),
        ],
    ) -> CameraImportSnapshot:
        return await get_camera_import().snapshot(refresh=True)

    @app.get(
        "/api/v1/fabric/camera-imports",
        response_model=list[CameraImportSnapshot],
        response_model_exclude_none=True,
    )
    async def camera_import_statuses(
        _principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.nodes.read")),
        ],
    ) -> list[CameraImportSnapshot]:
        return [await configured.snapshot(refresh=True) for configured in camera_imports().values()]

    @app.post(
        "/api/v1/fabric/camera-import/start",
        response_model=CameraImportActionResult,
        response_model_exclude_none=True,
    )
    async def start_camera_import(
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.commands.submit")),
        ],
    ) -> CameraImportActionResult:
        try:
            result = await get_camera_import().start_import()
        except SonyCameraImportError as error:
            _audit_camera_import(
                get_repository(),
                principal,
                clock(),
                outcome="denied",
                details={"code": error.code},
            )
            raise
        _audit_camera_import(
            get_repository(),
            principal,
            clock(),
            outcome="succeeded",
            details={
                "status": "accepted",
                "cameraFilesDeleted": False,
                "phoneFilesDeleted": False,
            },
        )
        return result

    @app.post(
        "/api/v1/fabric/camera-imports/{camera_id}/start",
        response_model=CameraImportActionResult,
        response_model_exclude_none=True,
    )
    async def start_named_camera_import(
        camera_id: str,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.commands.submit")),
        ],
    ) -> CameraImportActionResult:
        configured = camera_import(camera_id)
        try:
            result = await configured.start_import()
        except SonyCameraImportError as error:
            _audit_camera_import(
                get_repository(),
                principal,
                clock(),
                outcome="denied",
                details={"code": error.code},
                resource_id=configured.camera_id,
            )
            raise
        _audit_camera_import(
            get_repository(),
            principal,
            clock(),
            outcome="succeeded",
            details={
                "status": "accepted",
                "cameraFilesDeleted": False,
                "phoneFilesDeleted": False,
            },
            resource_id=configured.camera_id,
        )
        return result

    @app.post(
        "/api/v1/fabric/camera-import/open-destination",
        response_model=CameraDestinationActionResult,
        response_model_exclude_none=True,
    )
    async def open_camera_import_destination(
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.commands.submit")),
        ],
    ) -> CameraDestinationActionResult:
        try:
            result = await get_camera_import().open_destination()
        except SonyCameraImportError as error:
            _audit_camera_import(
                get_repository(),
                principal,
                clock(),
                outcome="denied",
                details={"code": error.code},
                action="fabric.camera_import.destination.open",
            )
            raise
        _audit_camera_import(
            get_repository(),
            principal,
            clock(),
            outcome="succeeded",
            details={"destination": result.destination},
            action="fabric.camera_import.destination.open",
        )
        return result

    @app.post(
        "/api/v1/fabric/camera-imports/{camera_id}/open-destination",
        response_model=CameraDestinationActionResult,
        response_model_exclude_none=True,
    )
    async def open_named_camera_import_destination(
        camera_id: str,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.commands.submit")),
        ],
    ) -> CameraDestinationActionResult:
        configured = camera_import(camera_id)
        try:
            result = await configured.open_destination()
        except SonyCameraImportError as error:
            _audit_camera_import(
                get_repository(),
                principal,
                clock(),
                outcome="denied",
                details={"code": error.code},
                action="fabric.camera_import.destination.open",
                resource_id=configured.camera_id,
            )
            raise
        _audit_camera_import(
            get_repository(),
            principal,
            clock(),
            outcome="succeeded",
            details={"destination": result.destination},
            action="fabric.camera_import.destination.open",
            resource_id=configured.camera_id,
        )
        return result


def _audit_camera_import(
    repository: SQLiteFabricRepository,
    principal: FabricPrincipal,
    at: datetime,
    *,
    outcome: str,
    details: dict[str, object],
    action: str = "fabric.camera_import.start",
    resource_id: str = "sony-zve10-android",
) -> None:
    repository.record_fabric_audit(
        actor_id=principal.identity_id,
        action=action,
        resource_type="camera_media",
        resource_id=resource_id,
        outcome=outcome,
        correlation_id=None,
        occurred_at=at,
        details=details,
    )
