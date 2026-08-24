from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cit_runtime.fabric_auth import FABRIC_PERMISSIONS, FabricBootstrapIdentity
from cit_runtime.fabric_installation import FabricInstallationCatalog
from cit_runtime.fabric_service import create_fabric_app
from fastapi.testclient import TestClient

NOW = datetime(2026, 8, 24, 4, 30, 0, tzinfo=UTC)
ADMIN_TOKEN = "cit-install-admin-" + "a" * 40
OBSERVER_TOKEN = "cit-install-observer-" + "b" * 40
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
OBSERVER_HEADERS = {"Authorization": f"Bearer {OBSERVER_TOKEN}"}


def identities() -> tuple[FabricBootstrapIdentity, ...]:
    return (
        FabricBootstrapIdentity(
            identity_id="installation-admin",
            token=ADMIN_TOKEN,
            actor_type="administrator",
            roles=("administrator",),
            permissions=tuple(sorted(FABRIC_PERMISSIONS)),
        ),
        FabricBootstrapIdentity(
            identity_id="installation-observer",
            token=OBSERVER_TOKEN,
            actor_type="observer",
            roles=("observer",),
            permissions=("fabric.nodes.read",),
        ),
    )


def installation_directory(root: Path, payload: bytes = b"portable CIT setup") -> Path:
    root.mkdir()
    filename = "CITPhysicalXR-Windows-Setup-0.0.0-abcdef123456.zip"
    (root / filename).write_bytes(payload)
    manifest = {
        "schemaVersion": "1.0",
        "available": True,
        "product": "CITPhysicalXR",
        "version": "0.0.0",
        "revision": "abcdef1234567890abcdef1234567890abcdef12",
        "generatedAt": NOW.isoformat(),
        "platform": "windows-x64",
        "requiresInternet": True,
        "artifacts": [
            {
                "artifactId": "windows-transfer-online",
                "fileName": filename,
                "mediaType": "application/zip",
                "sizeBytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
    }
    (root / "installation-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_installation_catalog_is_explicitly_unavailable_without_a_manifest(
    tmp_path: Path,
) -> None:
    catalog = FabricInstallationCatalog.load(tmp_path / "not-built")

    assert catalog.directory is None
    assert catalog.info.model_dump(exclude_none=True) == {
        "schemaVersion": "1.0",
        "available": False,
        "product": "CITPhysicalXR",
        "platform": "windows-x64",
        "requiresInternet": True,
        "artifacts": [],
    }


def test_installation_catalog_fails_closed_when_artifact_digest_changes(tmp_path: Path) -> None:
    directory = installation_directory(tmp_path / "downloads")
    artifact_path = next(directory.glob("*.zip"))
    changed = bytearray(artifact_path.read_bytes())
    changed[0] ^= 0x01
    artifact_path.write_bytes(changed)

    with pytest.raises(ValueError, match="SHA-256"):
        FabricInstallationCatalog.load(directory)


def test_authenticated_installation_download_is_verified_and_audited(tmp_path: Path) -> None:
    payload = b"PK\x03\x04 test classroom setup archive"
    directory = installation_directory(tmp_path / "downloads", payload)
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=identities(),
            maintenance_interval=None,
            installation_directory=directory,
        )
    ) as client:
        unauthenticated = client.get("/api/v1/fabric/installation")
        observer = client.get(
            "/api/v1/fabric/installation",
            headers=OBSERVER_HEADERS,
        )
        info = client.get("/api/v1/fabric/installation", headers=ADMIN_HEADERS)
        download = client.get(
            "/api/v1/fabric/installation/artifacts/windows-transfer-online",
            headers=ADMIN_HEADERS,
        )
        missing = client.get(
            "/api/v1/fabric/installation/artifacts/not-present",
            headers=ADMIN_HEADERS,
        )
        audit = client.get("/api/v1/fabric/audit", headers=ADMIN_HEADERS)

    expected_hash = hashlib.sha256(payload).hexdigest()
    assert unauthenticated.status_code == 401
    assert observer.status_code == 403
    assert info.status_code == 200
    assert info.json()["available"] is True
    assert info.json()["requiresInternet"] is True
    assert info.json()["artifacts"][0]["sha256"] == expected_hash
    assert download.status_code == 200
    assert download.content == payload
    assert download.headers["content-type"].startswith("application/zip")
    assert download.headers["x-cit-sha256"] == expected_hash
    assert "CITPhysicalXR-Windows-Setup" in download.headers["content-disposition"]
    assert missing.status_code == 404
    record = next(item for item in audit.json() if item["action"] == "fabric.installation.download")
    assert record["actorId"] == "installation-admin"
    assert record["resourceId"] == "windows-transfer-online"
    assert record["details"]["sha256"] == expected_hash


def test_installation_api_reports_unavailable_before_release_build(tmp_path: Path) -> None:
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=identities(),
            maintenance_interval=None,
        )
    ) as client:
        response = client.get("/api/v1/fabric/installation", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["artifacts"] == []


def test_installation_download_fails_closed_if_artifact_changes_after_startup(
    tmp_path: Path,
) -> None:
    directory = installation_directory(tmp_path / "downloads")
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=identities(),
            maintenance_interval=None,
            installation_directory=directory,
        )
    ) as client:
        artifact_path = next(directory.glob("*.zip"))
        changed = bytearray(artifact_path.read_bytes())
        changed[-1] ^= 0x01
        artifact_path.write_bytes(changed)
        response = client.get(
            "/api/v1/fabric/installation/artifacts/windows-transfer-online",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 404
    assert response.json()["code"] == "INSTALLATION_ARTIFACT_NOT_FOUND"
