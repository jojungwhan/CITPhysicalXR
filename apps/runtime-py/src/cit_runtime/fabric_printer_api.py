"""Authenticated, audited HTTP routes for the bounded 3D-printer workflow."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import unquote
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .fabric_auth import (
    FabricAuthenticationError,
    FabricAuthService,
    FabricPrincipal,
)
from .fabric_printer import (
    CrealityPrinterService,
    PrinterActionResult,
    PrinterError,
    PrinterSnapshot,
    PrinterSourceArtifact,
    PrinterStartIntent,
)
from .fabric_repository import SQLiteFabricRepository

_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"


class PrinterSliceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profileId: Annotated[str, Field(min_length=1, max_length=96, pattern=_IDENTIFIER_PATTERN)]


class PrinterStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmationToken: Annotated[str, Field(min_length=32, max_length=128)]
    plateClearConfirmed: Literal[True]
    profileConfirmed: Literal[True]


PrinterGetter = Callable[[], CrealityPrinterService]
AuthGetter = Callable[[], FabricAuthService]
RepositoryGetter = Callable[[], SQLiteFabricRepository]


def install_fabric_printer_api(
    app: FastAPI,
    *,
    get_printer: PrinterGetter,
    get_auth: AuthGetter,
    get_repository: RepositoryGetter,
    clock: Callable[[], datetime],
) -> None:
    """Install routes without making any eager printer or slicer connection."""

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

    @app.exception_handler(PrinterError)
    async def printer_error_handler(_request: Request, error: PrinterError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={
                "code": error.code,
                "message": str(error),
                "correlationId": str(uuid4()),
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.get(
        "/api/v1/fabric/printer",
        response_model=PrinterSnapshot,
        response_model_exclude_none=True,
    )
    async def printer_status(
        _principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.nodes.read")),
        ],
    ) -> PrinterSnapshot:
        return await get_printer().snapshot(refresh=True)

    @app.post(
        "/api/v1/fabric/printer/verify-idle",
        response_model=PrinterActionResult,
        response_model_exclude_none=True,
    )
    async def verify_printer_idle(
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.commands.submit")),
        ],
    ) -> PrinterActionResult:
        try:
            result = await get_printer().verify_idle()
        except PrinterError as error:
            _audit_printer(
                get_repository(),
                principal,
                "fabric.printer.verify_idle",
                clock(),
                outcome="denied",
                details={"code": error.code},
            )
            raise
        _audit_printer(
            get_repository(),
            principal,
            "fabric.printer.verify_idle",
            clock(),
        )
        return result

    @app.post(
        "/api/v1/fabric/printer/sources",
        response_model=PrinterSourceArtifact,
        response_model_exclude_none=True,
    )
    async def stage_printer_source(
        request: Request,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.commands.submit")),
        ],
        file_name: Annotated[
            str,
            Header(alias="X-CIT-Filename", min_length=1, max_length=1500),
        ],
        content_type: Annotated[
            str,
            Header(alias="Content-Type", min_length=1, max_length=128),
        ] = "application/octet-stream",
    ) -> PrinterSourceArtifact:
        try:
            artifact = await get_printer().stage_source(
                file_name=_decode_file_name(file_name),
                media_type=content_type.split(";", maxsplit=1)[0].strip().casefold(),
                content=await request.body(),
            )
        except PrinterError as error:
            _audit_printer(
                get_repository(),
                principal,
                "fabric.printer.source.stage",
                clock(),
                outcome="denied",
                details={"code": error.code},
            )
            raise
        _audit_printer(
            get_repository(),
            principal,
            "fabric.printer.source.stage",
            clock(),
            resource_id=artifact.artifactId,
            details={
                "fileName": artifact.fileName,
                "sizeBytes": artifact.sizeBytes,
                "sha256": artifact.sha256,
            },
        )
        return artifact

    @app.post(
        "/api/v1/fabric/printer/sources/{source_id}/slice",
        response_model=PrinterActionResult,
        response_model_exclude_none=True,
    )
    async def slice_printer_source(
        source_id: str,
        request: PrinterSliceRequest,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.commands.submit")),
        ],
    ) -> PrinterActionResult:
        try:
            result = await get_printer().slice_source(source_id, request.profileId)
        except PrinterError as error:
            _audit_printer(
                get_repository(),
                principal,
                "fabric.printer.slice",
                clock(),
                outcome="denied",
                resource_id=source_id,
                details={"code": error.code, "profileId": request.profileId},
            )
            raise
        _audit_printer(
            get_repository(),
            principal,
            "fabric.printer.slice",
            clock(),
            resource_id=source_id,
            details={"profileId": request.profileId, "networkUsed": False},
        )
        return result

    @app.get("/api/v1/fabric/printer/artifacts/{artifact_id}/download")
    async def download_printer_artifact(
        artifact_id: str,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.commands.read")),
        ],
    ) -> FileResponse:
        artifact, path = get_printer().gcode_download(artifact_id)
        _audit_printer(
            get_repository(),
            principal,
            "fabric.printer.artifact.download",
            clock(),
            resource_id=artifact_id,
            details={"sha256": artifact.sha256},
        )
        return FileResponse(
            path,
            media_type="text/x-gcode",
            filename=artifact.fileName,
            headers={"X-CIT-SHA256": artifact.sha256},
        )

    @app.post(
        "/api/v1/fabric/printer/artifacts/{artifact_id}/upload",
        response_model=PrinterActionResult,
        response_model_exclude_none=True,
    )
    async def upload_printer_artifact(
        artifact_id: str,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.commands.submit")),
        ],
    ) -> PrinterActionResult:
        try:
            result = await get_printer().upload_artifact(artifact_id)
        except PrinterError as error:
            _audit_printer(
                get_repository(),
                principal,
                "fabric.printer.upload",
                clock(),
                outcome="denied",
                resource_id=artifact_id,
                details={"code": error.code, "autoStart": False},
            )
            raise
        _audit_printer(
            get_repository(),
            principal,
            "fabric.printer.upload",
            clock(),
            resource_id=artifact_id,
            details={"autoStart": False},
        )
        return result

    @app.post(
        "/api/v1/fabric/printer/artifacts/{artifact_id}/start-intent",
        response_model=PrinterStartIntent,
        response_model_exclude_none=True,
    )
    async def prepare_printer_start(
        artifact_id: str,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.commands.submit")),
        ],
    ) -> PrinterStartIntent:
        try:
            intent = await get_printer().prepare_start(
                artifact_id,
                actor_id=principal.identity_id,
            )
        except PrinterError as error:
            _audit_printer(
                get_repository(),
                principal,
                "fabric.printer.start.prepare",
                clock(),
                outcome="denied",
                resource_id=artifact_id,
                details={"code": error.code},
            )
            raise
        _audit_printer(
            get_repository(),
            principal,
            "fabric.printer.start.prepare",
            clock(),
            resource_id=artifact_id,
            details={"expiresAt": intent.expiresAt.isoformat()},
        )
        return intent

    @app.post(
        "/api/v1/fabric/printer/artifacts/{artifact_id}/start",
        response_model=PrinterActionResult,
        response_model_exclude_none=True,
    )
    async def start_printer_artifact(
        artifact_id: str,
        request: PrinterStartRequest,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.commands.submit")),
        ],
    ) -> PrinterActionResult:
        try:
            result = await get_printer().start_artifact(
                artifact_id,
                actor_id=principal.identity_id,
                confirmation_token=request.confirmationToken,
            )
        except PrinterError as error:
            _audit_printer(
                get_repository(),
                principal,
                "fabric.printer.start",
                clock(),
                outcome="unknown" if error.code == "PRINTER_START_OUTCOME_UNKNOWN" else "denied",
                resource_id=artifact_id,
                details={"code": error.code, "automaticRetry": False},
            )
            raise
        _audit_printer(
            get_repository(),
            principal,
            "fabric.printer.start",
            clock(),
            resource_id=artifact_id,
            details={"automaticRetry": False},
        )
        return result


def _audit_printer(
    repository: SQLiteFabricRepository,
    principal: FabricPrincipal,
    action: str,
    at: datetime,
    *,
    outcome: str = "succeeded",
    resource_id: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    repository.record_fabric_audit(
        actor_id=principal.identity_id,
        action=action,
        resource_type="3d_printer",
        resource_id=resource_id,
        outcome=outcome,
        correlation_id=None,
        occurred_at=at,
        details=details,
    )


def _decode_file_name(value: str) -> str:
    try:
        return unquote(value, encoding="utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PrinterError(
            "PRINTER_SOURCE_NAME_INVALID",
            "Model filename is invalid",
            status_code=422,
        ) from error
