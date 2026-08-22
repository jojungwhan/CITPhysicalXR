"""Authenticated HTTP routes for the local, ephemeral Fabric media plane."""

import asyncio
import hashlib
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .fabric_auth import (
    FabricAuthenticationError,
    FabricAuthService,
    FabricPrincipal,
)
from .fabric_media import (
    FabricMediaError,
    FabricMediaRegistry,
    MediaSourceRegistration,
    VisionDetector,
    analysis_wire,
)
from .fabric_repository import SQLiteFabricRepository

AuthGetter = Callable[[], FabricAuthService]
RepositoryGetter = Callable[[], SQLiteFabricRepository]

_PAIRING_TTL = timedelta(minutes=5)
_PUBLISHER_TTL = timedelta(days=7)
_MAX_PENDING_PAIRINGS = 16


@dataclass(frozen=True, slots=True)
class _MediaPairing:
    pairing_id: str
    code_digest: str
    site_id: str
    room_id: str
    created_by: str
    expires_at: datetime


class MediaSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sourceId: Annotated[str, Field(min_length=3, max_length=64)]
    displayName: Annotated[str, Field(min_length=1, max_length=100)]
    kind: Literal["meta_glasses", "robomaster", "tello", "usb_camera", "simulator"]
    captureMode: Literal["video", "snapshot"]
    siteId: Annotated[str, Field(min_length=1, max_length=100)]
    roomId: Annotated[str, Field(min_length=1, max_length=100)]
    nodeId: Annotated[str | None, Field(min_length=1, max_length=128)] = None


class CreateMediaPairingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    siteId: Annotated[str, Field(min_length=1, max_length=100)]
    roomId: Annotated[str, Field(min_length=1, max_length=100)]


class RedeemMediaPairingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pairingCode: Annotated[str, Field(min_length=20, max_length=64)]


