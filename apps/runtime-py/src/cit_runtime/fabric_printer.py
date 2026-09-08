"""Fail-closed Creality/Klipper preparation and print-job boundary.

The service deliberately separates local model staging, local slicing, remote
upload, and print start.  Merely constructing it or reading a locked snapshot
never opens a network connection or launches Creality Print.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import secrets
import subprocess
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from ipaddress import IPv4Address
from pathlib import Path, PurePath
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

_SAFE_ARTIFACT_ID = re.compile(r"^[a-f0-9]{32}$")
_SAFE_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9.-]{0,95}$")
_SAFE_REMOTE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,159}\.gcode$")
_SOURCE_SUFFIXES = {".stl": "model/stl", ".3mf": "model/3mf"}
_MAX_SOURCE_BYTES = 64 * 1024 * 1024
_MAX_GCODE_BYTES = 256 * 1024 * 1024
_START_INTENT_TTL = timedelta(minutes=2)


class PrinterState(StrEnum):
    CURRENT_PRINT_LOCKED = "current_print_locked"
    UNCONFIGURED = "unconfigured"
    STANDBY = "standby"
    PRINTING = "printing"
    PAUSED = "paused"
    ERROR = "error"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    STARTING = "starting"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class PrinterLockReason(StrEnum):
    CURRENT_PRINT = "current_print"
    MONITORING_NOT_CONFIGURED = "monitoring_not_configured"
    REMOTE_WRITES_DISABLED = "remote_writes_disabled"
    NOT_STANDBY = "not_standby"


class PrinterError(RuntimeError):
    """A stable printer-boundary failure safe to return to the tutor UI."""

    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class PrinterOutcomeUnknownError(PrinterError):
    """A start request may have reached the printer and must not be retried."""


class PrinterTemperature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actualCelsius: float
    targetCelsius: float


class PrinterJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    progressPercent: float | None = None
    elapsedSeconds: float | None = None


class PrinterProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profileId: str
    displayName: str
    printerModel: str
    nozzleDiameterMm: float
    filament: str
    process: str
    available: bool


class PrinterSourceArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifactId: str
    fileName: str
    mediaType: str
    sizeBytes: int
    sha256: str
    createdAt: datetime


class PrinterGcodeArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifactId: str
    fileName: str
    sizeBytes: int
    sha256: str
    createdAt: datetime
    sourceArtifactId: str
    profileId: str
    remoteFileName: str | None = None
    uploadedAt: datetime | None = None
    startAttemptedAt: datetime | None = None


class PrinterOperations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stageSource: bool
    verifyIdle: bool
    slice: bool
    upload: bool
    start: bool
    lockReasonCode: PrinterLockReason | None = None
    lockReason: str | None = None


class PrinterSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: str = "1.0"
    printerId: str
    displayName: str
    model: str
    address: str
    transport: str
    state: PrinterState
    lastCheckedAt: datetime | None = None
    currentJob: PrinterJob | None = None
    nozzle: PrinterTemperature | None = None
    bed: PrinterTemperature | None = None
    operations: PrinterOperations
    profiles: list[PrinterProfile]
    sources: list[PrinterSourceArtifact]
    gcodeArtifacts: list[PrinterGcodeArtifact]


class PrinterStartIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifactId: str
    confirmationToken: str
    expiresAt: datetime
    remoteFileName: str
    sha256: str
    profileId: str


class PrinterActionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    message: str
    snapshot: PrinterSnapshot


@dataclass(frozen=True, slots=True)
class PrinterProfileConfiguration:
    profile_id: str
    display_name: str
    printer_model: str
    nozzle_diameter_mm: float
    filament_name: str
    process_name: str
    printer_settings: Path
    process_settings: Path
    filament_settings: Path
    max_nozzle_celsius: float = 300.0
    max_bed_celsius: float = 120.0

    def __post_init__(self) -> None:
        if _SAFE_PROFILE_ID.fullmatch(self.profile_id) is None:
            raise ValueError("Printer profile identifier is invalid")
        if not all(
            path.is_absolute()
            for path in (
                self.printer_settings,
                self.process_settings,
                self.filament_settings,
            )
        ):
            raise ValueError("Printer profile paths must be absolute")

    @property
    def available(self) -> bool:
        return all(
            path.is_file()
            for path in (
                self.printer_settings,
                self.process_settings,
                self.filament_settings,
            )
        )

    def public(self) -> PrinterProfile:
        return PrinterProfile(
            profileId=self.profile_id,
            displayName=self.display_name,
            printerModel=self.printer_model,
            nozzleDiameterMm=self.nozzle_diameter_mm,
            filament=self.filament_name,
            process=self.process_name,
            available=self.available,
        )


@dataclass(frozen=True, slots=True)
class PrinterConfiguration:
    address: IPv4Address
    display_name: str
    model: str
    staging_root: Path
    slicer_executable: Path | None = None
    profiles: tuple[PrinterProfileConfiguration, ...] = ()
    moonraker_port: int | None = None
    api_key: str | None = None
    network_monitoring_enabled: bool = False
    remote_writes_enabled: bool = False
    current_print_locked: bool = True

    def __post_init__(self) -> None:
        if not self.staging_root.is_absolute():
            raise ValueError("Printer staging root must be absolute")
        if self.slicer_executable is not None and not self.slicer_executable.is_absolute():
            raise ValueError("Creality Print executable path must be absolute")
        if self.moonraker_port is not None and not 1 <= self.moonraker_port <= 65535:
            raise ValueError("Moonraker port is invalid")
        if self.network_monitoring_enabled and self.moonraker_port is None:
            raise ValueError("Network monitoring requires an explicit Moonraker port")
        if self.remote_writes_enabled and not self.network_monitoring_enabled:
            raise ValueError("Remote writes require verified network monitoring")
        profile_ids = [profile.profile_id for profile in self.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("Printer profile identifiers must be unique")


@dataclass(frozen=True, slots=True)
class TransportSnapshot:
    state: PrinterState
    checked_at: datetime
    job: PrinterJob | None = None
    nozzle: PrinterTemperature | None = None
    bed: PrinterTemperature | None = None


class PrinterTransport(Protocol):
    async def status(self) -> TransportSnapshot: ...

    async def upload(self, path: Path, *, remote_name: str, checksum: str) -> str: ...

    async def start(self, remote_name: str) -> None: ...


class PrinterSlicer(Protocol):
    async def slice(
        self,
        source: Path,
        *,
        output_directory: Path,
        profile: PrinterProfileConfiguration,
    ) -> Path: ...


HttpRequest = Callable[
    [str, str, Mapping[str, str], bytes | None, float],
    Awaitable[tuple[int, bytes]],
]


class MoonrakerTransport:
    """Small documented Moonraker HTTP client pinned to one configured host."""

    def __init__(
        self,
        address: IPv4Address,
        port: int,
        *,
        api_key: str | None = None,
        request: HttpRequest | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        if not 1 <= port <= 65535:
            raise ValueError("Moonraker port is invalid")
        if not 0.1 <= timeout_seconds <= 60:
            raise ValueError("Moonraker timeout is invalid")
        self._base_url = f"http://{address}:{port}"
        self._headers = {
            "Accept": "application/json",
            **({"X-Api-Key": api_key} if api_key else {}),
        }
        self._request = request or _stdlib_http_request
        self._timeout = timeout_seconds

    async def status(self) -> TransportSnapshot:
        server = await self._json("GET", "/server/info")
        result = _mapping(server.get("result"), "Moonraker server response")
        if result.get("klippy_connected") is not True:
            return TransportSnapshot(
                state=PrinterState.OFFLINE,
                checked_at=datetime.now(UTC),
            )
        objects = await self._json(
            "GET",
            "/printer/objects/query?print_stats&extruder&heater_bed&virtual_sdcard",
        )
        object_result = _mapping(objects.get("result"), "Moonraker object response")
        status = _mapping(object_result.get("status"), "Moonraker printer status")
        print_stats = _mapping(status.get("print_stats"), "Moonraker print statistics")
        raw_state = str(print_stats.get("state", "unknown")).casefold()
        state = {
            "standby": PrinterState.STANDBY,
            "printing": PrinterState.PRINTING,
            "paused": PrinterState.PAUSED,
            "error": PrinterState.ERROR,
            "complete": PrinterState.COMPLETE,
            "cancelled": PrinterState.CANCELLED,
        }.get(raw_state, PrinterState.UNKNOWN)
        filename = print_stats.get("filename")
        progress = _optional_number(_mapping_or_empty(status.get("virtual_sdcard")).get("progress"))
        duration = _optional_number(print_stats.get("print_duration"))
        job = (
            PrinterJob(
                filename=filename,
                progressPercent=None if progress is None else round(progress * 100, 1),
                elapsedSeconds=duration,
            )
            if isinstance(filename, str) and filename
            else None
        )
        return TransportSnapshot(
            state=state,
            checked_at=datetime.now(UTC),
            job=job,
            nozzle=_temperature(status.get("extruder")),
            bed=_temperature(status.get("heater_bed")),
        )

    async def upload(self, path: Path, *, remote_name: str, checksum: str) -> str:
        if _SAFE_REMOTE_NAME.fullmatch(remote_name) is None:
            raise PrinterError("PRINTER_REMOTE_NAME_INVALID", "Remote print filename is invalid")
        boundary = f"cit-{secrets.token_hex(16)}"
        prefix = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{remote_name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        fields = (
            f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="root"\r\n\r\ngcodes'
            f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="checksum"\r\n\r\n{checksum}'
            f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="print"\r\n\r\nfalse'
            f"\r\n--{boundary}--\r\n"
        ).encode()
        payload = prefix + await asyncio.to_thread(path.read_bytes) + fields
        response = await self._json(
            "POST",
            "/server/files/upload",
            body=payload,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            request_timeout=30.0,
        )
        result = _mapping(response.get("result"), "Moonraker upload response")
        if result.get("print_started") is not False:
            raise PrinterError(
                "PRINTER_UPLOAD_STARTED_UNEXPECTEDLY",
                "The printer reported an unexpected print start; do not retry",
            )
        item = _mapping(result.get("item"), "Moonraker uploaded item")
        uploaded_path = item.get("path")
        if uploaded_path != remote_name:
            raise PrinterError(
                "PRINTER_UPLOAD_IDENTITY_MISMATCH",
                "The printer did not confirm the exact uploaded filename",
            )
        return remote_name

    async def start(self, remote_name: str) -> None:
        if _SAFE_REMOTE_NAME.fullmatch(remote_name) is None:
            raise PrinterError("PRINTER_REMOTE_NAME_INVALID", "Remote print filename is invalid")
        try:
            response = await self._json(
                "POST",
                f"/printer/print/start?{urlencode({'filename': remote_name})}",
                body=b"",
            )
        except PrinterError as error:
            raise PrinterOutcomeUnknownError(
                "PRINTER_START_OUTCOME_UNKNOWN",
                "The start result is unknown. Check printer status and do not retry.",
                status_code=502,
            ) from error
        if response.get("result") != "ok":
            raise PrinterOutcomeUnknownError(
                "PRINTER_START_OUTCOME_UNKNOWN",
                "The printer did not confirm the start. Check status and do not retry.",
                status_code=502,
            )

    async def _json(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        request_timeout: float | None = None,
    ) -> Mapping[str, object]:
        try:
            status, payload = await self._request(
                method,
                f"{self._base_url}{path}",
                {**self._headers, **(headers or {})},
                body,
                request_timeout or self._timeout,
            )
        except (OSError, TimeoutError, URLError) as error:
            raise PrinterError(
                "PRINTER_NETWORK_UNAVAILABLE",
                "The documented printer service is unavailable",
                status_code=502,
            ) from error
        if not 200 <= status < 300:
            raise PrinterError(
                "PRINTER_SERVICE_REJECTED",
                f"The printer service rejected the request with HTTP {status}",
                status_code=502,
            )
        try:
            decoded = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PrinterError(
                "PRINTER_RESPONSE_INVALID",
                "The printer returned an invalid response",
                status_code=502,
            ) from error
        if not isinstance(decoded, dict):
            raise PrinterError(
                "PRINTER_RESPONSE_INVALID",
                "The printer returned an invalid response",
                status_code=502,
            )
        if "error" in decoded:
            raise PrinterError(
                "PRINTER_SERVICE_REJECTED",
                "The printer service rejected the request",
                status_code=502,
            )
        return decoded


class CrealityPrintCliSlicer:
    """Invoke only Creality Print's documented offline slicing action."""

    def __init__(self, executable: Path, *, timeout_seconds: float = 300.0) -> None:
        if not executable.is_absolute():
            raise ValueError("Creality Print executable path must be absolute")
        if not 1 <= timeout_seconds <= 900:
            raise ValueError("Slicer timeout is invalid")
        self._executable = executable
        self._timeout = timeout_seconds

    async def slice(
        self,
        source: Path,
        *,
        output_directory: Path,
        profile: PrinterProfileConfiguration,
    ) -> Path:
        if not self._executable.is_file():
            raise PrinterError("PRINTER_SLICER_UNAVAILABLE", "Creality Print is not installed")
        if not profile.available:
            raise PrinterError(
                "PRINTER_PROFILE_UNAVAILABLE",
                "The selected Creality Print profile is unavailable",
            )
        await asyncio.to_thread(output_directory.mkdir, parents=True, exist_ok=False)
        settings = f"{profile.printer_settings};{profile.process_settings}"
        creation_flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        process = await asyncio.create_subprocess_exec(
            str(self._executable),
            "--slice",
            "0",
            "--outputdir",
            str(output_directory),
            "--load_settings",
            settings,
            "--load_filaments",
            str(profile.filament_settings),
            "--logfile",
            str(output_directory / "slice.log"),
            str(source),
            cwd=str(self._executable.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creation_flags,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), self._timeout)
        except TimeoutError as error:
            process.kill()
            await process.communicate()
            raise PrinterError(
                "PRINTER_SLICE_TIMEOUT", "Creality Print slicing timed out"
            ) from error
        if process.returncode != 0:
            diagnostic = (stderr or stdout).decode(errors="replace").strip()[-400:]
            raise PrinterError(
                "PRINTER_SLICE_FAILED",
                "Creality Print could not prepare this model"
                + (f": {diagnostic}" if diagnostic else ""),
            )
        outputs = await asyncio.to_thread(_gcode_outputs, output_directory)
        if len(outputs) != 1:
            raise PrinterError(
                "PRINTER_SLICE_OUTPUT_INVALID",
                "Creality Print did not produce exactly one G-code file",
            )
        return outputs[0]


