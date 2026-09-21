"""Narrow signed API for explicit phone control of one local Matter site.

This router deliberately accepts neither Fabric bearer credentials nor arbitrary
node identifiers.  A paired companion can read and set only the exact plug group
saved by the local operator.  Tailscale Serve publishes only this path while the
ordinary Control Tower service remains loopback/local-LAN scoped.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import Body, Depends, FastAPI, Header

from .fabric_repository import SQLiteFabricRepository
from .fabric_unlock_automation import (
    RemotePlugPowerRequest,
    RemotePlugPowerResult,
    RemotePlugSiteState,
    RemotePlugStateRequest,
    RemotePowerCommandRunner,
    UnlockAutomationService,
)

RepositoryGetter = Callable[[], SQLiteFabricRepository]
RemoteStateReader = Callable[[tuple[str, ...]], RemotePlugSiteState]


@dataclass(frozen=True, slots=True)
class _AuthenticatedStateRequest:
    body: RemotePlugStateRequest
    selected_node_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _AuthenticatedPowerRequest:
    body: RemotePlugPowerRequest
    result: RemotePlugPowerResult


def install_fabric_remote_plug_api(
    app: FastAPI,
    *,
    service: UnlockAutomationService,
    get_repository: RepositoryGetter,
    clock: Callable[[], datetime],
    state_reader: RemoteStateReader,
    command_runner: RemotePowerCommandRunner,
) -> None:
    """Install the complete and intentionally tiny remote physical API."""

    async def authenticated_state_request(
        body: Annotated[RemotePlugStateRequest, Body()],
        signature: Annotated[
            str,
            Header(alias="X-CIT-Remote-Signature", min_length=64, max_length=64),
        ],
    ) -> _AuthenticatedStateRequest:
        selected = service.authenticate_remote_state(body, signature)
        return _AuthenticatedStateRequest(body=body, selected_node_ids=selected)

    async def authenticated_power_request(
        body: Annotated[RemotePlugPowerRequest, Body()],
        signature: Annotated[
            str,
            Header(alias="X-CIT-Remote-Signature", min_length=64, max_length=64),
        ],
    ) -> _AuthenticatedPowerRequest:
        result = await service.accept_remote_power(body, signature, command_runner)
        return _AuthenticatedPowerRequest(body=body, result=result)

    state_request_dependency = Depends(authenticated_state_request)
    power_request_dependency = Depends(authenticated_power_request)

    @app.post(
        "/api/v1/fabric/remote-plugs/state",
        response_model=RemotePlugSiteState,
        response_model_exclude_none=True,
    )
    async def remote_plug_state(
        request: _AuthenticatedStateRequest = state_request_dependency,
    ) -> RemotePlugSiteState:
        result = state_reader(request.selected_node_ids)
        _audit(
            get_repository(),
            request.body.deviceId,
            clock(),
            service=service,
            action="fabric.smart_plug.remote_state",
            outcome="succeeded",
            details={
                "eventId": str(request.body.eventId),
                "sequence": request.body.sequence,
                "selectedCount": len(request.selected_node_ids),
            },
        )
        return result

    @app.post(
        "/api/v1/fabric/remote-plugs/power",
        response_model=RemotePlugPowerResult,
    )
    async def remote_plug_power(
        request: _AuthenticatedPowerRequest = power_request_dependency,
    ) -> RemotePlugPowerResult:
        body = request.body
        result = request.result
        _audit(
            get_repository(),
            body.deviceId,
            clock(),
            service=service,
            action="fabric.smart_plug.remote_power",
            outcome="succeeded" if result.accepted else "failed",
            details={
                "eventId": str(body.eventId),
                "sequence": body.sequence,
                "requestedOn": body.on,
                "requestedCount": result.requestedCount,
                "acceptedCount": result.acceptedCount,
            },
        )
        return result


def _audit(
    repository: SQLiteFabricRepository,
    actor_id: str,
    at: datetime,
    *,
    service: UnlockAutomationService,
    action: str,
    outcome: str,
    details: dict[str, object],
) -> None:
    repository.record_fabric_audit(
        actor_id=actor_id,
        action=action,
        resource_type="remote_smart_plug_site",
        resource_id=service.site_id,
        outcome=outcome,
        correlation_id=None,
        occurred_at=at,
        details=details,
    )
