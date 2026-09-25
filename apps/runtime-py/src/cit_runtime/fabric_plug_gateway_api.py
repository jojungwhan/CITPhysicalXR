"""Local authenticated UI boundary for independently paired plug gateways."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .fabric_auth import FabricAuthenticationError, FabricAuthService, FabricPrincipal
from .fabric_plug_gateways import GatewaySnapshot, PlugGatewayService
from .fabric_repository import SQLiteFabricRepository
from .fabric_unlock_automation import (
    RemotePlugPowerResult,
    UnlockAutomationConfigurationRequest,
    UnlockAutomationError,
)


class GatewayPowerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on: bool
    selectedNodeIds: list[str] = Field(min_length=1, max_length=8)

    @field_validator("selectedNodeIds")
    @classmethod
    def validate_selection(cls, value: list[str]) -> list[str]:
        return UnlockAutomationConfigurationRequest.validate_node_ids(value)


def install_plug_gateway_api(
    app: FastAPI,
    *,
    service: PlugGatewayService,
    get_auth: Callable[[], FabricAuthService],
    get_repository: Callable[[], SQLiteFabricRepository],
    clock: Callable[[], datetime],
    allow_physical: bool,
) -> None:
    async def principal_from_header(
        authorization: Annotated[str | None, Header()] = None,
    ) -> FabricPrincipal:
        if authorization is None or not authorization.startswith("Bearer "):
            raise FabricAuthenticationError("A Fabric bearer credential is required")
        principal = get_auth().authenticate(authorization.removeprefix("Bearer "), at=clock())
        if any((principal.site_id, principal.room_id, principal.session_id)):
            raise UnlockAutomationError(
                "PLUG_GATEWAY_SCOPE_DENIED",
                "Gateway access requires an unscoped local operator.",
                status_code=403,
            )
        return principal

    principal_dependency = Depends(principal_from_header)

    @app.exception_handler(UnlockAutomationError)
    async def gateway_error(_request: Request, error: UnlockAutomationError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code, content={"code": error.code, "message": str(error)}
        )

    @app.get("/api/v1/fabric/plug-gateways", response_model=list[GatewaySnapshot])
    async def snapshots(principal: FabricPrincipal = principal_dependency) -> list[GatewaySnapshot]:
        get_auth().require(principal, "fabric.nodes.read")
        can_control = allow_physical and "fabric.commands.submit" in principal.permissions
        return [
            snapshot.model_copy(update={"canControl": can_control})
            for snapshot in await service.snapshots()
        ]

    @app.post("/api/v1/fabric/plug-gateways/{site_id}/power", response_model=RemotePlugPowerResult)
    async def power(
        site_id: str, body: GatewayPowerRequest, principal: FabricPrincipal = principal_dependency
    ) -> RemotePlugPowerResult:
        get_auth().require(principal, "fabric.commands.submit")
        if not allow_physical:
            raise UnlockAutomationError(
                "PHYSICAL_ACTUATION_DISABLED",
                "Enable classroom devices before controlling gateway plugs.",
                status_code=403,
            )
        outcome = "failed"
        try:
            result = await service.power(site_id, body.on, body.selectedNodeIds)
            outcome = "succeeded" if result.accepted else "failed"
            return result
        finally:
            get_repository().record_fabric_audit(
                actor_id=principal.identity_id,
                action="fabric.plug_gateway.power",
                resource_type="remote_smart_plug_site",
                resource_id=site_id,
                outcome=outcome,
                correlation_id=None,
                occurred_at=clock(),
                details={"requestedOn": body.on, "selectedNodeIds": body.selectedNodeIds},
            )
