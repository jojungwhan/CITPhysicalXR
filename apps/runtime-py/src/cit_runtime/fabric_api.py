"""Authenticated HTTP and WebSocket routes for the CIT Interaction Fabric."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import uuid4

from cit_protocol import (
    CoursePack,
    CreateInteractionSessionRequest,
    FabricCommandPriority,
    FabricCommandRequest,
    FabricEventEnvelope,
    FabricSessionMode,
    IntegrationNode,
    InteractionSession,
    PluginManifest,
    to_wire,
)
from fastapi import Depends, FastAPI, Header, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .fabric import (
    FabricConflictError,
    FabricNotFoundError,
    FabricPolicyError,
    InteractionFabric,
)
from .fabric_adapters import FabricAdapterConnections
from .fabric_auth import (
    INSTRUCTOR_PERMISSIONS,
    FabricAuthenticationError,
    FabricAuthorizationError,
    FabricAuthService,
    FabricPrincipal,
)
from .fabric_course import device_monitoring_course_pack
from .fabric_discovery import (
    SESSION_TARGET_ACTION_COURSE_PACKS,
    FabricDiscoveryActionResult,
    FabricDiscoveryError,
    FabricDiscoveryReport,
    FabricDiscoveryService,
    FabricDiscoverySessionTarget,
    FabricRememberedConnection,
    FabricRememberedConnectionResult,
    FabricRememberedConnections,
    LegoConnectionConfiguration,
    MatterWifiConfiguration,
    SpheroBoltConnectionConfiguration,
    SpheroOllieConnectionConfiguration,
    WonderWorkshopConnectionConfiguration,
    remembered_connection_policies_for_nodes,
    remembered_connection_policy,
)
from .fabric_installation import FabricInstallationCatalog, FabricInstallationInfo
from .fabric_persistence import FABRIC_PAGE_LIMIT, FabricIdentityRecord
from .fabric_repository import SQLiteFabricRepository

_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"


class IssueIdentityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identityId: Annotated[str, Field(min_length=1, max_length=128, pattern=_IDENTIFIER_PATTERN)]
    actorType: Literal[
        "administrator",
        "instructor",
        "teaching_assistant",
        "student",
        "observer",
        "automated_agent",
        "adapter",
    ]
    roles: Annotated[list[str], Field(min_length=1, max_length=16)]
    permissions: Annotated[list[str], Field(min_length=1, max_length=32)]
    siteId: Annotated[
        str | None,
        Field(min_length=1, max_length=128, pattern=_IDENTIFIER_PATTERN),
    ] = None
    roomId: Annotated[
        str | None,
        Field(min_length=1, max_length=128, pattern=_IDENTIFIER_PATTERN),
    ] = None
    sessionId: Annotated[
        str | None,
        Field(min_length=1, max_length=128, pattern=_IDENTIFIER_PATTERN),
    ] = None
    ttlSeconds: Annotated[int, Field(ge=60, le=7_776_000)] = 86_400


class RedeemConsoleTicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket: Annotated[str, Field(min_length=32, max_length=128)]


class AssignRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodeId: Annotated[str, Field(min_length=1, max_length=128, pattern=_IDENTIFIER_PATTERN)]


class EnsureMonitoringSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    siteId: Annotated[str, Field(min_length=1, max_length=128, pattern=_IDENTIFIER_PATTERN)]
    roomId: Annotated[str, Field(min_length=1, max_length=128, pattern=_IDENTIFIER_PATTERN)]
    mode: Literal["simulation", "physical"]


class SessionStartPolicyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessionId: str
    requiresArming: bool


class DiscoveryActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmGrounded: bool = False
    sessionId: Annotated[
        str | None,
        Field(min_length=1, max_length=128, pattern=_IDENTIFIER_PATTERN),
    ] = None


class MatterCommissioningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    setupCode: SecretStr


class FabricStreamAuthentication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["authenticate"]
    token: Annotated[str, Field(min_length=32, max_length=512)]
    sessionId: Annotated[
        str | None,
        Field(min_length=1, max_length=128, pattern=_IDENTIFIER_PATTERN),
    ] = None
    afterEventSequence: Annotated[int, Field(ge=0)] = 0


FabricGetter = Callable[[], InteractionFabric]
AuthGetter = Callable[[], FabricAuthService]
ConnectionsGetter = Callable[[], FabricAdapterConnections]
RepositoryGetter = Callable[[], SQLiteFabricRepository]
DiscoveryGetter = Callable[[], FabricDiscoveryService]
StopAll = Callable[[], Awaitable[dict[str, object]]]


def install_fabric_api(
    app: FastAPI,
    *,
    get_fabric: FabricGetter,
    get_auth: AuthGetter,
    get_connections: ConnectionsGetter,
    get_repository: RepositoryGetter,
    get_discovery: DiscoveryGetter,
    clock: Callable[[], datetime],
    allowed_origins: frozenset[str],
    stop_all: StopAll,
    installation_catalog: FabricInstallationCatalog,
) -> None:
    def current_time() -> datetime:
        return clock()

    async def principal_from_header(
        authorization: Annotated[str | None, Header()] = None,
    ) -> FabricPrincipal:
        if authorization is None or not authorization.startswith("Bearer "):
            raise FabricAuthenticationError("A Fabric bearer credential is required")
        token = authorization.removeprefix("Bearer ")
        return get_auth().authenticate(token, at=current_time())

    def require(permission: str) -> Callable[..., Awaitable[FabricPrincipal]]:
        async def dependency(
            principal: Annotated[FabricPrincipal, Depends(principal_from_header)],
        ) -> FabricPrincipal:
            get_auth().require(principal, permission)
            if principal.actor_type in {"instructor", "administrator"}:
                # An open console polls this API continuously. Treat that as a
                # tutor attending the room so a lesson can stay armed for a
                # full teaching block instead of the unattended window.
                get_fabric().note_console_attendance()
            return principal

        return dependency

    @app.exception_handler(FabricAuthenticationError)
    async def authentication_error_handler(
        _request: Request,
        _error: FabricAuthenticationError,
    ) -> JSONResponse:
        return _fabric_error(401, "AUTHENTICATION_REQUIRED", "Fabric authentication failed")

    @app.exception_handler(FabricAuthorizationError)
    async def authorization_error_handler(
        _request: Request,
        error: FabricAuthorizationError,
    ) -> JSONResponse:
        return _fabric_error(403, "AUTHORIZATION_DENIED", str(error))

    @app.exception_handler(FabricNotFoundError)
    async def not_found_error_handler(
        _request: Request,
        error: FabricNotFoundError,
    ) -> JSONResponse:
        return _fabric_error(404, error.code, str(error))

    @app.exception_handler(FabricConflictError)
    async def conflict_error_handler(
        _request: Request,
        error: FabricConflictError,
    ) -> JSONResponse:
        return _fabric_error(409, error.code, str(error))

    @app.exception_handler(FabricPolicyError)
    async def policy_error_handler(
        _request: Request,
        error: FabricPolicyError,
    ) -> JSONResponse:
        return _fabric_error(403, error.code, str(error))

    @app.exception_handler(FabricDiscoveryError)
    async def discovery_error_handler(
        _request: Request,
        error: FabricDiscoveryError,
    ) -> JSONResponse:
        return _fabric_error(409, error.code, str(error))

    @app.get("/api/v1/fabric/auth/whoami")
    async def whoami(
        principal: Annotated[FabricPrincipal, Depends(principal_from_header)],
    ) -> dict[str, object]:
        return _principal_wire(principal)

    @app.post(
        "/api/v1/fabric/auth/console-tickets",
        status_code=201,
    )
    async def create_console_ticket(
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.auth.issue")),
        ],
    ) -> dict[str, object]:
        issued_at = current_time()
        identity_id = f"tutor-console-{uuid4().hex[:16]}"
        permissions = tuple(sorted(INSTRUCTOR_PERMISSIONS & principal.permissions))
        ticket, ticket_expires_at = get_auth().create_console_ticket(
            identity_id=identity_id,
            permissions=permissions,
            site_id=principal.site_id,
            room_id=principal.room_id,
            at=issued_at,
        )
        get_repository().record_fabric_audit(
            actor_id=principal.identity_id,
            action="fabric.console.open",
            resource_type="identity",
            resource_id=identity_id,
            outcome="succeeded",
            correlation_id=None,
            occurred_at=issued_at,
            details={"actorType": "instructor", "singleUse": True},
        )
        return {
            "ticket": ticket,
            "expiresAt": ticket_expires_at,
            "singleUse": True,
        }

    @app.post("/api/v1/fabric/auth/console-tickets/redeem")
    async def redeem_console_ticket(
        request: RedeemConsoleTicketRequest,
    ) -> dict[str, object]:
        redeemed_at = current_time()
        grant = get_auth().redeem_console_ticket(request.ticket, at=redeemed_at)
        record, credential = get_auth().issue(
            identity_id=grant.identity_id,
            actor_type="instructor",
            roles=("instructor",),
            permissions=grant.permissions,
            site_id=grant.site_id,
            room_id=grant.room_id,
            session_id=None,
            ttl=timedelta(hours=12),
            at=redeemed_at,
        )
        get_repository().record_fabric_audit(
            actor_id=grant.identity_id,
            action="fabric.console.connect",
            resource_type="identity",
            resource_id=grant.identity_id,
            outcome="succeeded",
            correlation_id=None,
            occurred_at=redeemed_at,
            details={"singleUse": True},
        )
        return {
            "accessToken": credential,
            "expiresAt": record.expires_at,
        }

    @app.post(
        "/api/v1/fabric/auth/identities",
        status_code=201,
        response_model=None,
    )
    async def issue_identity(
        request: IssueIdentityRequest,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.auth.issue")),
        ],
    ) -> dict[str, object] | JSONResponse:
        requested_permissions = tuple(request.permissions)
        if len(requested_permissions) != len(set(requested_permissions)):
            return _fabric_error(422, "INVALID_IDENTITY", "Permissions must be unique")
        if set(requested_permissions) - principal.permissions:
            raise FabricAuthorizationError("An issuer cannot grant permissions it does not hold")
        if len(request.roles) != len(set(request.roles)):
            return _fabric_error(422, "INVALID_IDENTITY", "Roles must be unique")
        record, token = get_auth().issue(
            identity_id=request.identityId,
            actor_type=request.actorType,
            roles=tuple(request.roles),
            permissions=requested_permissions,
            site_id=request.siteId,
            room_id=request.roomId,
            session_id=request.sessionId,
            ttl=timedelta(seconds=request.ttlSeconds),
            at=current_time(),
        )
        get_repository().record_fabric_audit(
            actor_id=principal.identity_id,
            action="fabric.auth.issue",
            resource_type="identity",
            resource_id=record.identity_id,
            outcome="succeeded",
            correlation_id=None,
            occurred_at=current_time(),
            details={"actorType": record.actor_type},
        )
        return {
            "identity": _identity_wire(record),
            "token": token,
            "tokenDisplayedOnce": True,
        }

    @app.delete("/api/v1/fabric/auth/identities/{identity_id}")
    async def revoke_identity(
        identity_id: str,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.auth.revoke")),
        ],
    ) -> dict[str, object]:
        if identity_id == principal.identity_id:
            raise FabricConflictError(
                "SELF_REVOCATION_DENIED",
                "Use a second administrator identity to revoke this credential",
            )
        revoked = get_auth().revoke(identity_id, at=current_time())
        if not revoked:
            raise FabricNotFoundError("IDENTITY_NOT_FOUND", "Identity was not active")
        get_repository().record_fabric_audit(
            actor_id=principal.identity_id,
            action="fabric.auth.revoke",
            resource_type="identity",
            resource_id=identity_id,
            outcome="succeeded",
            correlation_id=None,
            occurred_at=current_time(),
        )
        return {"identityId": identity_id, "revoked": True}

    @app.get("/api/v1/fabric/plugins", response_model=list[PluginManifest])
    async def plugins(
        _principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.nodes.read")),
        ],
    ) -> list[PluginManifest]:
        return list(get_repository().list_fabric_plugins())

    @app.get(
        "/api/v1/fabric/installation",
        response_model=FabricInstallationInfo,
        response_model_exclude_none=True,
    )
    async def installation_info(
        _principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.installation.read")),
        ],
    ) -> FabricInstallationInfo:
        return installation_catalog.info

    @app.get("/api/v1/fabric/installation/artifacts/{artifact_id}")
    async def download_installation_artifact(
        artifact_id: str,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.installation.read")),
        ],
    ) -> FileResponse:
        selected = installation_catalog.artifact(artifact_id)
        if selected is None:
            raise FabricNotFoundError(
                "INSTALLATION_ARTIFACT_NOT_FOUND",
                "The requested installation package is not available",
            )
        artifact, artifact_path = selected
        _audit(
            get_repository(),
            principal,
            action="fabric.installation.download",
            resource_type="installation_artifact",
            resource_id=artifact.artifactId,
            at=current_time(),
            details={
                "fileName": artifact.fileName,
                "sizeBytes": artifact.sizeBytes,
                "sha256": artifact.sha256,
            },
        )
        return FileResponse(
            artifact_path,
            media_type=artifact.mediaType,
            filename=artifact.fileName,
            headers={"X-CIT-SHA256": artifact.sha256},
        )

    @app.get("/api/v1/fabric/nodes", response_model=list[IntegrationNode])
    async def nodes(
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.nodes.read")),
        ],
        site_id: Annotated[str | None, Query(alias="siteId")] = None,
        room_id: Annotated[str | None, Query(alias="roomId")] = None,
        capability: str | None = None,
    ) -> list[IntegrationNode]:
        selected_site = site_id or principal.site_id
        selected_room = room_id or principal.room_id
        get_auth().require(
            principal,
            "fabric.nodes.read",
            site_id=selected_site,
            room_id=selected_room,
        )
        return list(
            get_fabric().list_nodes(
                site_id=selected_site,
                room_id=selected_room,
                capability=capability,
            )
        )

    def visible_nodes(principal: FabricPrincipal) -> tuple[IntegrationNode, ...]:
        return get_fabric().list_nodes(
            site_id=principal.site_id,
            room_id=principal.room_id,
        )

    def remember_connection_action(
        action_id: str,
        principal: FabricPrincipal,
        *,
        at: datetime | None = None,
    ) -> None:
        policy = remembered_connection_policy(action_id)
        if policy is None:
            return
        report = get_discovery().current(visible_nodes(principal))
        get_repository().remember_fabric_connection(
            host_id=report.hostId,
            reconnect_action_id=policy.action_id,
            requires_grounded_confirmation=policy.requires_grounded_confirmation,
            remembered_at=at or current_time(),
            remembered_by=principal.identity_id,
        )

    def remembered_connections_for(
        principal: FabricPrincipal,
    ) -> FabricRememberedConnections:
        nodes = visible_nodes(principal)
        report = get_discovery().current(nodes)
        records = get_repository().list_fabric_remembered_connections(host_id=report.hostId)
        known_actions = {record.reconnect_action_id for record in records}
        added = False
        for policy, last_seen_at in remembered_connection_policies_for_nodes(nodes):
            if policy.action_id in known_actions:
                continue
            get_repository().remember_fabric_connection(
                host_id=report.hostId,
                reconnect_action_id=policy.action_id,
                requires_grounded_confirmation=policy.requires_grounded_confirmation,
                remembered_at=last_seen_at,
                remembered_by="runtime-node-history",
            )
            added = True
        if added:
            records = get_repository().list_fabric_remembered_connections(host_id=report.hostId)
        return FabricRememberedConnections(
            hostId=report.hostId,
            connections=[
                FabricRememberedConnection(
                    actionId=record.reconnect_action_id,
                    requiresGroundedConfirmation=(record.requires_grounded_confirmation),
                    rememberedAt=record.remembered_at,
                )
                for record in records
                if remembered_connection_policy(record.reconnect_action_id) is not None
            ],
        )

    @app.get(
        "/api/v1/fabric/discovery",
        response_model=FabricDiscoveryReport,
        response_model_exclude_none=True,
    )
    async def discovery_status(
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.nodes.read")),
        ],
    ) -> FabricDiscoveryReport:
        return get_discovery().current(visible_nodes(principal))

    @app.post(
        "/api/v1/fabric/discovery/scan",
        response_model=FabricDiscoveryReport,
        response_model_exclude_none=True,
    )
    async def scan_devices(
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.nodes.read")),
        ],
    ) -> FabricDiscoveryReport:
        report = await get_discovery().scan(visible_nodes(principal))
        _audit(
            get_repository(),
            principal,
            action="fabric.discovery.scan",
            resource_type="host",
            resource_id=report.hostId,
            at=current_time(),
            outcome="succeeded",
            details={
                "scanId": report.scanId,
                "integrationCount": len(report.integrations),
            },
        )
        return report

    @app.get(
        "/api/v1/fabric/discovery/remembered",
        response_model=FabricRememberedConnections,
        response_model_exclude_none=True,
    )
    async def remembered_connections(
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.nodes.read")),
        ],
    ) -> FabricRememberedConnections:
        return remembered_connections_for(principal)

    @app.post(
        "/api/v1/fabric/discovery/remembered/connect",
        response_model=FabricRememberedConnectionResult,
        response_model_exclude_none=True,
    )
    async def reconnect_remembered_connections(
        request: DiscoveryActionRequest,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.discovery.connect")),
        ],
    ) -> FabricRememberedConnectionResult:
        remembered = remembered_connections_for(principal)
        result = await get_discovery().reconnect_remembered(
            remembered.connections,
            confirm_grounded=request.confirmGrounded,
            nodes=lambda: visible_nodes(principal),
        )
        _audit(
            get_repository(),
            principal,
            action="fabric.discovery.reconnect_remembered",
            resource_type="host",
            resource_id=remembered.hostId,
            at=current_time(),
            outcome="failed" if result.failedCount else "succeeded",
            details={
                "rememberedCount": len(remembered.connections),
                "connectedCount": result.connectedCount,
                "alreadyConnectedCount": result.alreadyConnectedCount,
                "skippedCount": result.skippedCount,
                "failedCount": result.failedCount,
                "groundedConfirmed": request.confirmGrounded,
                "broadScanPerformed": False,
            },
        )
        return result

    @app.post(
        "/api/v1/fabric/discovery/actions/{action_id}",
        response_model=FabricDiscoveryActionResult,
        response_model_exclude_none=True,
    )
    async def run_discovery_action(
        action_id: Annotated[
            str,
            Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=96),
        ],
        request: DiscoveryActionRequest,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.discovery.connect")),
        ],
    ) -> FabricDiscoveryActionResult:
        session_target: FabricDiscoverySessionTarget | None = None
        if request.sessionId is not None:
            allowed_course_packs = SESSION_TARGET_ACTION_COURSE_PACKS.get(action_id)
            if allowed_course_packs is None:
                raise FabricPolicyError(
                    "DISCOVERY_SESSION_TARGET_DENIED",
                    "This connection action cannot be attached to a lesson session",
                )
            session = get_fabric().get_session(request.sessionId)
            get_auth().require(
                principal,
                "fabric.roles.assign",
                site_id=session.siteId,
                room_id=session.roomId,
                session_id=session.sessionId,
            )
            if session.coursePackId not in allowed_course_packs:
                raise FabricPolicyError(
                    "DEVICE_CONTROL_SESSION_INVALID",
                    "Select a compatible device-control lesson",
                )
            if session.mode is not FabricSessionMode.physical:
                raise FabricPolicyError(
                    "PHYSICAL_SESSION_REQUIRED",
                    "Connect physical glasses to a physical lesson",
                )
            session_target = FabricDiscoverySessionTarget(
                sessionId=session.sessionId,
                coursePackId=session.coursePackId,
                siteId=session.siteId,
                roomId=session.roomId,
            )
        try:
            result = await get_discovery().perform(
                action_id,
                confirm_grounded=request.confirmGrounded,
                nodes=lambda: visible_nodes(principal),
                session_target=session_target,
            )
        except FabricDiscoveryError as error:
            _audit(
                get_repository(),
                principal,
                action="fabric.discovery.connect",
                resource_type="integration_action",
                resource_id=action_id,
                at=current_time(),
                outcome="denied",
                details={"code": error.code},
            )
            raise
        _audit(
            get_repository(),
            principal,
            action="fabric.discovery.connect",
            resource_type="integration_action",
            resource_id=action_id,
            at=current_time(),
            outcome="succeeded",
            details={
                "groundedConfirmed": request.confirmGrounded,
                **({"sessionId": request.sessionId} if request.sessionId is not None else {}),
            },
        )
        remember_connection_action(action_id, principal)
        return result

    @app.post(
        "/api/v1/fabric/sphero-bolt/connect",
        response_model=FabricDiscoveryActionResult,
        response_model_exclude_none=True,
    )
    async def connect_sphero_bolt_robots(
        request: SpheroBoltConnectionConfiguration,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.discovery.connect")),
        ],
    ) -> FabricDiscoveryActionResult:
        try:
            result = await get_discovery().connect_sphero_bolts(
                request,
                nodes=lambda: visible_nodes(principal),
            )
        except FabricDiscoveryError as error:
            _audit(
                get_repository(),
                principal,
                action="fabric.sphero_bolt.connect",
                resource_type="integration_action",
                resource_id="cit.sphero-bolt",
                at=current_time(),
                outcome="denied",
                details={"code": error.code},
            )
            raise
        _audit(
            get_repository(),
            principal,
            action="fabric.sphero_bolt.connect",
            resource_type="integration_action",
            resource_id="cit.sphero-bolt",
            at=current_time(),
            outcome="succeeded",
            details={
                "candidateCount": len(request.robots),
                "candidateIds": [robot.candidateId for robot in request.robots],
                "movementCommandIssued": False,
                "aimCommandIssued": False,
            },
        )
        remember_connection_action("cit.sphero-bolt.reconnect", principal)
        return result

    @app.post(
        "/api/v1/fabric/sphero-ollie/connect",
        response_model=FabricDiscoveryActionResult,
        response_model_exclude_none=True,
    )
    async def connect_sphero_ollie_robots(
        request: SpheroOllieConnectionConfiguration,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.discovery.connect")),
        ],
    ) -> FabricDiscoveryActionResult:
        try:
            result = await get_discovery().connect_sphero_ollies(
                request,
                nodes=lambda: visible_nodes(principal),
            )
        except FabricDiscoveryError as error:
            _audit(
                get_repository(),
                principal,
                action="fabric.sphero_ollie.connect",
                resource_type="integration_action",
                resource_id="cit.sphero-ollie",
                at=current_time(),
                outcome="denied",
                details={"code": error.code},
            )
            raise
        _audit(
            get_repository(),
            principal,
            action="fabric.sphero_ollie.connect",
            resource_type="integration_action",
            resource_id="cit.sphero-ollie",
            at=current_time(),
            outcome="succeeded",
            details={
                "candidateCount": len(request.robots),
                "candidateIds": [robot.candidateId for robot in request.robots],
                "movementCommandIssued": False,
                "aimCommandIssued": False,
            },
        )
        remember_connection_action("cit.sphero-ollie.reconnect", principal)
        return result

    @app.post(
        "/api/v1/fabric/wonder-workshop/connect",
        response_model=FabricDiscoveryActionResult,
        response_model_exclude_none=True,
    )
    async def connect_wonder_workshop_robots(
        request: WonderWorkshopConnectionConfiguration,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.discovery.connect")),
        ],
    ) -> FabricDiscoveryActionResult:
        try:
            result = await get_discovery().connect_wonder_workshop(
                request,
                nodes=lambda: visible_nodes(principal),
            )
        except FabricDiscoveryError as error:
            _audit(
                get_repository(),
                principal,
                action="fabric.wonder_workshop.connect",
                resource_type="integration_action",
                resource_id="cit.wonder-workshop",
                at=current_time(),
                outcome="denied",
                details={"code": error.code},
            )
            raise
        _audit(
            get_repository(),
            principal,
            action="fabric.wonder_workshop.connect",
            resource_type="integration_action",
            resource_id="cit.wonder-workshop",
            at=current_time(),
            outcome="succeeded",
            details={
                "candidateCount": len(request.robots),
                "candidateIds": [robot.candidateId for robot in request.robots],
                "movementCommandIssued": False,
            },
        )
        remember_connection_action("cit.wonder-workshop.reconnect", principal)
        return result

    @app.post(
        "/api/v1/fabric/matter/wifi",
        response_model=FabricDiscoveryActionResult,
        response_model_exclude_none=True,
    )
    async def configure_matter_wifi(
        request: MatterWifiConfiguration,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.discovery.connect")),
        ],
    ) -> FabricDiscoveryActionResult:
        try:
            result = await get_discovery().configure_matter_wifi(
                request,
                nodes=lambda: visible_nodes(principal),
            )
        except FabricDiscoveryError as error:
            _audit(
                get_repository(),
                principal,
                action="fabric.matter.configure_wifi",
                resource_type="integration_action",
                resource_id="cit.matter-smart-plug",
                at=current_time(),
                outcome="denied",
                details={"code": error.code},
            )
            raise
        _audit(
            get_repository(),
            principal,
            action="fabric.matter.configure_wifi",
            resource_type="integration_action",
            resource_id="cit.matter-smart-plug",
            at=current_time(),
            outcome="succeeded",
            details={
                "inputRetained": False,
                "vendorAccountUsed": False,
            },
        )
        return result

    @app.post(
        "/api/v1/fabric/matter/commission",
        response_model=FabricDiscoveryActionResult,
        response_model_exclude_none=True,
    )
    async def commission_matter_plug(
        request: MatterCommissioningRequest,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.discovery.connect")),
        ],
    ) -> FabricDiscoveryActionResult:
        try:
            result = await get_discovery().commission_matter(
                request.setupCode.get_secret_value(),
                nodes=lambda: visible_nodes(principal),
            )
        except FabricDiscoveryError as error:
            _audit(
                get_repository(),
                principal,
                action="fabric.matter.commission",
                resource_type="integration_action",
                resource_id="cit.matter-smart-plug",
                at=current_time(),
                outcome="denied",
                details={"code": error.code},
            )
            raise
        _audit(
            get_repository(),
            principal,
            action="fabric.matter.commission",
            resource_type="integration_action",
            resource_id="cit.matter-smart-plug",
            at=current_time(),
            outcome="succeeded",
            details={"inputRetained": False, "vendorAccountUsed": False},
        )
        remember_connection_action("cit.matter-smart-plug.connect", principal)
        return result

    @app.post(
        "/api/v1/fabric/lego/connect",
        response_model=FabricDiscoveryActionResult,
        response_model_exclude_none=True,
    )
    async def connect_lego_hub(
        request: LegoConnectionConfiguration,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.discovery.connect")),
        ],
    ) -> FabricDiscoveryActionResult:
        try:
            result = await get_discovery().connect_lego(
                request,
                nodes=lambda: visible_nodes(principal),
            )
        except FabricDiscoveryError as error:
            _audit(
                get_repository(),
                principal,
                action="fabric.lego.connect",
                resource_type="integration_action",
                resource_id="cit.lego-pybricks",
                at=current_time(),
                outcome="denied",
                details={"code": error.code},
            )
            raise
        _audit(
            get_repository(),
            principal,
            action="fabric.lego.connect",
            resource_type="integration_action",
            resource_id="cit.lego-pybricks",
            at=current_time(),
            outcome="succeeded",
            details={
                "hubModel": request.hubModel,
                "configuredPortCount": len(request.ports),
                "motorCommandIssued": False,
            },
        )
        remember_connection_action("cit.lego-pybricks.connect", principal)
        return result

    @app.get(
        "/api/v1/fabric/course-packs",
        response_model=list[CoursePack],
        response_model_exclude_none=True,
    )
    async def course_packs(
        _principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.course.read")),
        ],
    ) -> list[CoursePack]:
        return list(get_fabric().list_course_packs())

    @app.post(
        "/api/v1/fabric/course-packs",
        response_model=CoursePack,
        response_model_exclude_none=True,
        status_code=201,
    )
    async def install_course_pack(
        course_pack: CoursePack,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.course.manage")),
        ],
    ) -> CoursePack:
        installed = get_fabric().install_course_pack(
            course_pack,
            actor_id=principal.identity_id,
        )
        _audit(
            get_repository(),
            principal,
            action="fabric.course.install",
            resource_type="course_pack",
            resource_id=f"{installed.coursePackId}@{installed.version}",
            at=current_time(),
        )
        return installed

    @app.post(
        "/api/v1/fabric/sessions",
        response_model=InteractionSession,
        response_model_exclude_none=True,
        status_code=201,
    )
    async def create_session(
        request: CreateInteractionSessionRequest,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.sessions.manage")),
        ],
    ) -> InteractionSession:
        get_auth().require(
            principal,
            "fabric.sessions.manage",
            site_id=request.siteId,
            room_id=request.roomId,
        )
        session = get_fabric().create_session(request, actor_id=principal.identity_id)
        _audit(
            get_repository(),
            principal,
            action="fabric.session.create",
            resource_type="session",
            resource_id=session.sessionId,
            at=current_time(),
        )
        return session

    @app.post(
        "/api/v1/fabric/monitoring/session",
        response_model=InteractionSession,
        response_model_exclude_none=True,
    )
    async def ensure_monitoring_session(
        request: EnsureMonitoringSessionRequest,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.sessions.manage")),
        ],
    ) -> InteractionSession:
        """Reuse one unarmed monitoring session across independent adapters."""

        get_auth().require(
            principal,
            "fabric.sessions.manage",
            site_id=request.siteId,
            room_id=request.roomId,
        )
        session, reused = get_fabric().ensure_monitoring_session(
            device_monitoring_course_pack(),
            site_id=request.siteId,
            room_id=request.roomId,
            mode=FabricSessionMode(request.mode),
            actor_id=principal.identity_id,
        )
        _audit(
            get_repository(),
            principal,
            action="fabric.monitoring_session.ensure",
            resource_type="session",
            resource_id=session.sessionId,
            at=current_time(),
            details={"reused": reused},
        )
        return session

    @app.get(
        "/api/v1/fabric/sessions",
        response_model=list[InteractionSession],
        response_model_exclude_none=True,
    )
    async def sessions(
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.sessions.read")),
        ],
    ) -> list[InteractionSession]:
        return [
            session
            for session in get_fabric().list_sessions()
            if principal.permits(
                "fabric.sessions.read",
                site_id=session.siteId,
                room_id=session.roomId,
                session_id=session.sessionId,
            )
        ]

    @app.get(
        "/api/v1/fabric/sessions/{session_id}",
        response_model=InteractionSession,
        response_model_exclude_none=True,
    )
    async def get_session(
        session_id: str,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.sessions.read")),
        ],
    ) -> InteractionSession:
        session = get_fabric().get_session(session_id)
        get_auth().require(
            principal,
            "fabric.sessions.read",
            site_id=session.siteId,
            room_id=session.roomId,
            session_id=session.sessionId,
        )
        return session

    @app.get(
        "/api/v1/fabric/sessions/{session_id}/start-policy",
        response_model=SessionStartPolicyResponse,
    )
    async def get_session_start_policy(
        session_id: str,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.sessions.read")),
        ],
    ) -> SessionStartPolicyResponse:
        session = get_fabric().get_session(session_id)
        get_auth().require(
            principal,
            "fabric.sessions.read",
            site_id=session.siteId,
            room_id=session.roomId,
            session_id=session.sessionId,
        )
        can_start_unarmed = get_fabric().can_start_unarmed(session_id)
        return SessionStartPolicyResponse(
            sessionId=session.sessionId,
            requiresArming=not can_start_unarmed,
        )

    @app.put(
        "/api/v1/fabric/sessions/{session_id}/roles/{role}",
        response_model=InteractionSession,
        response_model_exclude_none=True,
    )
    async def assign_role(
        session_id: str,
        role: str,
        request: AssignRoleRequest,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.roles.assign")),
        ],
    ) -> InteractionSession:
        current = get_fabric().get_session(session_id)
        get_auth().require(
            principal,
            "fabric.roles.assign",
            site_id=current.siteId,
            room_id=current.roomId,
            session_id=current.sessionId,
        )
        session = get_fabric().assign_role(
            session_id,
            role,
            request.nodeId,
            actor_id=principal.identity_id,
        )
        _audit(
            get_repository(),
            principal,
            action="fabric.role.assign",
            resource_type="session_role",
            resource_id=f"{session_id}:{role}",
            at=current_time(),
            details={"nodeId": request.nodeId},
        )
        return session

    for action in ("arm", "disarm", "start", "pause", "stop"):
        _install_session_action(
            app,
            action=action,
            get_fabric=get_fabric,
            get_auth=get_auth,
            get_repository=get_repository,
            current_time=current_time,
            require=require,
        )

    @app.post("/api/v1/fabric/events", status_code=202)
    async def publish_event(
        event: FabricEventEnvelope,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.events.publish")),
        ],
    ) -> dict[str, object]:
        get_auth().require(
            principal,
            "fabric.events.publish",
            site_id=event.siteId,
            room_id=event.roomId,
            session_id=event.sessionId,
        )
        result = await get_fabric().ingest_event(event)
        _audit(
            get_repository(),
            principal,
            action="fabric.event.publish",
            resource_type="event",
            resource_id=str(event.messageId),
            at=current_time(),
            correlation_id=event.correlationId,
            details={"duplicate": result.duplicate, "topic": event.topic},
        )
        return {
            "status": "duplicate" if result.duplicate else "accepted",
            "streamSequence": (
                result.stored_event.stream_sequence if result.stored_event is not None else None
            ),
            "commandLifecycle": [to_wire(item) for item in result.command_lifecycle],
        }

    @app.get("/api/v1/fabric/events")
    async def list_events(
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.events.read")),
        ],
        session_id: Annotated[str | None, Query(alias="sessionId")] = None,
        after_sequence: Annotated[int, Query(alias="afterSequence", ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=FABRIC_PAGE_LIMIT)] = FABRIC_PAGE_LIMIT,
        latest: Annotated[bool, Query()] = False,
    ) -> list[dict[str, object]]:
        if session_id is not None:
            session = get_fabric().get_session(session_id)
            get_auth().require(
                principal,
                "fabric.events.read",
                site_id=session.siteId,
                room_id=session.roomId,
                session_id=session.sessionId,
            )
        elif _principal_is_scoped(principal):
            raise FabricAuthorizationError(
                "A scoped identity must select one exact session event stream"
            )
        return [
            {"streamSequence": item.stream_sequence, "event": to_wire(item.event)}
            for item in get_fabric().list_events(
                session_id=session_id,
                after_sequence=after_sequence,
                limit=limit,
                latest=latest,
            )
        ]

    @app.post("/api/v1/fabric/commands", status_code=202)
    async def submit_command(
        command: FabricCommandRequest,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.commands.submit")),
        ],
    ) -> dict[str, object]:
        session = get_fabric().get_session(command.sessionId)
        get_auth().require(
            principal,
            "fabric.commands.submit",
            site_id=session.siteId,
            room_id=session.roomId,
            session_id=session.sessionId,
        )
        _authorize_priority(principal, command.priority)
        lifecycle = await get_fabric().submit_command(command)
        _audit(
            get_repository(),
            principal,
            action="fabric.command.submit",
            resource_type="command_request",
            resource_id=str(command.messageId),
            at=current_time(),
            correlation_id=command.correlationId,
            details={"action": command.action, "targetRole": command.target.role},
        )
        return {"lifecycle": [to_wire(item) for item in lifecycle]}

    @app.get("/api/v1/fabric/commands/lifecycle")
    async def list_command_lifecycle(
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.commands.read")),
        ],
        command_id: Annotated[str | None, Query(alias="commandId")] = None,
        after_sequence: Annotated[int, Query(alias="afterSequence", ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=FABRIC_PAGE_LIMIT)] = FABRIC_PAGE_LIMIT,
    ) -> list[dict[str, object]]:
        if command_id is not None:
            command = get_repository().get_fabric_command(command_id)
            if command is None:
                raise FabricNotFoundError("COMMAND_NOT_FOUND", "Fabric command was not found")
            session = get_fabric().get_session(command.sessionId)
            get_auth().require(
                principal,
                "fabric.commands.read",
                site_id=session.siteId,
                room_id=session.roomId,
                session_id=session.sessionId,
            )
        elif _principal_is_scoped(principal):
            raise FabricAuthorizationError(
                "A scoped identity must select one exact command lifecycle"
            )
        return [
            {
                "streamSequence": item.stream_sequence,
                "lifecycle": to_wire(item.lifecycle),
            }
            for item in get_fabric().list_lifecycle(
                command_id=command_id,
                after_sequence=after_sequence,
                limit=limit,
            )
        ]

    @app.post("/api/v1/fabric/safety/stop-all")
    async def fabric_stop_all(
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.stop_all")),
        ],
    ) -> dict[str, object]:
        result = await stop_all()
        _audit(
            get_repository(),
            principal,
            action="fabric.safety.stop_all",
            resource_type="runtime",
            resource_id="local",
            at=current_time(),
            details={"status": result.get("status", "unknown")},
        )
        return result

    @app.get("/api/v1/fabric/audit")
    async def audit_records(
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.audit.read")),
        ],
        limit: Annotated[int, Query(ge=1, le=FABRIC_PAGE_LIMIT)] = FABRIC_PAGE_LIMIT,
    ) -> list[dict[str, object]]:
        if _principal_is_scoped(principal):
            raise FabricAuthorizationError(
                "Scoped audit projections require a future site-aware query"
            )
        return [
            {
                "auditId": record.audit_id,
                "actorId": record.actor_id,
                "action": record.action,
                "resourceType": record.resource_type,
                "resourceId": record.resource_id,
                "outcome": record.outcome,
                "correlationId": record.correlation_id,
                "occurredAt": record.occurred_at.isoformat(),
                "details": record.details,
            }
            for record in get_repository().list_fabric_audit(limit=limit)
        ]

    @app.websocket("/api/v1/adapters/connect")
    async def adapter_connection(websocket: WebSocket) -> None:
        await get_connections().run(websocket, allowed_origins=allowed_origins)

    @app.websocket("/api/v1/fabric/events/ws")
    async def fabric_event_stream(websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin")
        if origin is not None and origin not in allowed_origins:
            await websocket.close(code=4403, reason="WebSocket origin is not allowed")
            return
        await websocket.accept()
        try:
            async with asyncio.timeout(5.0):
                raw = await websocket.receive_text()
            if len(raw.encode("utf-8")) > 4096:
                raise ValueError("Authentication frame is too large")
            authentication = FabricStreamAuthentication.model_validate_json(raw)
            principal = get_auth().authenticate(authentication.token, at=current_time())
            get_auth().require(
                principal,
                "fabric.events.read",
            )
            if authentication.sessionId is not None:
                session = get_fabric().get_session(authentication.sessionId)
                get_auth().require(
                    principal,
                    "fabric.events.read",
                    site_id=session.siteId,
                    room_id=session.roomId,
                    session_id=session.sessionId,
                )
            elif _principal_is_scoped(principal):
                raise FabricAuthorizationError(
                    "A scoped identity must select one exact session event stream"
                )
            cursor = authentication.afterEventSequence
            while True:
                events = get_fabric().list_events(
                    session_id=authentication.sessionId,
                    after_sequence=cursor,
                    limit=100,
                )
                if events:
                    for item in events:
                        await websocket.send_json(
                            {
                                "type": "fabric.event",
                                "streamSequence": item.stream_sequence,
                                "event": to_wire(item.event),
                            }
                        )
                        cursor = item.stream_sequence
                else:
                    await websocket.send_json({"type": "heartbeat", "eventSequence": cursor})
                await asyncio.sleep(1.0 if events else 5.0)
        except (FabricAuthenticationError, FabricAuthorizationError):
            await websocket.close(code=4401, reason="Fabric authentication failed")
        except (ValueError, json.JSONDecodeError):
            await websocket.close(code=4400, reason="Fabric stream frame is invalid")
        except (TimeoutError, WebSocketDisconnect):
            pass


def _install_session_action(
    app: FastAPI,
    *,
    action: str,
    get_fabric: FabricGetter,
    get_auth: AuthGetter,
    get_repository: RepositoryGetter,
    current_time: Callable[[], datetime],
    require: Callable[[str], Callable[..., Awaitable[FabricPrincipal]]],
) -> None:
    async def session_action(
        session_id: str,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.sessions.manage")),
        ],
    ) -> InteractionSession:
        current = get_fabric().get_session(session_id)
        get_auth().require(
            principal,
            "fabric.sessions.manage",
            site_id=current.siteId,
            room_id=current.roomId,
            session_id=current.sessionId,
        )
        updated = get_fabric().transition_session(
            session_id,
            action,
            actor_id=principal.identity_id,
        )
        _audit(
            get_repository(),
            principal,
            action=f"fabric.session.{action}",
            resource_type="session",
            resource_id=session_id,
            at=current_time(),
        )
        return updated

    app.add_api_route(
        f"/api/v1/fabric/sessions/{{session_id}}/{action}",
        session_action,
        methods=["POST"],
        response_model=InteractionSession,
        response_model_exclude_none=True,
        name=f"fabric_session_{action}",
    )


def _authorize_priority(
    principal: FabricPrincipal,
    priority: FabricCommandPriority,
) -> None:
    roles = set(principal.roles)
    if priority in {
        FabricCommandPriority.emergency_stop,
        FabricCommandPriority.safety_engine,
    }:
        raise FabricAuthorizationError(
            "Emergency and safety-engine priorities are available only through dedicated controls"
        )
    if priority is FabricCommandPriority.instructor_override and not roles.intersection(
        {"administrator", "instructor"}
    ):
        raise FabricAuthorizationError("Instructor priority requires an instructor role")
    if priority is FabricCommandPriority.lesson_automation and not roles.intersection(
        {"administrator", "instructor", "teaching_assistant"}
    ):
        raise FabricAuthorizationError("Lesson automation requires course authority")
    if priority is FabricCommandPriority.autonomous_agent and not roles.intersection(
        {"administrator", "automated_agent"}
    ):
        raise FabricAuthorizationError("Autonomous-agent priority requires an agent role")


def _audit(
    repository: SQLiteFabricRepository,
    principal: FabricPrincipal,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None,
    at: datetime,
    outcome: str = "succeeded",
    correlation_id: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    repository.record_fabric_audit(
        actor_id=principal.identity_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        correlation_id=correlation_id,
        occurred_at=at,
        details=details,
    )


def _fabric_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "correlationId": str(uuid4()),
        },
        headers={"Cache-Control": "no-store"},
    )


def _principal_wire(principal: FabricPrincipal) -> dict[str, object]:
    return {
        "identityId": principal.identity_id,
        "actorType": principal.actor_type,
        "roles": list(principal.roles),
        "permissions": sorted(principal.permissions),
        "siteId": principal.site_id,
        "roomId": principal.room_id,
        "sessionId": principal.session_id,
        "expiresAt": principal.expires_at.isoformat(),
    }


def _principal_is_scoped(principal: FabricPrincipal) -> bool:
    return any(
        value is not None for value in (principal.site_id, principal.room_id, principal.session_id)
    )


def _identity_wire(record: FabricIdentityRecord) -> dict[str, object]:
    return {
        "identityId": record.identity_id,
        "actorType": record.actor_type,
        "roles": list(record.roles),
        "permissions": list(record.permissions),
        "siteId": record.site_id,
        "roomId": record.room_id,
        "sessionId": record.session_id,
        "createdAt": record.created_at.isoformat(),
        "expiresAt": record.expires_at.isoformat(),
        "revokedAt": None,
    }
