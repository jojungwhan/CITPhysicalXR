"""Authenticated API for opening Control Tower on one USB Android phone."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse

from .fabric_android import (
    AndroidControllerActionResult,
    AndroidControllerError,
    AndroidControllerService,
    AndroidControllerSnapshot,
)
from .fabric_auth import (
    INSTRUCTOR_PERMISSIONS,
    FabricAuthenticationError,
    FabricAuthService,
    FabricPrincipal,
)
from .fabric_repository import SQLiteFabricRepository

AndroidControllerGetter = Callable[[], AndroidControllerService]
AuthGetter = Callable[[], FabricAuthService]
RepositoryGetter = Callable[[], SQLiteFabricRepository]


def install_fabric_android_api(
    app: FastAPI,
    *,
    get_android_controller: AndroidControllerGetter,
    get_auth: AuthGetter,
    get_repository: RepositoryGetter,
    clock: Callable[[], datetime],
) -> None:
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

    @app.exception_handler(AndroidControllerError)
    async def android_controller_error_handler(
        _request: Request,
        error: AndroidControllerError,
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
        "/api/v1/fabric/android-controller",
        response_model=AndroidControllerSnapshot,
        response_model_exclude_none=True,
    )
    async def android_controller_status(
        _principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.nodes.read")),
        ],
    ) -> AndroidControllerSnapshot:
        return await get_android_controller().snapshot()

    @app.post(
        "/api/v1/fabric/android-controller/open",
        response_model=AndroidControllerActionResult,
        response_model_exclude_none=True,
    )
    async def open_android_controller(
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.console.open_android")),
        ],
    ) -> AndroidControllerActionResult:
        issued_at = clock()
        identity_id = f"android-controller-{uuid4().hex[:16]}"
        permissions = tuple(
            sorted(
                (INSTRUCTOR_PERMISSIONS & principal.permissions)
                - {"fabric.console.open_android", "fabric.lan_access.manage"}
            )
        )
        ticket, _expires_at = get_auth().create_console_ticket(
            identity_id=identity_id,
            actor_type="android_controller",
            permissions=permissions,
            site_id=principal.site_id,
            room_id=principal.room_id,
            at=issued_at,
            persistent_session=True,
        )
        try:
            result = await get_android_controller().open_controller(ticket)
        except AndroidControllerError as error:
            _audit_android_open(
                get_repository(),
                principal,
                issued_at,
                outcome="failed",
                details={"code": error.code},
            )
            raise
        _audit_android_open(
            get_repository(),
            principal,
            issued_at,
            outcome="succeeded",
            details={
                "singleUse": True,
                "persistentSession": True,
                "transport": "adb_reverse",
            },
        )
        return result


def _audit_android_open(
    repository: SQLiteFabricRepository,
    principal: FabricPrincipal,
    at: datetime,
    *,
    outcome: str,
    details: dict[str, object],
) -> None:
    repository.record_fabric_audit(
        actor_id=principal.identity_id,
        action="fabric.android_controller.open",
        resource_type="console",
        resource_id="usb-android-controller",
        outcome=outcome,
        correlation_id=None,
        occurred_at=at,
        details=details,
    )
