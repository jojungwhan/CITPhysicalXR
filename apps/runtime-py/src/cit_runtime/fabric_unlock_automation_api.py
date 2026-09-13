"""Local administration and signed wireless trigger API for phone unlock automation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from .fabric import InteractionFabric
from .fabric_android import AndroidControllerError, AndroidControllerService
from .fabric_auth import FabricAuthenticationError, FabricAuthService, FabricPrincipal
from .fabric_lan_access import LanMacAccessPolicy, is_loopback_client
from .fabric_repository import SQLiteFabricRepository
from .fabric_unlock_automation import (
    ToggleCommandRunner,
    ToggleEventRequest,
    ToggleEventResult,
    UnlockAutomationConfigurationRequest,
    UnlockAutomationError,
    UnlockAutomationPairRequest,
    UnlockAutomationService,
    UnlockAutomationSnapshot,
    UnlockCommandRunner,
    UnlockEventRequest,
    UnlockEventResult,
    known_smart_plug_node_ids,
)

AuthGetter = Callable[[], FabricAuthService]
FabricGetter = Callable[[], InteractionFabric]
RepositoryGetter = Callable[[], SQLiteFabricRepository]


class UnlockAutomationActionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    message: str
    snapshot: UnlockAutomationSnapshot


def install_fabric_unlock_automation_api(
    app: FastAPI,
    *,
    service: UnlockAutomationService,
    get_fabric: FabricGetter,
    get_auth: AuthGetter,
    get_repository: RepositoryGetter,
    clock: Callable[[], datetime],
    command_runner: UnlockCommandRunner,
    toggle_command_runner: ToggleCommandRunner,
    android_controller: AndroidControllerService | None,
    lan_access: LanMacAccessPolicy | None,
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
            raise UnlockAutomationError(
                "UNLOCK_AUTOMATION_LOCAL_ONLY",
                "Unlock automation settings can only be changed from this computer.",
                status_code=403,
            )
        return principal

    local_manager_dependency = Depends(local_manager)

    async def snapshot() -> UnlockAutomationSnapshot:
        android_ready = False
        if android_controller is not None:
            current = await android_controller.snapshot()
            android_ready = current.operations.openController
        return service.snapshot(
            can_manage=True,
            can_install_and_pair=android_ready and service.can_install_and_pair(),
        )

    @app.exception_handler(UnlockAutomationError)
    async def unlock_automation_error_handler(
        _request: Request,
        error: UnlockAutomationError,
    ) -> JSONResponse:
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
        "/api/v1/fabric/unlock-automation",
        response_model=UnlockAutomationSnapshot,
        response_model_exclude_none=True,
    )
    async def get_unlock_automation(
        _principal: FabricPrincipal = local_manager_dependency,
    ) -> UnlockAutomationSnapshot:
        return await snapshot()

    @app.put(
        "/api/v1/fabric/unlock-automation/configuration",
        response_model=UnlockAutomationActionResult,
        response_model_exclude_none=True,
    )
    async def configure_unlock_automation(
        body: UnlockAutomationConfigurationRequest,
        principal: FabricPrincipal = local_manager_dependency,
    ) -> UnlockAutomationActionResult:
        updated = service.configure(
            body,
            known_node_ids=known_smart_plug_node_ids(get_fabric()),
        )
        _audit(
            get_repository(),
            principal.identity_id,
            clock(),
            action="fabric.unlock_automation.configure",
            outcome="succeeded",
            details={
                "enabled": body.enabled,
                "selectedCount": len(body.selectedNodeIds),
            },
        )
        return UnlockAutomationActionResult(
            accepted=True,
            message=(
                "Phone-unlock automation is enabled for the selected Matter smart plugs."
                if body.enabled
                else "Phone-unlock automation is disabled."
            ),
            snapshot=updated,
        )

    @app.post(
        "/api/v1/fabric/unlock-automation/companion/pair-usb",
        response_model=UnlockAutomationActionResult,
        response_model_exclude_none=True,
    )
    async def install_and_pair_companion(
        body: UnlockAutomationPairRequest,
        principal: FabricPrincipal = local_manager_dependency,
    ) -> UnlockAutomationActionResult:
        if android_controller is None:
            raise UnlockAutomationError(
                "UNLOCK_AUTOMATION_ANDROID_UNAVAILABLE",
                "The one-time Android installer is not configured.",
            )
        apk_path = service.companion_apk_path
        if apk_path is None or not service.can_install_and_pair():
            raise UnlockAutomationError(
                "UNLOCK_AUTOMATION_APK_UNAVAILABLE",
                "Build the Control Tower Companion APK before pairing the phone.",
            )
        if lan_access is None or not lan_access.enabled or service.lan_origin is None:
            raise UnlockAutomationError(
                "UNLOCK_AUTOMATION_LAN_UNAVAILABLE",
                "Enable local Wi-Fi access before pairing the phone.",
            )
        try:
            wifi_identity = await android_controller.wifi_identity()
            candidate = service.create_pairing(body.displayName or wifi_identity.display_name)
            await android_controller.install_unlock_companion(
                apk_path,
                candidate.provisioning_uri,
            )
        except AndroidControllerError as error:
            raise UnlockAutomationError(error.code, str(error)) from error
        lan_access.add_device(wifi_identity.display_name, wifi_identity.mac_address)
        service.commit_pairing(candidate)
        _audit(
            get_repository(),
            principal.identity_id,
            clock(),
            action="fabric.unlock_automation.companion.pair",
            outcome="succeeded",
            details={
                "deviceId": candidate.device_id,
                "transport": "one_time_usb_install",
                "runtimeTransport": "local_wifi",
            },
        )
        return UnlockAutomationActionResult(
            accepted=True,
            message=(
                "Control Tower Companion is paired. USB can now be disconnected; "
                "enable the selected plugs separately."
            ),
            snapshot=await snapshot(),
        )

    @app.delete(
        "/api/v1/fabric/unlock-automation/companion",
        response_model=UnlockAutomationActionResult,
        response_model_exclude_none=True,
    )
    async def remove_unlock_companion(
        principal: FabricPrincipal = local_manager_dependency,
    ) -> UnlockAutomationActionResult:
        service.remove_companion()
        _audit(
            get_repository(),
            principal.identity_id,
            clock(),
            action="fabric.unlock_automation.companion.remove",
            outcome="succeeded",
            details={"enabled": False},
        )
        return UnlockAutomationActionResult(
            accepted=True,
            message="The wireless unlock companion is unpaired and automation is disabled.",
            snapshot=await snapshot(),
        )

    @app.post(
        "/api/v1/fabric/unlock-automation/events",
        response_model=UnlockEventResult,
    )
    async def receive_unlock_event(
        body: UnlockEventRequest,
        x_cit_unlock_signature: Annotated[
            str,
            Header(alias="X-CIT-Unlock-Signature", min_length=64, max_length=64),
        ],
    ) -> UnlockEventResult:
        result = await service.accept_event(body, x_cit_unlock_signature, command_runner)
        _audit(
            get_repository(),
            body.deviceId,
            clock(),
            action="fabric.unlock_automation.trigger",
            outcome="succeeded" if result.accepted else "failed",
            details={
                "eventId": str(body.eventId),
                "sequence": body.sequence,
                "trigger": "android.user_present",
                "result": result.outcome,
                "requestedCount": result.requestedCount,
                "acceptedCount": result.acceptedCount,
            },
        )
        return result

    @app.post(
        "/api/v1/fabric/unlock-automation/toggle",
        response_model=ToggleEventResult,
        response_model_exclude_none=True,
    )
    async def toggle_saved_smart_plugs(
        body: ToggleEventRequest,
        x_cit_toggle_signature: Annotated[
            str,
            Header(alias="X-CIT-Toggle-Signature", min_length=64, max_length=64),
        ],
    ) -> ToggleEventResult:
        result = await service.accept_toggle(
            body,
            x_cit_toggle_signature,
            toggle_command_runner,
        )
        _audit(
            get_repository(),
            body.deviceId,
            clock(),
            action="fabric.smart_plug.phone_toggle",
            outcome="succeeded" if result.accepted else "failed",
            details={
                "eventId": str(body.eventId),
                "sequence": body.sequence,
                "trigger": "android.main_screen_button",
                "result": result.outcome,
                "requestedCount": result.requestedCount,
                "acceptedCount": result.acceptedCount,
                "on": result.on,
            },
        )
        return result


def _audit(
    repository: SQLiteFabricRepository,
    actor_id: str,
    at: datetime,
    *,
    action: str,
    outcome: str,
    details: dict[str, object],
) -> None:
    repository.record_fabric_audit(
        actor_id=actor_id,
        action=action,
        resource_type="unlock_automation",
        resource_id="wireless-android-unlock",
        outcome=outcome,
        correlation_id=None,
        occurred_at=at,
        details=details,
    )
