"""Authenticated FTP ingress for camera originals staged on the Android phone.

The first-generation Sony ZV-E10 has no FTP client.  Imaging Edge Mobile is
therefore the camera-side Wi-Fi receiver, and the paired Control Tower phone
uses this narrowly scoped FTP endpoint for the second wireless hop.  Uploads
land as resumable parts and are made visible only after a SHA-256 receipt has
been validated.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pyftpdlib.authorizers import AuthenticationFailed
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

CAMERA_FTP_PORT = 2121
CAMERA_FTP_PASSIVE_PORTS = range(32100, 32110)
CAMERA_FTP_PASSWORD_DOMAIN = b"cit-control-tower-camera-ftp-v1"
CAMERA_MEDIA_SUFFIXES = frozenset(
    {".arw", ".heic", ".heif", ".hif", ".jpeg", ".jpg", ".m2ts", ".mov", ".mp4", ".mts"}
)
_DEVICE_ID = re.compile(r"^android-[a-f0-9]{16}$")
_UPLOAD_ID = re.compile(r"^[a-f0-9]{64}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True, slots=True)
class CameraFtpCredentials:
    """A short-lived view of credentials derived from the paired phone."""

    username: str
    password: str


def derive_camera_ftp_password(secret: str) -> str:
    """Derive a protocol-specific password without storing another secret."""

    digest = hmac.new(
        secret.encode("ascii"),
        CAMERA_FTP_PASSWORD_DOMAIN,
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class CameraFtpReceipt(BaseModel):
    """Phone assertion that one resumable part has completely uploaded."""

    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["1.0"] = "1.0"
    uploadId: str
    name: str = Field(min_length=1, max_length=180)
    sizeBytes: int = Field(ge=0, le=2**63 - 1)
    sha256: str

    @field_validator("uploadId")
    @classmethod
    def validate_upload_id(cls, value: str) -> str:
        normalized = value.casefold()
        if _UPLOAD_ID.fullmatch(normalized) is None:
            raise ValueError("uploadId is invalid")
        return normalized

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if (
            value != Path(value).name
            or value in {".", ".."}
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
            or Path(value).suffix.casefold() not in CAMERA_MEDIA_SUFFIXES
        ):
            raise ValueError("name must be one supported media filename")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.casefold()
        if _SHA256.fullmatch(normalized) is None:
            raise ValueError("sha256 is invalid")
        return normalized


@dataclass(frozen=True, slots=True)
class CameraFtpFinalizedFile:
    upload_id: str
    name: str
    path: Path
    size_bytes: int
    sha256: str
    outcome: Literal["copied", "already_verified"]


CredentialProvider = Callable[[], CameraFtpCredentials | None]


class _DynamicCameraAuthorizer:
    """Minimal pyftpdlib authorizer backed by the current paired phone."""

    def __init__(self, home: Path, credentials: CredentialProvider) -> None:
        self._home = str(home.resolve())
        self._credentials = credentials

    def validate_authentication(
        self,
        username: str,
        password: str,
        _handler: FTPHandler,
    ) -> None:
        expected = self._credentials()
        if (
            expected is None
            or not hmac.compare_digest(username, expected.username)
            or not hmac.compare_digest(password, expected.password)
        ):
            raise AuthenticationFailed("Authentication failed")

    def get_home_dir(self, _username: str) -> str:
        return self._home

    @staticmethod
    def get_msg_login(_username: str) -> str:
        return "Control Tower camera FTP ready"

    @staticmethod
    def get_msg_quit(_username: str) -> str:
        return "Camera FTP session closed"

    @staticmethod
    def has_user(username: str) -> bool:
        return _DEVICE_ID.fullmatch(username) is not None

    @staticmethod
    def has_perm(_username: str, perm: str, path: str | None = None) -> bool:
        del path
        return all(item in "elw" for item in perm)

    @staticmethod
    def get_perms(_username: str) -> str:
        return "elw"

    @staticmethod
    def impersonate_user(_username: str, _password: str) -> None:
        return

    @staticmethod
    def terminate_impersonation(_username: str) -> None:
        return


class CameraFtpReceiptProcessor:
    """Verify completed parts and publish them atomically in the Sony folder."""

    def __init__(self, destination: Path, incoming: Path) -> None:
        self.destination = destination.resolve()
        self.incoming = incoming.resolve()
        self.summary_path = self.destination / "sony-camera-ftp-summary.json"
        self._lock = threading.RLock()

    def process(self, receipt_path: Path) -> CameraFtpFinalizedFile:
        resolved_receipt = receipt_path.resolve()
        if resolved_receipt.parent != self.incoming or resolved_receipt.suffix != ".json":
            raise ValueError("Receipt is outside the camera FTP staging directory")
        if resolved_receipt.stat().st_size > 16_384:
            raise ValueError("Camera FTP receipt is too large")
        receipt = CameraFtpReceipt.model_validate_json(resolved_receipt.read_text(encoding="utf-8"))
        if resolved_receipt.stem != receipt.uploadId:
            raise ValueError("Receipt filename does not match uploadId")
        part = (self.incoming / f"{receipt.uploadId}.part").resolve()
        if part.parent != self.incoming or not part.is_file():
            raise ValueError("Camera FTP upload part is missing")
        if part.stat().st_size != receipt.sizeBytes:
            raise ValueError("Camera FTP upload size does not match its receipt")
        actual_hash = self._hash_file(part)
        if not hmac.compare_digest(actual_hash, receipt.sha256):
            raise ValueError("Camera FTP upload checksum does not match its receipt")

        with self._lock:
            target = self.destination / receipt.name
            outcome: Literal["copied", "already_verified"] = "copied"
            if target.is_file() and self._matches(target, receipt):
                part.unlink()
                outcome = "already_verified"
            else:
                if target.exists():
                    target = self._collision_target(target, receipt)
                if target.is_file() and self._matches(target, receipt):
                    part.unlink()
                    outcome = "already_verified"
                else:
                    os.replace(part, target)
                self._write_summary(receipt, target, outcome)
            if outcome == "already_verified":
                self._write_summary(receipt, target, outcome)
            acknowledgement = self.incoming / f"{receipt.uploadId}.ok"
            temporary_acknowledgement = acknowledgement.with_suffix(".ok.tmp")
            temporary_acknowledgement.write_text(
                json.dumps(
                    {
                        "schemaVersion": "1.0",
                        "name": target.name,
                        "sizeBytes": receipt.sizeBytes,
                        "sha256": receipt.sha256,
                        "outcome": outcome,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            os.replace(temporary_acknowledgement, acknowledgement)
            resolved_receipt.unlink()
        return CameraFtpFinalizedFile(
            upload_id=receipt.uploadId,
            name=receipt.name,
            path=target,
            size_bytes=receipt.sizeBytes,
            sha256=receipt.sha256,
            outcome=outcome,
        )

    def _collision_target(self, target: Path, receipt: CameraFtpReceipt) -> Path:
        suffix = receipt.sha256[:8]
        candidate = target.with_name(f"{target.stem}__{suffix}{target.suffix}")
        index = 2
        while candidate.exists() and not self._matches(candidate, receipt):
            candidate = target.with_name(f"{target.stem}__{suffix}_{index}{target.suffix}")
            index += 1
        return candidate

    def _matches(self, path: Path, receipt: CameraFtpReceipt) -> bool:
        return (
            path.is_file()
            and path.stat().st_size == receipt.sizeBytes
            and hmac.compare_digest(self._hash_file(path), receipt.sha256)
        )

    def _write_summary(
        self,
        receipt: CameraFtpReceipt,
        target: Path,
        outcome: Literal["copied", "already_verified"],
    ) -> None:
        current: dict[str, object] = {}
        if self.summary_path.is_file():
            try:
                loaded = json.loads(self.summary_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    current = loaded
            except (OSError, ValueError, json.JSONDecodeError):
                current = {}
        files = current.get("files")
        if not isinstance(files, dict):
            files = {}
        files[receipt.uploadId] = {
            "name": target.name,
            "sizeBytes": receipt.sizeBytes,
            "sha256": receipt.sha256,
            "outcome": outcome,
            "verifiedAt": datetime.now(UTC).isoformat(),
        }
        summary = {
            "schemaVersion": "1.0",
            "source": "Sony ZV-E10 via Imaging Edge Mobile and authenticated FTP",
            "verified": True,
            "cameraFilesDeleted": False,
            "phoneFilesDeleted": False,
            "fileCount": len(files),
            "files": files,
        }
        temporary = self.summary_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.summary_path)

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()


class CameraFtpServer:
    """Lifecycle wrapper for a LAN-bound, phone-authenticated FTP receiver."""

    def __init__(
        self,
        destination: Path,
        *,
        bind_host: str,
        credentials: CredentialProvider,
        port: int = CAMERA_FTP_PORT,
        passive_ports: range | None = CAMERA_FTP_PASSIVE_PORTS,
    ) -> None:
        if not 0 <= port <= 65_535:
            raise ValueError("Camera FTP port must be between 0 and 65535")
        if passive_ports is not None and (
            not passive_ports or any(not 1024 <= item <= 65_535 for item in passive_ports)
        ):
            raise ValueError("Camera FTP passive ports must be non-empty and unprivileged")
        self.destination = destination.resolve()
        self.incoming = self.destination / ".cit-ftp-incoming"
        self.bind_host = bind_host
        self.port = port
        self.passive_ports = tuple(passive_ports) if passive_ports is not None else None
        self._credentials = credentials
        self._processor = CameraFtpReceiptProcessor(self.destination, self.incoming)
        self._server: FTPServer | None = None
        self._thread: threading.Thread | None = None
        self._receipt_workers: ThreadPoolExecutor | None = None

    @property
    def bound_port(self) -> int | None:
        server = self._server
        if server is None:
            return None
        return int(server.socket.getsockname()[1])

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self.destination.mkdir(parents=True, exist_ok=True)
        self.incoming.mkdir(parents=True, exist_ok=True)
        processor = self._processor
        receipt_workers = ThreadPoolExecutor(max_workers=1, thread_name_prefix="camera-ftp")

        class CameraUploadHandler(FTPHandler):  # type: ignore[misc]
            def on_file_received(self, file: str) -> None:
                path = Path(file)
                if path.suffix == ".json":
                    receipt_workers.submit(
                        processor.process,
                        path,
                    )

        CameraUploadHandler.authorizer = _DynamicCameraAuthorizer(
            self.incoming,
            self._credentials,
        )
        CameraUploadHandler.passive_ports = self.passive_ports
        CameraUploadHandler.banner = "CIT Control Tower camera FTP"
        try:
            server = FTPServer((self.bind_host, self.port), CameraUploadHandler)
        except Exception:
            receipt_workers.shutdown(wait=False, cancel_futures=True)
            raise
        self._receipt_workers = receipt_workers
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"timeout": 0.2, "blocking": True, "handle_exit": False},
            name="control-tower-camera-ftp",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        receipt_workers = self._receipt_workers
        self._server = None
        self._thread = None
        self._receipt_workers = None
        if server is not None:
            server.close_all()
        if thread is not None:
            thread.join(timeout=5)
        if receipt_workers is not None:
            receipt_workers.shutdown(wait=True, cancel_futures=False)
