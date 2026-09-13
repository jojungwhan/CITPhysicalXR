"""Local-only administration API for the Control Tower LAN MAC allowlist."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .fabric_android import AndroidControllerService
from .fabric_auth import (
    INSTRUCTOR_PERMISSIONS,
    FabricAuthenticationError,
    FabricAuthService,
    FabricPrincipal,
)
from .fabric_lan_access import (
    LanAccessActionResult,
    LanAccessSnapshot,
    LanMacAccessError,
    LanMacAccessPolicy,
    is_loopback_client,
    normalize_device_name,
    normalize_mac_address,
)
from .fabric_repository import SQLiteFabricRepository

AuthGetter = Callable[[], FabricAuthService]
RepositoryGetter = Callable[[], SQLiteFabricRepository]


class LanAccessDeviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    displayName: str = Field(min_length=1, max_length=80)
    macAddress: str

    @field_validator("displayName")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalize_device_name(value)

    @field_validator("macAddress")
    @classmethod
    def validate_mac_address(cls, value: str) -> str:
        return normalize_mac_address(value)


class LanAccessLinkResult(BaseModel):
    schemaVersion: Literal["1.0"] = "1.0"
    accessUrl: str
    expiresAt: datetime


def install_fabric_lan_access_api(
    app: FastAPI,
    *,
    policy: LanMacAccessPolicy,
    get_auth: AuthGetter,
    get_repository: RepositoryGetter,
    clock: Callable[[], datetime],
    android_controller: AndroidControllerService | None,
) -> None:
    async def principal_from_header(
        authorization: Annotated[str | None, Header()] = None,
    ) -> FabricPrincipal:
        if authorization is None or not authorization.startswith("Bearer "):
            raise FabricAuthenticationError("A Fabric bearer credential is required")
        return get_auth().authenticate(authorization.removeprefix("Bearer "), at=clock())

    principal_dependency = Depends(principal_from_header)

    async def local_manager(
        request: Request,
        principal: FabricPrincipal = principal_dependency,
    ) -> FabricPrincipal:
        get_auth().require(principal, "fabric.lan_access.manage")
        if not is_loopback_client(request.client.host if request.client else None):
            raise LanMacAccessError(
                "LAN_ACCESS_LOCAL_ONLY",
                "LAN access settings can only be changed from this computer.",
            )
        return principal

    local_manager_dependency = Depends(local_manager)

    async def snapshot() -> LanAccessSnapshot:
        can_enroll = False
        if android_controller is not None:
            android_snapshot = await android_controller.snapshot()
            can_enroll = android_snapshot.operations.openController
        return policy.snapshot(
            can_manage=True,
            can_enroll_usb_android=can_enroll,
        )

    @app.exception_handler(LanMacAccessError)
    async def lan_access_error_handler(
        _request: Request,
        error: LanMacAccessError,
    ) -> JSONResponse:
        status_code = 403 if error.code == "LAN_ACCESS_LOCAL_ONLY" else 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": str(error),
                "correlationId": str(uuid4()),
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.get(
        "/api/v1/fabric/lan-access",
        response_model=LanAccessSnapshot,
        response_model_exclude_none=True,
    )
    async def get_lan_access(
        _principal: FabricPrincipal = local_manager_dependency,
    ) -> LanAccessSnapshot:
        return await snapshot()

    @app.post(
        "/api/v1/fabric/lan-access/devices",
        response_model=LanAccessActionResult,
        response_model_exclude_none=True,
    )
    async def add_lan_access_device(
        body: LanAccessDeviceRequest,
        principal: FabricPrincipal = local_manager_dependency,
    ) -> LanAccessActionResult:
        device = policy.add_device(body.displayName, body.macAddress)
        _audit(
            get_repository(),
            principal,
            clock(),
            action="fabric.lan_access.device.upsert",
            mac_address=device.macAddress,
        )
        return LanAccessActionResult(
            accepted=True,
            message="The device is allowed to reach Control Tower on this local network.",
            snapshot=await snapshot(),
        )

    @app.delete(
        "/api/v1/fabric/lan-access/devices/{mac_address}",
        response_model=LanAccessActionResult,
        response_model_exclude_none=True,
    )
    async def remove_lan_access_device(
        mac_address: str,
        principal: FabricPrincipal = local_manager_dependency,
    ) -> LanAccessActionResult:
        try:
            normalized_mac = normalize_mac_address(mac_address)
        except ValueError as error:
            raise LanMacAccessError(
                "LAN_ACCESS_MAC_INVALID",
                "The MAC address is invalid.",
            ) from error
        removed = policy.remove_device(normalized_mac)
        if not removed:
            raise LanMacAccessError(
                "LAN_ACCESS_DEVICE_NOT_FOUND",
                "The allowed device was not found.",
            )
        _audit(
            get_repository(),
            principal,
            clock(),
            action="fabric.lan_access.device.remove",
            mac_address=normalized_mac,
        )
        return LanAccessActionResult(
            accepted=True,
            message="The device can no longer reach Control Tower over the local network.",
            snapshot=await snapshot(),
        )

    @app.post(
        "/api/v1/fabric/lan-access/enroll-usb-android",
        response_model=LanAccessActionResult,
        response_model_exclude_none=True,
    )
    async def enroll_usb_android(
        principal: FabricPrincipal = local_manager_dependency,
    ) -> LanAccessActionResult:
        if android_controller is None:
            raise LanMacAccessError(
                "LAN_ACCESS_ANDROID_UNAVAILABLE",
                "Android controller support is not configured.",
            )
        if not policy.enabled or policy.lan_origin is None:
            raise LanMacAccessError(
                "LAN_ACCESS_UNAVAILABLE",
                "Control Tower local-network access is not enabled.",
            )
        identity = await android_controller.wifi_identity()
        device = policy.add_device(identity.display_name, identity.mac_address)
        _audit(
            get_repository(),
            principal,
            clock(),
            action="fabric.lan_access.android.enroll",
            mac_address=device.macAddress,
        )
        permissions = tuple(
            sorted(
                (INSTRUCTOR_PERMISSIONS & principal.permissions)
                - {"fabric.console.open_android", "fabric.lan_access.manage"}
            )
        )
        ticket, _expires_at = get_auth().create_console_ticket(
            identity_id=f"android-lan-{uuid4().hex[:16]}",
            actor_type="android_controller",
            permissions=permissions,
            site_id=principal.site_id,
            room_id=principal.room_id,
            at=clock(),
            persistent_session=True,
        )
        await android_controller.open_lan_controller(ticket, policy.lan_origin)
        return LanAccessActionResult(
            accepted=True,
            message="The USB phone is allowed and Control Tower opened over local Wi-Fi.",
            snapshot=await snapshot(),
        )

    @app.post(
        "/api/v1/fabric/lan-access/devices/{mac_address}/access-link",
        response_model=LanAccessLinkResult,
    )
    async def create_lan_access_link(
        mac_address: str,
        principal: FabricPrincipal = local_manager_dependency,
    ) -> LanAccessLinkResult:
        try:
            normalized_mac = normalize_mac_address(mac_address)
        except ValueError as error:
            raise LanMacAccessError(
                "LAN_ACCESS_MAC_INVALID",
                "The MAC address is invalid.",
            ) from error
        if not policy.contains_device(normalized_mac):
            raise LanMacAccessError(
                "LAN_ACCESS_DEVICE_NOT_FOUND",
                "The allowed device was not found.",
            )
        if not policy.enabled or policy.lan_origin is None:
            raise LanMacAccessError(
                "LAN_ACCESS_UNAVAILABLE",
                "Control Tower local-network access is not enabled.",
            )
        permissions = tuple(
            sorted(
                (INSTRUCTOR_PERMISSIONS & principal.permissions)
                - {"fabric.console.open_android", "fabric.lan_access.manage"}
            )
        )
        ticket, expires_at = get_auth().create_console_ticket(
            identity_id=f"lan-controller-{uuid4().hex[:16]}",
            actor_type="android_controller",
            permissions=permissions,
            site_id=principal.site_id,
            room_id=principal.room_id,
            at=clock(),
            persistent_session=True,
        )
        _audit(
            get_repository(),
            principal,
            clock(),
            action="fabric.lan_access.link.issue",
            mac_address=normalized_mac,
        )
        fragment = urlencode({"android-console-ticket": ticket})
        return LanAccessLinkResult(
            accessUrl=f"{policy.lan_origin.rstrip('/')}/fabric#{fragment}",
            expiresAt=expires_at,
        )


def _audit(
    repository: SQLiteFabricRepository,
    principal: FabricPrincipal,
    at: datetime,
    *,
    action: str,
    mac_address: str,
) -> None:
    repository.record_fabric_audit(
        actor_id=principal.identity_id,
        action=action,
        resource_type="lan_client",
        resource_id=mac_address,
        outcome="succeeded",
        correlation_id=None,
        occurred_at=at,
        details={"localOnly": True},
    )
