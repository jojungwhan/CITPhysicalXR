"""Wireless Android unlock automation for explicitly selected Matter plugs."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import threading
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from cit_protocol import (
    CreateInteractionSessionRequest,
    FabricCommandLifecycleEvent,
    FabricCommandLifecycleStage,
    FabricCommandPriority,
    FabricCommandRequest,
    FabricNodeConnectionState,
    FabricSessionMode,
    FabricSessionState,
    IntegrationNode,
    InteractionSession,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .fabric import InteractionFabric
from .fabric_camera_ftp import CameraFtpCredentials, derive_camera_ftp_password

_UNLOCK_SIGNING_DOMAIN = "cit-control-tower-unlock-v1"
_TOGGLE_SIGNING_DOMAIN = "cit-control-tower-toggle-v1"
_SIGNATURE = re.compile(r"^[0-9a-fA-F]{64}$")
_NODE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DEVICE_ID = re.compile(r"^android-[a-f0-9]{16}$")
_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
_MAX_CLOCK_SKEW_MS = 120_000
_DEFAULT_COOLDOWN_SECONDS = 15
_SMART_PLUG_ACTION = "power.switch.set"
_SMART_PLUG_COURSE = "smart-plug-control"
_SMART_PLUG_ROLE = re.compile(r"^classroom_plug(?:_[2-8])?$")
_FAILED_COMMAND_STAGES = {
    FabricCommandLifecycleStage.FAILED,
    FabricCommandLifecycleStage.REJECTED,
    FabricCommandLifecycleStage.CANCELLED,
    FabricCommandLifecycleStage.TIMED_OUT,
}


class UnlockAutomationError(RuntimeError):
    """A bounded configuration, authentication, or trigger failure."""

    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class UnlockAutomationCompanion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deviceId: str
    displayName: str
    pairedAt: datetime
    lastSeenAt: datetime | None = None


class UnlockAutomationLastResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["succeeded", "failed", "disabled", "cooldown"]
    occurredAt: datetime
    requestedCount: int = Field(ge=0, le=8)
    acceptedCount: int = Field(ge=0, le=8)
    message: str = Field(min_length=1, max_length=300)


class UnlockAutomationOperations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manage: bool
    installAndPair: bool


class UnlockAutomationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["1.0"] = "1.0"
    enabled: bool
    selectedNodeIds: list[str]
    cooldownSeconds: int
    companion: UnlockAutomationCompanion | None = None
    lastResult: UnlockAutomationLastResult | None = None
    operations: UnlockAutomationOperations


class UnlockAutomationConfigurationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    selectedNodeIds: list[str] = Field(max_length=8)

    @field_validator("selectedNodeIds")
    @classmethod
    def validate_node_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("selectedNodeIds must be unique")
        if any(_NODE_ID.fullmatch(node_id) is None for node_id in value):
            raise ValueError("selectedNodeIds contains an invalid node identity")
        return value


class UnlockAutomationPairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    displayName: str = Field(default="Control Tower phone", min_length=1, max_length=80)

    @field_validator("displayName")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized or any(
            ord(character) < 32 or ord(character) == 127 for character in value
        ):
            raise ValueError("displayName must contain printable text")
        return normalized


class UnlockEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["1.0"] = "1.0"
    deviceId: str
    eventId: UUID
    sequence: int = Field(ge=1, le=9_223_372_036_854_775_807)
    occurredAtEpochMs: int = Field(ge=0, le=9_223_372_036_854_775_807)

    @field_validator("deviceId")
    @classmethod
    def validate_device_id(cls, value: str) -> str:
        if _DEVICE_ID.fullmatch(value) is None:
            raise ValueError("deviceId is invalid")
        return value


class UnlockEventResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["1.0"] = "1.0"
    accepted: bool
    outcome: Literal["succeeded", "failed", "disabled", "cooldown"]
    requestedCount: int = Field(ge=0, le=8)
    acceptedCount: int = Field(ge=0, le=8)
    message: str


class ToggleEventRequest(UnlockEventRequest):
    """One explicit main-screen toggle from the paired Android companion."""


class ToggleEventResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["1.0"] = "1.0"
    accepted: bool
    outcome: Literal["succeeded", "failed"]
    requestedCount: int = Field(ge=0, le=8)
    acceptedCount: int = Field(ge=0, le=8)
    on: bool | None = None
    message: str


class UnlockPowerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requestedCount: int = Field(ge=0, le=8)
    acceptedCount: int = Field(ge=0, le=8)
    failedNodeIds: list[str] = Field(max_length=8)
    on: bool | None = None
    message: str


class _StoredCompanion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deviceId: str
    displayName: str
    secret: str = Field(min_length=43, max_length=128, repr=False)
    pairedAt: datetime
    lastSequence: int = Field(default=0, ge=0)
    lastSeenAt: datetime | None = None


class _StoredUnlockAutomation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["1.0"] = "1.0"
    enabled: bool = False
    selectedNodeIds: list[str] = Field(default_factory=list, max_length=8)
    cooldownSeconds: int = Field(default=_DEFAULT_COOLDOWN_SECONDS, ge=5, le=300)
    companion: _StoredCompanion | None = None
    lastAcceptedAt: datetime | None = None
    lastResult: UnlockAutomationLastResult | None = None


@dataclass(frozen=True, slots=True)
class UnlockPairingCandidate:
    device_id: str
    display_name: str
    paired_at: datetime
    provisioning_uri: str = field(repr=False)
    secret: str = field(repr=False)


UnlockCommandRunner = Callable[[tuple[str, ...], str, str], Awaitable[UnlockPowerResult]]
ToggleCommandRunner = Callable[[tuple[str, ...], str, str], Awaitable[UnlockPowerResult]]


class UnlockAutomationService:
    """Persist one paired phone and accept non-replayable signed unlock events."""

    def __init__(
        self,
        *,
        state_path: str | Path,
        lan_origin: str | None,
        companion_apk_path: str | Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._state_path = Path(state_path).resolve()
        self._lan_origin = _validated_lan_origin(lan_origin)
        self._companion_apk_path = (
            Path(companion_apk_path).resolve() if companion_apk_path is not None else None
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self._state_lock = threading.RLock()
        self._event_lock = asyncio.Lock()
        self._state = self._load()

    @property
    def lan_origin(self) -> str | None:
        return self._lan_origin

    @property
    def companion_apk_path(self) -> Path | None:
        return self._companion_apk_path

    def can_install_and_pair(self) -> bool:
        return (
            self._lan_origin is not None
            and self._companion_apk_path is not None
            and self._companion_apk_path.is_file()
            and self._companion_apk_path.suffix.casefold() == ".apk"
        )

    def has_companion(self) -> bool:
        with self._state_lock:
            return self._state.companion is not None

    def camera_ftp_credentials(self) -> CameraFtpCredentials | None:
        """Return protocol-separated FTP credentials for the paired phone."""

        with self._state_lock:
            companion = self._state.companion
            if companion is None:
                return None
            return CameraFtpCredentials(
                username=companion.deviceId,
                password=derive_camera_ftp_password(companion.secret),
            )

    def snapshot(
        self,
        *,
        can_manage: bool,
        can_install_and_pair: bool,
    ) -> UnlockAutomationSnapshot:
        with self._state_lock:
            companion = self._state.companion
            public_companion = (
                UnlockAutomationCompanion(
                    deviceId=companion.deviceId,
                    displayName=companion.displayName,
                    pairedAt=companion.pairedAt,
                    lastSeenAt=companion.lastSeenAt,
                )
                if companion is not None
                else None
            )
            return UnlockAutomationSnapshot(
                enabled=self._state.enabled,
                selectedNodeIds=list(self._state.selectedNodeIds),
                cooldownSeconds=self._state.cooldownSeconds,
                companion=public_companion,
                lastResult=(
                    self._state.lastResult.model_copy(deep=True)
                    if self._state.lastResult is not None
                    else None
                ),
                operations=UnlockAutomationOperations(
                    manage=can_manage,
                    installAndPair=can_manage and can_install_and_pair,
                ),
            )

    def create_pairing(self, display_name: str) -> UnlockPairingCandidate:
        if self._lan_origin is None:
            raise UnlockAutomationError(
                "UNLOCK_AUTOMATION_LAN_UNAVAILABLE",
                "Enable the Control Tower local-network address before pairing the phone.",
            )
        if self.has_companion():
            raise UnlockAutomationError(
                "UNLOCK_AUTOMATION_PHONE_ALREADY_PAIRED",
                "Unpair the current Android companion before pairing another phone.",
            )
        normalized_name = UnlockAutomationPairRequest(displayName=display_name).displayName
        device_id = f"android-{secrets.token_hex(8)}"
        secret = secrets.token_urlsafe(32)
        paired_at = _aware_utc(self._clock())
        provisioning_payload = (
            base64.urlsafe_b64encode(
                json.dumps(
                    {
                        "origin": self._lan_origin,
                        "deviceId": device_id,
                        "secret": secret,
                        "name": normalized_name,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            .rstrip(b"=")
            .decode("ascii")
        )
        return UnlockPairingCandidate(
            device_id=device_id,
            display_name=normalized_name,
            paired_at=paired_at,
            provisioning_uri=f"cit-control-tower://pair/{provisioning_payload}",
            secret=secret,
        )

    def commit_pairing(self, candidate: UnlockPairingCandidate) -> UnlockAutomationSnapshot:
        with self._state_lock:
            self._state.companion = _StoredCompanion(
                deviceId=candidate.device_id,
                displayName=candidate.display_name,
                secret=candidate.secret,
                pairedAt=candidate.paired_at,
            )
            self._state.enabled = False
            self._state.lastAcceptedAt = None
            self._state.lastResult = None
            self._save()
        return self.snapshot(can_manage=True, can_install_and_pair=self.can_install_and_pair())

    def remove_companion(self) -> UnlockAutomationSnapshot:
        with self._state_lock:
            self._state.enabled = False
            self._state.companion = None
            self._state.lastAcceptedAt = None
            self._state.lastResult = None
            self._save()
        return self.snapshot(can_manage=True, can_install_and_pair=self.can_install_and_pair())

    def configure(
        self,
        request: UnlockAutomationConfigurationRequest,
        *,
        known_node_ids: Iterable[str],
    ) -> UnlockAutomationSnapshot:
        known = frozenset(known_node_ids)
        unknown = [node_id for node_id in request.selectedNodeIds if node_id not in known]
        with self._state_lock:
            preserves_disabled_targets = (
                not request.enabled and request.selectedNodeIds == self._state.selectedNodeIds
            )
            if unknown and not preserves_disabled_targets:
                raise UnlockAutomationError(
                    "UNLOCK_AUTOMATION_NODE_INVALID",
                    "Unlock automation can target only known Matter smart plugs.",
                )
            if request.enabled and self._state.companion is None:
                raise UnlockAutomationError(
                    "UNLOCK_AUTOMATION_PHONE_REQUIRED",
                    "Pair the wireless Android companion before enabling unlock automation.",
                )
            if request.enabled and not request.selectedNodeIds:
                raise UnlockAutomationError(
                    "UNLOCK_AUTOMATION_TARGET_REQUIRED",
                    "Select at least one Matter smart plug before enabling unlock automation.",
                )
            self._state.enabled = request.enabled
            self._state.selectedNodeIds = list(request.selectedNodeIds)
            self._save()
        return self.snapshot(can_manage=True, can_install_and_pair=self.can_install_and_pair())

    async def accept_event(
        self,
        event: UnlockEventRequest,
        signature: str,
        command_runner: UnlockCommandRunner,
    ) -> UnlockEventResult:
        async with self._event_lock:
            now = _aware_utc(self._clock())
            (
                enabled,
                selected_node_ids,
                last_accepted_at,
                cooldown_seconds,
            ) = self._authenticate_and_record_event(
                event,
                signature,
                signing_domain=_UNLOCK_SIGNING_DOMAIN,
                at=now,
            )

            if not enabled:
                return self._finish_event(
                    outcome="disabled",
                    accepted=False,
                    requested_count=len(selected_node_ids),
                    accepted_count=0,
                    message="Unlock automation is disabled in Control Tower.",
                    at=now,
                )
            if (
                last_accepted_at is not None
                and (now - last_accepted_at).total_seconds() < cooldown_seconds
            ):
                return self._finish_event(
                    outcome="cooldown",
                    accepted=False,
                    requested_count=len(selected_node_ids),
                    accepted_count=0,
                    message="A recent unlock event already triggered the configured plugs.",
                    at=now,
                )

            with self._state_lock:
                self._state.lastAcceptedAt = now
                self._save()
            try:
                power = await command_runner(
                    selected_node_ids,
                    event.deviceId,
                    str(event.eventId),
                )
            except Exception:
                return self._finish_event(
                    outcome="failed",
                    accepted=False,
                    requested_count=len(selected_node_ids),
                    accepted_count=0,
                    message="Control Tower could not prepare the configured smart-plug command.",
                    at=now,
                )
            succeeded = power.acceptedCount == power.requestedCount and power.requestedCount > 0
            return self._finish_event(
                outcome="succeeded" if succeeded else "failed",
                accepted=succeeded,
                requested_count=power.requestedCount,
                accepted_count=power.acceptedCount,
                message=power.message,
                at=now,
            )

    async def accept_toggle(
        self,
        event: ToggleEventRequest,
        signature: str,
        command_runner: ToggleCommandRunner,
    ) -> ToggleEventResult:
        """Authenticate one explicit phone button press and toggle the saved plugs."""

        async with self._event_lock:
            now = _aware_utc(self._clock())
            _, selected_node_ids, _, _ = self._authenticate_and_record_event(
                event,
                signature,
                signing_domain=_TOGGLE_SIGNING_DOMAIN,
                at=now,
            )
            if not selected_node_ids:
                return ToggleEventResult(
                    accepted=False,
                    outcome="failed",
                    requestedCount=0,
                    acceptedCount=0,
                    message="No Matter smart plugs are saved for phone control.",
                )
            try:
                power = await command_runner(
                    selected_node_ids,
                    event.deviceId,
                    str(event.eventId),
                )
            except Exception:
                return ToggleEventResult(
                    accepted=False,
                    outcome="failed",
                    requestedCount=len(selected_node_ids),
                    acceptedCount=0,
                    message="Control Tower could not prepare the smart-plug toggle.",
                )
            succeeded = power.acceptedCount == power.requestedCount and power.requestedCount > 0
            return ToggleEventResult(
                accepted=succeeded,
                outcome="succeeded" if succeeded else "failed",
                requestedCount=power.requestedCount,
                acceptedCount=power.acceptedCount,
                on=power.on if succeeded else None,
                message=power.message,
            )

    def _authenticate_and_record_event(
        self,
        event: UnlockEventRequest,
        signature: str,
        *,
        signing_domain: str,
        at: datetime,
    ) -> tuple[bool, tuple[str, ...], datetime | None, int]:
        with self._state_lock:
            companion = self._state.companion
            if companion is None or companion.deviceId != event.deviceId:
                raise UnlockAutomationError(
                    "UNLOCK_AUTOMATION_DEVICE_DENIED",
                    "This phone is not paired for Control Tower automation.",
                    status_code=401,
                )
            if not _valid_signature(
                event,
                signature,
                companion.secret,
                signing_domain=signing_domain,
            ):
                raise UnlockAutomationError(
                    "UNLOCK_AUTOMATION_SIGNATURE_INVALID",
                    "The phone event signature is invalid.",
                    status_code=401,
                )
            event_skew_ms = abs(int(at.timestamp() * 1000) - event.occurredAtEpochMs)
            if event_skew_ms > _MAX_CLOCK_SKEW_MS:
                raise UnlockAutomationError(
                    "UNLOCK_AUTOMATION_EVENT_STALE",
                    "The phone event is outside the accepted time window.",
                )
            if event.sequence <= companion.lastSequence:
                raise UnlockAutomationError(
                    "UNLOCK_AUTOMATION_EVENT_REPLAYED",
                    "The phone event was already processed.",
                )
            companion.lastSequence = event.sequence
            companion.lastSeenAt = at
            result = (
                self._state.enabled,
                tuple(self._state.selectedNodeIds),
                self._state.lastAcceptedAt,
                self._state.cooldownSeconds,
            )
            self._save()
            return result

    def _finish_event(
        self,
        *,
        outcome: Literal["succeeded", "failed", "disabled", "cooldown"],
        accepted: bool,
        requested_count: int,
        accepted_count: int,
        message: str,
        at: datetime,
    ) -> UnlockEventResult:
        result = UnlockEventResult(
            accepted=accepted,
            outcome=outcome,
            requestedCount=requested_count,
            acceptedCount=accepted_count,
            message=message,
        )
        with self._state_lock:
            self._state.lastResult = UnlockAutomationLastResult(
                outcome=outcome,
                occurredAt=at,
                requestedCount=requested_count,
                acceptedCount=accepted_count,
                message=message,
            )
            self._save()
        return result

    def _load(self) -> _StoredUnlockAutomation:
        if not self._state_path.exists():
            return _StoredUnlockAutomation()
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            return _StoredUnlockAutomation.model_validate(raw)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise UnlockAutomationError(
                "UNLOCK_AUTOMATION_STATE_INVALID",
                "The saved unlock-automation configuration is invalid.",
            ) from error

    def _save(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        try:
            temporary_path.write_text(
                self._state.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(self._state_path)
        except OSError as error:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise UnlockAutomationError(
                "UNLOCK_AUTOMATION_SAVE_FAILED",
                "The unlock-automation configuration could not be saved.",
            ) from error


def signed_unlock_payload(event: UnlockEventRequest) -> bytes:
    return _signed_phone_payload(_UNLOCK_SIGNING_DOMAIN, event)


def sign_unlock_event(event: UnlockEventRequest, secret: str) -> str:
    """Build the signature used by the Android client and deterministic tests."""

    return hmac.new(
        secret.encode("ascii"),
        signed_unlock_payload(event),
        hashlib.sha256,
    ).hexdigest()


def signed_toggle_payload(event: ToggleEventRequest) -> bytes:
    return _signed_phone_payload(_TOGGLE_SIGNING_DOMAIN, event)


def sign_toggle_event(event: ToggleEventRequest, secret: str) -> str:
    """Build the domain-separated signature for an explicit phone toggle."""

    return hmac.new(
        secret.encode("ascii"),
        signed_toggle_payload(event),
        hashlib.sha256,
    ).hexdigest()


def _signed_phone_payload(domain: str, event: UnlockEventRequest) -> bytes:
    return (
        f"{domain}\n{event.deviceId}\n{event.eventId}\n{event.sequence}\n{event.occurredAtEpochMs}"
    ).encode("ascii")


def known_smart_plug_node_ids(fabric: InteractionFabric) -> tuple[str, ...]:
    return tuple(
        node.nodeId
        for node in fabric.list_nodes(capability=_SMART_PLUG_ACTION)
        if _is_smart_plug_node(node)
    )


async def turn_on_configured_smart_plugs(
    fabric: InteractionFabric,
    node_ids: tuple[str, ...],
    actor_id: str,
    event_id: str,
    *,
    clock: Callable[[], datetime] | None = None,
) -> UnlockPowerResult:
    """Route one unlock edge through the ordinary Fabric session safety boundary."""

    return await _set_configured_smart_plugs(
        fabric,
        node_ids,
        actor_id,
        event_id,
        requested_on=True,
        idempotency_scope="phone-unlock",
        clock=clock,
    )


async def toggle_configured_smart_plugs(
    fabric: InteractionFabric,
    node_ids: tuple[str, ...],
    actor_id: str,
    event_id: str,
    *,
    clock: Callable[[], datetime] | None = None,
) -> UnlockPowerResult:
    """Toggle one exact saved group from authoritative Matter health state."""

    return await _set_configured_smart_plugs(
        fabric,
        node_ids,
        actor_id,
        event_id,
        requested_on=None,
        idempotency_scope="phone-toggle",
        clock=clock,
    )


async def _set_configured_smart_plugs(
    fabric: InteractionFabric,
    node_ids: tuple[str, ...],
    actor_id: str,
    event_id: str,
    *,
    requested_on: bool | None,
    idempotency_scope: str,
    clock: Callable[[], datetime] | None,
) -> UnlockPowerResult:

    if not node_ids:
        return UnlockPowerResult(
            requestedCount=0,
            acceptedCount=0,
            failedNodeIds=[],
            message="No Matter smart plugs are configured for unlock automation.",
        )
    nodes_by_id = {node.nodeId: node for node in fabric.list_nodes()}
    nodes = [nodes_by_id.get(node_id) for node_id in node_ids]
    unavailable = [
        node_id
        for node_id, node in zip(node_ids, nodes, strict=True)
        if node is None
        or not _is_smart_plug_node(node)
        or node.connectionState is not FabricNodeConnectionState.connected
    ]
    if unavailable:
        return UnlockPowerResult(
            requestedCount=len(node_ids),
            acceptedCount=0,
            failedNodeIds=unavailable,
            message=(
                "At least one configured Matter smart plug is not connected; none were switched."
            ),
        )
    exact_nodes = [node for node in nodes if node is not None]
    scopes = {(node.siteId, node.roomId) for node in exact_nodes}
    if len(scopes) != 1:
        return UnlockPowerResult(
            requestedCount=len(node_ids),
            acceptedCount=0,
            failedNodeIds=list(node_ids),
            message="Configured Matter smart plugs must belong to one Control Tower room.",
        )

    desired_on = requested_on
    if desired_on is None:
        reported_states = [_reported_power_state(node) for node in exact_nodes]
        if any(state is None for state in reported_states):
            return UnlockPowerResult(
                requestedCount=len(node_ids),
                acceptedCount=0,
                failedNodeIds=list(node_ids),
                message=(
                    "Control Tower does not have a current power state for every configured "
                    "Matter smart plug; none were toggled."
                ),
            )
        desired_on = not all(state is True for state in reported_states)

    session = _preferred_automation_session(
        fabric,
        node_ids,
        nodes_by_id,
        actor_id=actor_id,
    )
    if session is None:
        session = _create_automation_session(fabric, exact_nodes, actor_id=actor_id)
    session = _prepare_automation_session(fabric, session, actor_id=actor_id)
    roles_by_node = {
        binding.nodeId: binding.role
        for binding in session.roleBindings
        if _SMART_PLUG_ROLE.fullmatch(binding.role) is not None
    }
    requested_at = _aware_utc((clock or (lambda: datetime.now(UTC)))())
    correlation_id = str(UUID(event_id))

    async def submit(
        node_id: str,
    ) -> tuple[str, tuple[FabricCommandLifecycleEvent, ...]]:
        request = FabricCommandRequest.model_validate(
            {
                "messageId": str(uuid4()),
                "schemaVersion": "1.0",
                "messageType": "command.requested",
                "action": _SMART_PLUG_ACTION,
                "target": {"role": roles_by_node[node_id]},
                "sessionId": session.sessionId,
                "parameters": {"on": desired_on},
                "priority": FabricCommandPriority.lesson_automation.value,
                "idempotencyKey": (f"{idempotency_scope}:{actor_id}:{event_id}:{node_id}"),
                "requestedAt": requested_at,
                "ttlMs": 5_000,
                "safetyProfile": session.safetyProfile,
                "correlationId": correlation_id,
            }
        )
        return node_id, await fabric.submit_command(request)

    submitted = await asyncio.gather(*(submit(node_id) for node_id in node_ids))
    failed = [
        node_id
        for node_id, lifecycle in submitted
        if not lifecycle or lifecycle[-1].stage in _FAILED_COMMAND_STAGES
    ]
    accepted_count = len(node_ids) - len(failed)
    return UnlockPowerResult(
        requestedCount=len(node_ids),
        acceptedCount=accepted_count,
        failedNodeIds=failed,
        on=desired_on,
        message=(
            f"Turn-{'on' if desired_on else 'off'} was accepted for "
            f"{accepted_count} configured Matter smart plugs."
            if not failed
            else "Control Tower rejected at least one configured Matter smart-plug command."
        ),
    )


def _reported_power_state(node: IntegrationNode) -> bool | None:
    metadata = node.metadata.model_dump(mode="json")
    health_metrics = metadata.get("healthMetrics")
    if not isinstance(health_metrics, Mapping):
        return None
    on = health_metrics.get("on")
    return on if isinstance(on, bool) else None


def _valid_signature(
    event: UnlockEventRequest,
    signature: str,
    secret: str,
    *,
    signing_domain: str,
) -> bool:
    if _SIGNATURE.fullmatch(signature) is None:
        return False
    expected = hmac.new(
        secret.encode("ascii"),
        _signed_phone_payload(signing_domain, event),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature.casefold())


def _is_smart_plug_node(node: IntegrationNode) -> bool:
    return any(capability.name == _SMART_PLUG_ACTION for capability in node.consumedCapabilities)


def _preferred_automation_session(
    fabric: InteractionFabric,
    node_ids: tuple[str, ...],
    nodes_by_id: dict[str, IntegrationNode],
    *,
    actor_id: str,
) -> InteractionSession | None:
    wanted = frozenset(node_ids)
    candidates: list[InteractionSession] = []
    for session in fabric.list_sessions():
        if (
            session.coursePackId != _SMART_PLUG_COURSE
            or session.createdBy != actor_id
            or session.state
            in {
                FabricSessionState.stopped,
                FabricSessionState.emergency_stopped,
                FabricSessionState.failed,
            }
        ):
            continue
        bindings = [
            binding
            for binding in session.roleBindings
            if _SMART_PLUG_ROLE.fullmatch(binding.role) is not None
        ]
        if not wanted.issubset(binding.nodeId for binding in bindings):
            continue
        bound_nodes = [nodes_by_id.get(binding.nodeId) for binding in bindings]
        if any(
            node is None or node.connectionState is not FabricNodeConnectionState.connected
            for node in bound_nodes
        ):
            continue
        candidates.append(session)
    rank = {
        FabricSessionState.active: 0,
        FabricSessionState.paused: 1,
        FabricSessionState.ready: 2,
        FabricSessionState.draft: 3,
    }
    return min(
        candidates,
        key=lambda item: (0 if item.armed else 1, rank[item.state], -item.updatedAt.timestamp()),
        default=None,
    )


def _create_automation_session(
    fabric: InteractionFabric,
    nodes: list[IntegrationNode],
    *,
    actor_id: str,
) -> InteractionSession:
    course_packs = [
        course_pack
        for course_pack in fabric.list_course_packs()
        if course_pack.coursePackId == _SMART_PLUG_COURSE
    ]
    if not course_packs:
        raise UnlockAutomationError(
            "UNLOCK_AUTOMATION_COURSE_UNAVAILABLE",
            "The Matter smart-plug control package is not installed.",
        )
    course_pack = max(course_packs, key=lambda item: _version_key(item.version))
    first = nodes[0]
    session = fabric.create_session(
        CreateInteractionSessionRequest.model_validate(
            {
                "coursePackId": course_pack.coursePackId,
                "coursePackVersion": course_pack.version,
                "siteId": first.siteId,
                "roomId": first.roomId,
                "mode": FabricSessionMode.physical.value,
            }
        ),
        actor_id=actor_id,
    )
    for index, node in enumerate(nodes):
        role = "classroom_plug" if index == 0 else f"classroom_plug_{index + 1}"
        session = fabric.assign_role(session.sessionId, role, node.nodeId, actor_id=actor_id)
    return session


def _prepare_automation_session(
    fabric: InteractionFabric,
    session: InteractionSession,
    *,
    actor_id: str,
) -> InteractionSession:
    prepared = session
    needs_arm = prepared.mode is FabricSessionMode.physical and not prepared.armed
    if needs_arm and prepared.state is FabricSessionState.active:
        prepared = fabric.transition_session(prepared.sessionId, "pause", actor_id=actor_id)
    if needs_arm:
        prepared = fabric.transition_session(prepared.sessionId, "arm", actor_id=actor_id)
    if prepared.state is not FabricSessionState.active or needs_arm:
        prepared = fabric.transition_session(prepared.sessionId, "start", actor_id=actor_id)
    if prepared.state is not FabricSessionState.active or not prepared.armed:
        raise UnlockAutomationError(
            "UNLOCK_AUTOMATION_SESSION_NOT_READY",
            "Control Tower could not prepare the Matter smart-plug safety session.",
        )
    return prepared


def _version_key(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError:
        return (0,)


def _validated_lan_origin(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
        port = parsed.port
    except ValueError as error:
        raise ValueError("Unlock automation requires an exact private IPv4 LAN origin") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not isinstance(address, ipaddress.IPv4Address)
        or not any(address in network for network in _PRIVATE_NETWORKS)
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Unlock automation requires an exact private IPv4 LAN origin")
    return f"{parsed.scheme}://{address}:{port}"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Unlock automation timestamps must include a UTC offset")
    return value.astimezone(UTC)