@dataclass(slots=True)
class _SourceRecord:
    public: PrinterSourceArtifact
    path: Path


@dataclass(slots=True)
class _GcodeRecord:
    public: PrinterGcodeArtifact
    path: Path


@dataclass(frozen=True, slots=True)
class _StartIntentRecord:
    token_hash: str
    artifact_id: str
    actor_id: str
    expires_at: datetime


class CrealityPrinterService:
    """Stateful, bounded coordinator for one exact classroom printer."""

    def __init__(
        self,
        configuration: PrinterConfiguration,
        *,
        transport: PrinterTransport | None = None,
        slicer: PrinterSlicer | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._configuration = configuration
        self._transport = transport
        if transport is None and configuration.network_monitoring_enabled:
            if configuration.moonraker_port is None:
                raise ValueError("Moonraker port is required")
            self._transport = MoonrakerTransport(
                configuration.address,
                configuration.moonraker_port,
                api_key=configuration.api_key,
            )
        self._slicer = slicer
        if slicer is None and configuration.slicer_executable is not None:
            self._slicer = CrealityPrintCliSlicer(configuration.slicer_executable)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._current_print_locked = configuration.current_print_locked
        self._sources: dict[str, _SourceRecord] = {}
        self._gcode: dict[str, _GcodeRecord] = {}
        self._start_intents: dict[str, _StartIntentRecord] = {}
        self._last_transport_snapshot: TransportSnapshot | None = None
        self._operation_lock = asyncio.Lock()

    async def snapshot(self, *, refresh: bool = False) -> PrinterSnapshot:
        if self._current_print_locked:
            return self._public_snapshot(PrinterState.CURRENT_PRINT_LOCKED)
        if not self._configuration.network_monitoring_enabled or self._transport is None:
            return self._public_snapshot(PrinterState.UNCONFIGURED)
        if refresh or self._last_transport_snapshot is None:
            try:
                self._last_transport_snapshot = await self._transport.status()
            except PrinterError:
                self._last_transport_snapshot = TransportSnapshot(
                    state=PrinterState.OFFLINE,
                    checked_at=self._now(),
                )
        return self._public_snapshot(self._last_transport_snapshot.state)

    async def verify_idle(self) -> PrinterActionResult:
        if not self._configuration.network_monitoring_enabled or self._transport is None:
            raise PrinterError(
                "PRINTER_MONITORING_NOT_CONFIGURED",
                "A documented Moonraker endpoint must be configured before checking the printer",
            )
        observed = await self._transport.status()
        self._last_transport_snapshot = observed
        if observed.state is not PrinterState.STANDBY:
            raise PrinterError(
                "PRINTER_NOT_IDLE",
                (
                    f"The printer reported {observed.state.value}; "
                    "the current-print lock remains active"
                ),
            )
        self._current_print_locked = False
        return PrinterActionResult(
            accepted=True,
            message="The printer reported standby; staged operations are now available.",
            snapshot=self._public_snapshot(observed.state),
        )

    async def stage_source(
        self,
        *,
        file_name: str,
        media_type: str,
        content: bytes,
    ) -> PrinterSourceArtifact:
        normalized = _validated_file_name(file_name)
        suffix = Path(normalized).suffix.casefold()
        expected_media_type = _SOURCE_SUFFIXES.get(suffix)
        if expected_media_type is None:
            raise PrinterError(
                "PRINTER_SOURCE_TYPE_UNSUPPORTED",
                "Choose an STL or 3MF model file",
                status_code=415,
            )
        if not 1 <= len(content) <= _MAX_SOURCE_BYTES:
            raise PrinterError(
                "PRINTER_SOURCE_SIZE_INVALID",
                "Model files must be between 1 byte and 64 MiB",
                status_code=413,
            )
        if media_type not in {"application/octet-stream", expected_media_type, "model/3mf"}:
            raise PrinterError(
                "PRINTER_SOURCE_TYPE_UNSUPPORTED",
                "The uploaded model media type is not supported",
                status_code=415,
            )
        artifact_id = uuid4().hex
        source_directory = self._configuration.staging_root / "sources"
        path = source_directory / f"{artifact_id}{suffix}"
        temporary = source_directory / f"{artifact_id}.part"
        await asyncio.to_thread(
            _write_source_atomically,
            source_directory,
            temporary,
            path,
            content,
        )
        public = PrinterSourceArtifact(
            artifactId=artifact_id,
            fileName=normalized,
            mediaType=expected_media_type,
            sizeBytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            createdAt=self._now(),
        )
        self._sources[artifact_id] = _SourceRecord(public=public, path=path)
        return public

    async def slice_source(self, source_id: str, profile_id: str) -> PrinterActionResult:
        _require_artifact_id(source_id)
        if self._current_print_locked:
            raise PrinterError(
                "PRINTER_CURRENT_PRINT_LOCKED",
                "The current print is protected; slicing remains locked until standby is verified",
            )
        if self._slicer is None:
            raise PrinterError("PRINTER_SLICER_UNAVAILABLE", "Creality Print CLI is unavailable")
        source = self._sources.get(source_id)
        if source is None:
            raise PrinterError(
                "PRINTER_SOURCE_NOT_FOUND", "The staged model was not found", status_code=404
            )
        profile = next(
            (item for item in self._configuration.profiles if item.profile_id == profile_id),
            None,
        )
        if profile is None:
            raise PrinterError("PRINTER_PROFILE_NOT_FOUND", "Select a configured printer profile")
        async with self._operation_lock:
            artifact_id = uuid4().hex
            work_directory = self._configuration.staging_root / "slice-work" / artifact_id
            generated = await self._slicer.slice(
                source.path,
                output_directory=work_directory,
                profile=profile,
            )
            gcode_directory = self._configuration.staging_root / "gcode"
            path = gcode_directory / f"{artifact_id}.gcode"
            size, digest = await asyncio.to_thread(
                _finalize_gcode,
                generated,
                path,
                profile,
            )
            stem = re.sub(r"[^A-Za-z0-9._ -]", "-", Path(source.public.fileName).stem)[:80]
            public = PrinterGcodeArtifact(
                artifactId=artifact_id,
                fileName=f"{stem or 'model'}.gcode",
                sizeBytes=size,
                sha256=digest,
                createdAt=self._now(),
                sourceArtifactId=source_id,
                profileId=profile_id,
            )
            self._gcode[artifact_id] = _GcodeRecord(public=public, path=path)
        return PrinterActionResult(
            accepted=True,
            message="G-code was prepared locally. Nothing was sent to the printer.",
            snapshot=await self.snapshot(),
        )

    async def upload_artifact(self, artifact_id: str) -> PrinterActionResult:
        record = self._gcode_record(artifact_id)
        self._require_remote_writes()
        async with self._operation_lock:
            observed = await self._require_standby()
            remote_name = _remote_name(record.public)
            assert self._transport is not None
            confirmed_name = await self._transport.upload(
                record.path,
                remote_name=remote_name,
                checksum=record.public.sha256,
            )
            record.public = record.public.model_copy(
                update={"remoteFileName": confirmed_name, "uploadedAt": self._now()}
            )
            self._last_transport_snapshot = observed
        return PrinterActionResult(
            accepted=True,
            message="G-code was uploaded without starting a print.",
            snapshot=await self.snapshot(),
        )

    async def prepare_start(self, artifact_id: str, *, actor_id: str) -> PrinterStartIntent:
        record = self._gcode_record(artifact_id)
        self._require_remote_writes()
        if record.public.remoteFileName is None or record.public.uploadedAt is None:
            raise PrinterError(
                "PRINTER_ARTIFACT_NOT_UPLOADED",
                "Upload this exact G-code artifact before starting it",
            )
        await self._require_standby()
        self._expire_start_intents()
        token = secrets.token_urlsafe(32)
        expires_at = self._now() + _START_INTENT_TTL
        token_hash = _hash_start_token(token)
        self._start_intents[token_hash] = _StartIntentRecord(
            token_hash=token_hash,
            artifact_id=artifact_id,
            actor_id=actor_id,
            expires_at=expires_at,
        )
        return PrinterStartIntent(
            artifactId=artifact_id,
            confirmationToken=token,
            expiresAt=expires_at,
            remoteFileName=record.public.remoteFileName,
            sha256=record.public.sha256,
            profileId=record.public.profileId,
        )

    async def start_artifact(
        self,
        artifact_id: str,
        *,
        actor_id: str,
        confirmation_token: str,
    ) -> PrinterActionResult:
        record = self._gcode_record(artifact_id)
        self._require_remote_writes()
        token_hash = _hash_start_token(confirmation_token)
        intent = self._start_intents.pop(token_hash, None)
        if (
            intent is None
            or intent.artifact_id != artifact_id
            or intent.actor_id != actor_id
            or intent.expires_at <= self._now()
        ):
            raise PrinterError(
                "PRINTER_START_CONFIRMATION_INVALID",
                "The print confirmation expired or does not match this artifact",
            )
        remote_name = record.public.remoteFileName
        if remote_name is None:
            raise PrinterError("PRINTER_ARTIFACT_NOT_UPLOADED", "The G-code is not uploaded")
        async with self._operation_lock:
            await self._require_standby()
            attempted_at = self._now()
            record.public = record.public.model_copy(update={"startAttemptedAt": attempted_at})
            assert self._transport is not None
            await self._transport.start(remote_name)
            self._last_transport_snapshot = TransportSnapshot(
                state=PrinterState.STARTING,
                checked_at=attempted_at,
                job=PrinterJob(filename=remote_name),
            )
        return PrinterActionResult(
            accepted=True,
            message="The printer confirmed the print start.",
            snapshot=self._public_snapshot(PrinterState.STARTING),
        )

    def gcode_download(self, artifact_id: str) -> tuple[PrinterGcodeArtifact, Path]:
        record = self._gcode_record(artifact_id)
        return record.public, record.path

    def _gcode_record(self, artifact_id: str) -> _GcodeRecord:
        _require_artifact_id(artifact_id)
        record = self._gcode.get(artifact_id)
        if record is None:
            raise PrinterError(
                "PRINTER_ARTIFACT_NOT_FOUND", "The G-code artifact was not found", status_code=404
            )
        return record

    def _require_remote_writes(self) -> None:
        if self._current_print_locked:
            raise PrinterError(
                "PRINTER_CURRENT_PRINT_LOCKED",
                "The current print is protected; remote operations are locked",
            )
        if (
            not self._configuration.remote_writes_enabled
            or not self._configuration.network_monitoring_enabled
            or self._transport is None
        ):
            raise PrinterError(
                "PRINTER_REMOTE_WRITES_DISABLED",
                "Printer upload and start are disabled until the documented transport is verified",
            )

    async def _require_standby(self) -> TransportSnapshot:
        assert self._transport is not None
        observed = await self._transport.status()
        self._last_transport_snapshot = observed
        if observed.state is not PrinterState.STANDBY:
            raise PrinterError(
                "PRINTER_NOT_IDLE",
                f"The printer reported {observed.state.value}; no write was sent",
            )
        return observed

    def _public_snapshot(self, state: PrinterState) -> PrinterSnapshot:
        observed = self._last_transport_snapshot
        locked = self._current_print_locked
        monitoring = self._configuration.network_monitoring_enabled and self._transport is not None
        writes = self._configuration.remote_writes_enabled and monitoring and not locked
        standby = state is PrinterState.STANDBY
        slicer_ready = (
            not locked
            and self._slicer is not None
            and any(profile.available for profile in self._configuration.profiles)
        )
        if locked:
            reason_code = PrinterLockReason.CURRENT_PRINT
            reason = "The current print is protected. Verify standby after it finishes."
        elif not monitoring:
            reason_code = PrinterLockReason.MONITORING_NOT_CONFIGURED
            reason = "Documented Moonraker monitoring has not been configured."
        elif not self._configuration.remote_writes_enabled:
            reason_code = PrinterLockReason.REMOTE_WRITES_DISABLED
            reason = "Remote upload and print start are disabled."
        elif not standby:
            reason_code = PrinterLockReason.NOT_STANDBY
            reason = f"Remote writes require standby; current state is {state.value}."
        else:
            reason_code = None
            reason = None
        uploaded_ready = any(
            record.public.remoteFileName is not None for record in self._gcode.values()
        )
        return PrinterSnapshot(
            printerId=f"creality-k1-max-{str(self._configuration.address).replace('.', '-')}",
            displayName=self._configuration.display_name,
            model=self._configuration.model,
            address=str(self._configuration.address),
            transport=(
                f"Moonraker:{self._configuration.moonraker_port}" if monitoring else "Not verified"
            ),
            state=state,
            lastCheckedAt=observed.checked_at if observed is not None else None,
            currentJob=observed.job if observed is not None else None,
            nozzle=observed.nozzle if observed is not None else None,
            bed=observed.bed if observed is not None else None,
            operations=PrinterOperations(
                stageSource=True,
                verifyIdle=locked and monitoring,
                slice=slicer_ready,
                upload=writes and standby and bool(self._gcode),
                start=writes and standby and uploaded_ready,
                lockReasonCode=reason_code,
                lockReason=reason,
            ),
            profiles=[profile.public() for profile in self._configuration.profiles],
            sources=[record.public for record in self._sources.values()],
            gcodeArtifacts=[record.public for record in self._gcode.values()],
        )

    def _expire_start_intents(self) -> None:
        now = self._now()
        self._start_intents = {
            key: value for key, value in self._start_intents.items() if value.expires_at > now
        }

    def _now(self) -> datetime:
        value = self._clock()
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def configured_creality_printer(
    data_directory: Path,
    *,
    allow_physical: bool,
) -> CrealityPrinterService:
    """Build the persistent printer boundary without contacting the printer."""

    address = IPv4Address(os.environ.get("CITXR_CREALITY_ADDRESS", "172.30.1.55"))
    port_text = os.environ.get("CITXR_CREALITY_MOONRAKER_PORT")
    port = int(port_text) if port_text else None
    monitoring = _environment_boolean("CITXR_CREALITY_MONITORING", False)
    requested_writes = _environment_boolean("CITXR_CREALITY_REMOTE_WRITES", False)
    current_print_locked = _environment_boolean("CITXR_CREALITY_CURRENT_PRINT_LOCKED", True)
    install_root = Path(
        os.environ.get(
            "CITXR_CREALITY_INSTALL_ROOT",
            r"C:\Program Files\Creality\Creality Print 7.2",
        )
    )
    profiles_root = install_root / "resources" / "profiles" / "Creality"
    profiles = (
        _creality_profile(
            profiles_root, model="Creality K1 Max", profile_id="k1-max-0.4-pla-standard"
        ),
        _creality_profile(
            profiles_root,
            model="Creality K1 Max 2025_CFS-C",
            profile_id="k1-max-2025-0.4-pla-standard",
            display_model="K1 Max 2025",
        ),
    )
    return CrealityPrinterService(
        PrinterConfiguration(
            address=address,
            display_name="3D Printer",
            model="Creality K1 Max (generation not yet verified)",
            staging_root=(data_directory / "printer-staging").resolve(),
            slicer_executable=(install_root / "CrealityPrint.exe").resolve(),
            profiles=profiles,
            moonraker_port=port,
            api_key=os.environ.get("CITXR_CREALITY_API_KEY"),
            network_monitoring_enabled=monitoring,
            remote_writes_enabled=requested_writes and allow_physical,
            current_print_locked=current_print_locked,
        )
    )


def disabled_creality_printer(staging_root: Path) -> CrealityPrinterService:
    return CrealityPrinterService(
        PrinterConfiguration(
            address=IPv4Address("172.30.1.55"),
            display_name="3D Printer",
            model="Creality K1 Max (generation not yet verified)",
            staging_root=staging_root.resolve(),
            current_print_locked=True,
        )
    )


def _creality_profile(
    root: Path,
    *,
    model: str,
    profile_id: str,
    display_model: str | None = None,
) -> PrinterProfileConfiguration:
    return PrinterProfileConfiguration(
        profile_id=profile_id,
        display_name=f"{display_model or 'K1 Max'} · 0.20 mm · Generic PLA · 0.4 mm",
        printer_model=display_model or "K1 Max",
        nozzle_diameter_mm=0.4,
        filament_name="Generic PLA",
        process_name="0.20 mm Standard",
        printer_settings=(root / "machine" / f"{model} 0.4 nozzle.json").resolve(),
        process_settings=(root / "process" / f"0.20mm Standard @{model} 0.4 nozzle.json").resolve(),
        filament_settings=(root / "filament" / f"Generic PLA @{model} 0.4 nozzle.json").resolve(),
    )


def _environment_boolean(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.casefold()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{name} must be 'true' or 'false'")
    return normalized == "true"


async def _stdlib_http_request(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | None,
    request_timeout: float,
) -> tuple[int, bytes]:
    def request() -> tuple[int, bytes]:
        outgoing = Request(url, method=method, headers=dict(headers), data=body)
        try:
            with urlopen(outgoing, timeout=request_timeout) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()

    return await asyncio.to_thread(request)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise PrinterError("PRINTER_RESPONSE_INVALID", f"{label} is invalid", status_code=502)
    return value


def _mapping_or_empty(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def _optional_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _temperature(value: object) -> PrinterTemperature | None:
    fields = _mapping_or_empty(value)
    actual = _optional_number(fields.get("temperature"))
    target = _optional_number(fields.get("target"))
    return (
        PrinterTemperature(actualCelsius=actual, targetCelsius=target)
        if actual is not None and target is not None
        else None
    )


def _validated_file_name(value: str) -> str:
    if (
        value != value.strip()
        or not 1 <= len(value) <= 160
        or PurePath(value).name != value
        or "/" in value
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise PrinterError("PRINTER_SOURCE_NAME_INVALID", "Model filename is invalid")
    return value


def _require_artifact_id(value: str) -> None:
    if _SAFE_ARTIFACT_ID.fullmatch(value) is None:
        raise PrinterError("PRINTER_ARTIFACT_ID_INVALID", "Printer artifact identifier is invalid")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_source_atomically(
    directory: Path,
    temporary: Path,
    destination: Path,
    content: bytes,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    temporary.write_bytes(content)
    temporary.replace(destination)


def _finalize_gcode(
    generated: Path,
    destination: Path,
    profile: PrinterProfileConfiguration,
) -> tuple[int, str]:
    _validate_gcode(generated, profile)
    destination.parent.mkdir(parents=True, exist_ok=True)
    generated.replace(destination)
    return destination.stat().st_size, _sha256_file(destination)


def _gcode_outputs(output_directory: Path) -> list[Path]:
    return [
        path
        for path in output_directory.rglob("*.gcode")
        if path.is_file() and path.stat().st_size > 0
    ]


def _validate_gcode(path: Path, profile: PrinterProfileConfiguration) -> None:
    size = path.stat().st_size
    if not 1 <= size <= _MAX_GCODE_BYTES:
        raise PrinterError("PRINTER_GCODE_SIZE_INVALID", "Generated G-code size is invalid")
    with path.open("rb") as source:
        sample = source.read(2 * 1024 * 1024).decode(errors="replace")
    lowered = sample.casefold()
    if "creality" not in lowered or "start_print" not in lowered:
        raise PrinterError(
            "PRINTER_GCODE_PROFILE_UNVERIFIED",
            "Generated G-code does not identify the expected Creality/Klipper profile",
        )
    overlap = ""
    with path.open("rb") as source:
        while raw_chunk := source.read(1024 * 1024):
            chunk = overlap + raw_chunk.decode(errors="replace")
            if re.search(r"(?im)^\s*(?:M112|FIRMWARE_RESTART)\b", chunk):
                raise PrinterError(
                    "PRINTER_GCODE_UNSAFE",
                    "Generated G-code contains a blocked command",
                )
            nozzle_values = (
                float(value)
                for value in re.findall(
                    r"(?:EXTRUDER_TEMP\s*=|M10[49]\s+S)\s*([0-9]+(?:\.[0-9]+)?)",
                    chunk,
                )
            )
            if any(value > profile.max_nozzle_celsius for value in nozzle_values):
                raise PrinterError(
                    "PRINTER_GCODE_TEMPERATURE_UNSAFE",
                    "Nozzle temperature exceeds the profile limit",
                )
            bed_values = (
                float(value)
                for value in re.findall(
                    r"(?:BED_TEMP\s*=|M1[49]0\s+S)\s*([0-9]+(?:\.[0-9]+)?)",
                    chunk,
                )
            )
            if any(value > profile.max_bed_celsius for value in bed_values):
                raise PrinterError(
                    "PRINTER_GCODE_TEMPERATURE_UNSAFE",
                    "Bed temperature exceeds the profile limit",
                )
            overlap = chunk[-256:]


def _remote_name(artifact: PrinterGcodeArtifact) -> str:
    stem = re.sub(r"[^A-Za-z0-9._ -]", "-", Path(artifact.fileName).stem)[:80]
    value = f"cit-{artifact.artifactId[:12]}-{stem or 'model'}.gcode"
    if _SAFE_REMOTE_NAME.fullmatch(value) is None:
        raise PrinterError("PRINTER_REMOTE_NAME_INVALID", "Remote print filename is invalid")
    return value


def _hash_start_token(token: str) -> str:
    if not 32 <= len(token) <= 128:
        return "invalid"
    return hashlib.sha256(b"cit-printer-start-v1\x00" + token.encode()).hexdigest()