def install_fabric_media_api(
    app: FastAPI,
    *,
    registry: FabricMediaRegistry,
    detector: VisionDetector,
    get_auth: AuthGetter,
    get_repository: RepositoryGetter,
    clock: Callable[[], datetime],
    media_ingress_origin: str | None = None,
) -> None:
    pairing_lock = asyncio.Lock()
    pending_pairings: dict[str, _MediaPairing] = {}

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

    def audit_pairing(
        pairing: _MediaPairing,
        *,
        action: str,
        actor_id: str,
        at: datetime,
    ) -> None:
        get_repository().record_fabric_audit(
            actor_id=actor_id,
            action=action,
            resource_type="media_pairing",
            resource_id=pairing.pairing_id,
            outcome="succeeded",
            correlation_id=None,
            occurred_at=at,
            details={"siteId": pairing.site_id, "roomId": pairing.room_id},
        )

    @app.exception_handler(FabricMediaError)
    async def media_error_handler(
        _request: Request,
        error: FabricMediaError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"code": error.code, "message": error.message},
        )

    @app.post("/api/v1/fabric/media/pairings", status_code=201)
    async def create_media_pairing(
        request: CreateMediaPairingRequest,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.media.manage")),
        ],
    ) -> dict[str, object]:
        if media_ingress_origin is None:
            raise FabricMediaError(
                "MEDIA_LAN_INGRESS_DISABLED",
                "Restart Classroom Control with local-network camera access enabled",
                status_code=409,
            )
        get_auth().require(
            principal,
            "fabric.media.manage",
            site_id=request.siteId,
            room_id=request.roomId,
        )
        issued_at = clock()
        code = secrets.token_urlsafe(18)
        pairing = _MediaPairing(
            pairing_id=f"media-pairing-{uuid4().hex}",
            code_digest=hashlib.sha256(code.encode("utf-8")).hexdigest(),
            site_id=request.siteId,
            room_id=request.roomId,
            created_by=principal.identity_id,
            expires_at=issued_at + _PAIRING_TTL,
        )
        async with pairing_lock:
            expired = [
                digest
                for digest, existing in pending_pairings.items()
                if existing.expires_at <= issued_at
            ]
            for digest in expired:
                del pending_pairings[digest]
            if len(pending_pairings) >= _MAX_PENDING_PAIRINGS:
                oldest = min(
                    pending_pairings,
                    key=lambda digest: pending_pairings[digest].expires_at,
                )
                del pending_pairings[oldest]
            pending_pairings[pairing.code_digest] = pairing
        audit_pairing(
            pairing,
            action="fabric.media.pairing.create",
            actor_id=principal.identity_id,
            at=issued_at,
        )
        return {
            "pairingId": pairing.pairing_id,
            "pairingCode": code,
            "expiresAt": pairing.expires_at,
            "fabricOrigin": media_ingress_origin,
            "siteId": pairing.site_id,
            "roomId": pairing.room_id,
            "singleUse": True,
        }

    @app.post("/api/v1/fabric/media/pairings/redeem")
    async def redeem_media_pairing(
        request: RedeemMediaPairingRequest,
    ) -> dict[str, object]:
        if media_ingress_origin is None:
            raise FabricMediaError(
                "MEDIA_LAN_INGRESS_DISABLED",
                "Local-network camera access is disabled",
                status_code=409,
            )
        redeemed_at = clock()
        digest = hashlib.sha256(request.pairingCode.encode("utf-8")).hexdigest()
        async with pairing_lock:
            pairing = pending_pairings.pop(digest, None)
        if pairing is None or pairing.expires_at <= redeemed_at:
            raise FabricMediaError(
                "MEDIA_PAIRING_INVALID",
                "The camera pairing code is invalid, expired, or already used",
                status_code=401,
            )
        identity_id = f"meta-camera-{uuid4().hex[:16]}"
        record, credential = get_auth().issue(
            identity_id=identity_id,
            actor_type="adapter",
            roles=("media_publisher",),
            permissions=("fabric.media.publish",),
            site_id=pairing.site_id,
            room_id=pairing.room_id,
            session_id=None,
            ttl=_PUBLISHER_TTL,
            at=redeemed_at,
        )
        audit_pairing(
            pairing,
            action="fabric.media.pairing.redeem",
            actor_id=identity_id,
            at=redeemed_at,
        )
        return {
            "publisherId": identity_id,
            "accessToken": credential,
            "expiresAt": record.expires_at,
            "fabricOrigin": media_ingress_origin,
            "siteId": pairing.site_id,
            "roomId": pairing.room_id,
            "permissions": ["fabric.media.publish"],
        }

    @app.post("/api/v1/fabric/media/sources", status_code=201)
    async def register_media_source(
        request: MediaSourceRequest,
        principal: Annotated[FabricPrincipal, Depends(principal_from_header)],
    ) -> dict[str, object]:
        permission = (
            "fabric.media.publish"
            if principal.permits("fabric.media.publish")
            else "fabric.media.manage"
        )
        get_auth().require(
            principal,
            permission,
            site_id=request.siteId,
            room_id=request.roomId,
        )
        return await registry.register(
            MediaSourceRegistration(
                source_id=request.sourceId,
                display_name=request.displayName.strip(),
                kind=request.kind,
                capture_mode=request.captureMode,
                site_id=request.siteId,
                room_id=request.roomId,
                node_id=request.nodeId,
            ),
            publisher_identity_id=principal.identity_id,
            at=clock(),
        )

    @app.delete("/api/v1/fabric/media/sources/{source_id}", status_code=204)
    async def remove_media_source(
        source_id: str,
        principal: Annotated[FabricPrincipal, Depends(principal_from_header)],
    ) -> Response:
        can_manage = principal.permits("fabric.media.manage")
        if not can_manage:
            get_auth().require(principal, "fabric.media.publish")
        removed = await registry.remove(
            source_id,
            identity_id=principal.identity_id,
            can_manage=can_manage,
        )
        if not removed:
            raise FabricMediaError(
                "MEDIA_SOURCE_NOT_FOUND",
                "The camera source is not registered",
                status_code=404,
            )
        return Response(status_code=204)

    @app.put("/api/v1/fabric/media/sources/{source_id}/frame", status_code=202)
    async def publish_media_frame(
        source_id: str,
        request: Request,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.media.publish")),
        ],
        content_type: Annotated[str | None, Header(alias="Content-Type")] = None,
        captured_at: Annotated[
            datetime | None,
            Header(alias="X-CIT-Captured-At"),
        ] = None,
    ) -> dict[str, object]:
        state = await registry.source(source_id)
        get_auth().require(
            principal,
            "fabric.media.publish",
            site_id=state.registration.site_id,
            room_id=state.registration.room_id,
        )
        data = await request.body()
        frame = await registry.publish_frame(
            source_id,
            data,
            content_type=content_type or "application/octet-stream",
            captured_at=captured_at or clock(),
            publisher_identity_id=principal.identity_id,
            at=clock(),
        )
        return {
            "sourceId": frame.source_id,
            "frameSequence": frame.sequence,
            "receivedAt": frame.received_at.isoformat(),
            "width": frame.width,
            "height": frame.height,
        }

    @app.get("/api/v1/fabric/media/sources")
    async def list_media_sources(
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.media.read")),
        ],
    ) -> list[dict[str, object]]:
        return await registry.list_sources(
            site_id=principal.site_id,
            room_id=principal.room_id,
            at=clock(),
        )

    @app.get("/api/v1/fabric/media/sources/{source_id}/frame")
    async def latest_media_frame(
        source_id: str,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.media.read")),
        ],
        if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    ) -> Response:
        state = await registry.source(source_id)
        get_auth().require(
            principal,
            "fabric.media.read",
            site_id=state.registration.site_id,
            room_id=state.registration.room_id,
        )
        frame = await registry.frame(source_id)
        headers = {
            "Cache-Control": "no-store",
            "ETag": frame.etag,
            "X-CIT-Frame-Sequence": str(frame.sequence),
            "X-CIT-Captured-At": frame.captured_at.isoformat(),
            "X-Content-Type-Options": "nosniff",
        }
        if if_none_match == frame.etag:
            return Response(status_code=304, headers=headers)
        return Response(
            content=frame.data,
            media_type=frame.content_type,
            headers=headers,
        )

    @app.post("/api/v1/fabric/media/sources/{source_id}/analyze")
    async def analyze_media_frame(
        source_id: str,
        principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.vision.analyze")),
        ],
    ) -> dict[str, object]:
        state = await registry.source(source_id)
        get_auth().require(
            principal,
            "fabric.vision.analyze",
            site_id=state.registration.site_id,
            room_id=state.registration.room_id,
        )
        return analysis_wire(await registry.analyze(source_id, detector, at=clock()))

    @app.get("/api/v1/fabric/vision/status")
    async def vision_status(
        _principal: Annotated[
            FabricPrincipal,
            Depends(require("fabric.media.read")),
        ],
    ) -> dict[str, object]:
        return {
            "mode": "local_on_demand",
            "model": detector.name,
            "labels": list(detector.labels),
            "minimumConfidence": detector.minimum_confidence,
            "rawFramesPersisted": False,
            "automaticActuation": False,
        }
