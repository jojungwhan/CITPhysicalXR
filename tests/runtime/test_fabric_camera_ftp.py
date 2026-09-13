from __future__ import annotations

import ftplib
import hashlib
import io
import json
import time
from pathlib import Path

import pytest
from cit_runtime.fabric_camera_ftp import (
    CameraFtpCredentials,
    CameraFtpReceipt,
    CameraFtpReceiptProcessor,
    CameraFtpServer,
    derive_camera_ftp_password,
)
from pydantic import ValidationError


def _receipt(name: str, payload: bytes) -> dict[str, object]:
    digest = hashlib.sha256(payload).hexdigest()
    return {
        "schemaVersion": "1.0",
        "uploadId": digest,
        "name": name,
        "sizeBytes": len(payload),
        "sha256": digest,
    }


def test_ftp_password_derivation_is_stable_and_protocol_separated() -> None:
    assert derive_camera_ftp_password("A" * 43) == ("WVuXwQziPrwfha8vLZ2hwrn5Hb1lr46FoC4XO_XFeHw")


def test_receipt_rejects_paths_and_non_media_names() -> None:
    body = _receipt("../escape.JPG", b"image")
    with pytest.raises(ValidationError):
        CameraFtpReceipt.model_validate(body)

    body["name"] = "notes.txt"
    with pytest.raises(ValidationError):
        CameraFtpReceipt.model_validate(body)


def test_processor_publishes_only_a_matching_verified_part(tmp_path: Path) -> None:
    destination = tmp_path / "Sony Camera Imports"
    incoming = destination / ".cit-ftp-incoming"
    incoming.mkdir(parents=True)
    payload = b"\xff\xd8\xff\xe0" + (b"camera-original" * 100)
    receipt = _receipt("DSC00001.JPG", payload)
    upload_id = str(receipt["uploadId"])
    (incoming / f"{upload_id}.part").write_bytes(payload)
    receipt_path = incoming / f"{upload_id}.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    result = CameraFtpReceiptProcessor(destination, incoming).process(receipt_path)

    assert result.outcome == "copied"
    assert result.path.read_bytes() == payload
    assert not (incoming / f"{upload_id}.part").exists()
    assert (incoming / f"{upload_id}.ok").is_file()
    summary = json.loads((destination / "sony-camera-ftp-summary.json").read_text())
    assert summary["verified"] is True
    assert summary["cameraFilesDeleted"] is False
    assert summary["phoneFilesDeleted"] is False
    assert summary["files"][upload_id]["sha256"] == upload_id


def test_processor_deduplicates_a_previously_verified_file(tmp_path: Path) -> None:
    destination = tmp_path / "Sony Camera Imports"
    incoming = destination / ".cit-ftp-incoming"
    incoming.mkdir(parents=True)
    payload = b"existing-camera-file"
    receipt = _receipt("C0001.MP4", payload)
    upload_id = str(receipt["uploadId"])
    (destination / "C0001.MP4").write_bytes(payload)
    (incoming / f"{upload_id}.part").write_bytes(payload)
    receipt_path = incoming / f"{upload_id}.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    result = CameraFtpReceiptProcessor(destination, incoming).process(receipt_path)

    assert result.outcome == "already_verified"
    assert list(destination.glob("C0001*.MP4")) == [destination / "C0001.MP4"]


def test_authenticated_ftp_upload_is_finalized_after_receipt(tmp_path: Path) -> None:
    destination = tmp_path / "Sony Camera Imports"
    credentials = CameraFtpCredentials(
        username="android-0123456789abcdef",
        password="camera-password",
    )
    server = CameraFtpServer(
        destination,
        bind_host="127.0.0.1",
        port=0,
        passive_ports=None,
        credentials=lambda: credentials,
    )
    payload = b"\xff\xd8\xff\xe0" + (b"ftp-camera-original" * 2_000)
    receipt = _receipt("DSC00010.JPG", payload)
    upload_id = str(receipt["uploadId"])

    server.start()
    try:
        assert server.bound_port is not None
        with ftplib.FTP() as client:
            client.connect("127.0.0.1", server.bound_port, timeout=5)
            client.login(credentials.username, credentials.password)
            client.storbinary(f"STOR {upload_id}.part", io.BytesIO(payload))
            client.storbinary(
                f"STOR {upload_id}.json",
                io.BytesIO(json.dumps(receipt).encode("utf-8")),
            )
            with pytest.raises(ftplib.error_perm):
                client.delete(f"{upload_id}.part")
        target = destination / "DSC00010.JPG"
        deadline = time.monotonic() + 5
        while not target.is_file() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert target.read_bytes() == payload

        with ftplib.FTP() as rejected:
            rejected.connect("127.0.0.1", server.bound_port, timeout=5)
            with pytest.raises(ftplib.error_perm):
                rejected.login(credentials.username, "wrong-password")
    finally:
        server.stop()


def test_ftp_server_can_restart_with_the_same_lifecycle_object(tmp_path: Path) -> None:
    credentials = CameraFtpCredentials(
        username="android-0123456789abcdef",
        password="camera-password",
    )
    server = CameraFtpServer(
        tmp_path / "Sony Camera Imports",
        bind_host="127.0.0.1",
        port=0,
        passive_ports=None,
        credentials=lambda: credentials,
    )

    server.start()
    first_port = server.bound_port
    assert first_port is not None
    with ftplib.FTP() as first_client:
        first_client.connect("127.0.0.1", first_port, timeout=5)
        first_client.login(credentials.username, credentials.password)
    server.stop()
    server.start()
    try:
        assert server.bound_port is not None
        payload = b"restarted-camera-ftp"
        receipt = _receipt("DSC00011.JPG", payload)
        upload_id = str(receipt["uploadId"])
        with ftplib.FTP() as client:
            client.connect("127.0.0.1", server.bound_port, timeout=5)
            client.login(credentials.username, credentials.password)
            client.storbinary(f"STOR {upload_id}.part", io.BytesIO(payload))
            client.storbinary(
                f"STOR {upload_id}.json",
                io.BytesIO(json.dumps(receipt).encode("utf-8")),
            )
        target = server.destination / "DSC00011.JPG"
        deadline = time.monotonic() + 2
        while not target.is_file() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert target.read_bytes() == payload
    finally:
        server.stop()
