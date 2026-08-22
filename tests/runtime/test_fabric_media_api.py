from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cit_runtime.fabric_media as fabric_media_module
import pytest
from cit_runtime.fabric_auth import FABRIC_PERMISSIONS, FabricBootstrapIdentity
from cit_runtime.fabric_media import MediaFrame, ObjectDetection, VisionAnalysis
from cit_runtime.fabric_service import create_fabric_app
from fastapi.testclient import TestClient

NOW = datetime(2026, 8, 22, 5, 0, 0, tzinfo=UTC)
ADMIN_TOKEN = "cit-media-admin-" + "a" * 36
PUBLISHER_TOKEN = "cit-meta-camera-" + "b" * 36
OBSERVER_TOKEN = "cit-observer-" + "c" * 36
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
PUBLISHER_HEADERS = {"Authorization": f"Bearer {PUBLISHER_TOKEN}"}
OBSERVER_HEADERS = {"Authorization": f"Bearer {OBSERVER_TOKEN}"}
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_yolo_world_loader_supports_lazy_module_exports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = object()

    class LazyUltralyticsModule:
        def __getattr__(self, name: str) -> object:
            if name == "YOLOWorld":
                return marker
            raise AttributeError(name)

    lazy_module = LazyUltralyticsModule()
    monkeypatch.setattr("importlib.import_module", lambda name: lazy_module)

    assert fabric_media_module._load_yolo_world() is marker


class FakeVisionDetector:
    @property
    def name(self) -> str:
        return "fake-yolo-world.pt"

    @property
    def labels(self) -> tuple[str, ...]:
        return ("lamp", "drone")

    @property
    def minimum_confidence(self) -> float:
        return 0.2

    async def analyze(self, frame: MediaFrame, *, at: datetime) -> VisionAnalysis:
        return VisionAnalysis(
            source_id=frame.source_id,
            frame_sequence=frame.sequence,
            analyzed_at=at,
            model=self.name,
            labels=self.labels,
            detections=(
                ObjectDetection(
                    label="lamp",
                    confidence=0.91,
                    x1=0,
                    y1=0,
                    x2=1,
                    y2=1,
                ),
            ),
        )


def identities() -> tuple[FabricBootstrapIdentity, ...]:
    return (
        FabricBootstrapIdentity(
            identity_id="admin",
            token=ADMIN_TOKEN,
            actor_type="administrator",
            roles=("administrator",),
            permissions=tuple(sorted(FABRIC_PERMISSIONS)),
        ),
        FabricBootstrapIdentity(
            identity_id="meta-phone",
            token=PUBLISHER_TOKEN,
            actor_type="adapter",
            roles=("adapter",),
            permissions=("fabric.media.publish",),
            site_id="cit-site",
            room_id="room-a",
        ),
        FabricBootstrapIdentity(
            identity_id="observer",
            token=OBSERVER_TOKEN,
            actor_type="observer",
            roles=("observer",),
            permissions=("fabric.nodes.read",),
        ),
    )


def test_meta_snapshot_is_ephemeral_authenticated_and_analyzable(tmp_path: Path) -> None:
    app = create_fabric_app(
        database_path=tmp_path / "fabric.sqlite3",
        clock=lambda: NOW,
        fabric_bootstrap_identities=identities(),
        maintenance_interval=None,
        vision_detector=FakeVisionDetector(),
    )
    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/fabric/media/sources",
            headers=PUBLISHER_HEADERS,
            json={
                "sourceId": "meta-room-a",
                "displayName": "Tutor Meta glasses",
                "kind": "meta_glasses",
                "captureMode": "snapshot",
                "siteId": "cit-site",
                "roomId": "room-a",
                "nodeId": "meta-phone-01",
            },
        )
        published = client.put(
            "/api/v1/fabric/media/sources/meta-room-a/frame",
            headers={
                **PUBLISHER_HEADERS,
                "Content-Type": "image/png",
                "X-CIT-Captured-At": NOW.isoformat(),
            },
            content=PNG_1X1,
        )
        sources = client.get("/api/v1/fabric/media/sources", headers=ADMIN_HEADERS)
        frame = client.get(
            "/api/v1/fabric/media/sources/meta-room-a/frame",
            headers=ADMIN_HEADERS,
        )
        unchanged = client.get(
            "/api/v1/fabric/media/sources/meta-room-a/frame",
            headers={**ADMIN_HEADERS, "If-None-Match": frame.headers["etag"]},
        )
        analysis = client.post(
            "/api/v1/fabric/media/sources/meta-room-a/analyze",
            headers=ADMIN_HEADERS,
        )
        vision_status = client.get(
            "/api/v1/fabric/vision/status",
            headers=ADMIN_HEADERS,
        )

    assert registered.status_code == 201
    assert published.status_code == 202
    assert published.json()["frameSequence"] == 1
    assert sources.status_code == 200
    assert (
        sources.json()[0]
        | {
            "state": "online",
            "frameSequence": 1,
            "width": 1,
            "height": 1,
        }
        == sources.json()[0]
    )
    assert frame.status_code == 200
    assert frame.content == PNG_1X1
    assert frame.headers["cache-control"] == "no-store"
    assert unchanged.status_code == 304
    assert unchanged.content == b""
    assert analysis.status_code == 200
    assert analysis.json()["detections"] == [
        {
            "label": "lamp",
            "confidence": 0.91,
            "box": {"x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0},
        }
    ]
    assert vision_status.status_code == 200
    assert vision_status.json()["minimumConfidence"] == 0.2


def test_live_video_source_reuses_the_bounded_latest_frame_contract(tmp_path: Path) -> None:
    app = create_fabric_app(
        database_path=tmp_path / "fabric.sqlite3",
        clock=lambda: NOW,
        fabric_bootstrap_identities=identities(),
        maintenance_interval=None,
        vision_detector=FakeVisionDetector(),
    )
    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/fabric/media/sources",
            headers=PUBLISHER_HEADERS,
            json={
                "sourceId": "meta-live-room-a",
                "displayName": "Tutor Meta live camera",
                "kind": "meta_glasses",
                "captureMode": "video",
                "siteId": "cit-site",
                "roomId": "room-a",
            },
        )
        first = client.put(
            "/api/v1/fabric/media/sources/meta-live-room-a/frame",
            headers={**PUBLISHER_HEADERS, "Content-Type": "image/png"},
            content=PNG_1X1,
        )
        second = client.put(
            "/api/v1/fabric/media/sources/meta-live-room-a/frame",
            headers={**PUBLISHER_HEADERS, "Content-Type": "image/png"},
            content=PNG_1X1,
        )
        sources = client.get("/api/v1/fabric/media/sources", headers=ADMIN_HEADERS)

    assert registered.status_code == 201
    assert registered.json()["captureMode"] == "video"
    assert first.status_code == 202
    assert first.json()["frameSequence"] == 1
    assert second.status_code == 202
    assert second.json()["frameSequence"] == 2
    assert sources.json()[0]["captureMode"] == "video"
    assert sources.json()[0]["frameSequence"] == 2


def test_media_is_not_public_and_one_publisher_cannot_take_another_source(
    tmp_path: Path,
) -> None:
    second_token = "cit-second-camera-" + "d" * 36
    second = FabricBootstrapIdentity(
        identity_id="second-phone",
        token=second_token,
        actor_type="adapter",
        roles=("adapter",),
        permissions=("fabric.media.publish",),
        site_id="cit-site",
        room_id="room-a",
    )
    app = create_fabric_app(
        database_path=tmp_path / "fabric.sqlite3",
        clock=lambda: NOW,
        fabric_bootstrap_identities=(*identities(), second),
        maintenance_interval=None,
        vision_detector=FakeVisionDetector(),
    )
    registration = {
        "sourceId": "meta-room-a",
        "displayName": "Tutor Meta glasses",
        "kind": "meta_glasses",
        "captureMode": "snapshot",
        "siteId": "cit-site",
        "roomId": "room-a",
    }
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/fabric/media/sources",
                headers=PUBLISHER_HEADERS,
                json=registration,
            ).status_code
            == 201
        )
        unauthenticated = client.get("/api/v1/fabric/media/sources")
        observer = client.get(
            "/api/v1/fabric/media/sources",
            headers=OBSERVER_HEADERS,
        )
        takeover = client.post(
            "/api/v1/fabric/media/sources",
            headers={"Authorization": f"Bearer {second_token}"},
            json=registration,
        )
        wrong_type = client.put(
            "/api/v1/fabric/media/sources/meta-room-a/frame",
            headers={**PUBLISHER_HEADERS, "Content-Type": "video/mp4"},
            content=PNG_1X1,
        )

    assert unauthenticated.status_code == 401
    assert observer.status_code == 403
    assert takeover.status_code == 409
    assert takeover.json()["code"] == "MEDIA_SOURCE_OWNED"
    assert wrong_type.status_code == 415
    assert wrong_type.json()["code"] == "MEDIA_TYPE_UNSUPPORTED"


def test_media_registry_does_not_survive_a_service_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "fabric.sqlite3"
    first_app = create_fabric_app(
        database_path=database_path,
        clock=lambda: NOW,
        fabric_bootstrap_identities=identities(),
        maintenance_interval=None,
        vision_detector=FakeVisionDetector(),
    )
    with TestClient(first_app) as client:
        client.post(
            "/api/v1/fabric/media/sources",
            headers=PUBLISHER_HEADERS,
            json={
                "sourceId": "meta-room-a",
                "displayName": "Tutor Meta glasses",
                "kind": "meta_glasses",
                "captureMode": "snapshot",
                "siteId": "cit-site",
                "roomId": "room-a",
            },
        )

    second_app = create_fabric_app(
        database_path=database_path,
        clock=lambda: NOW,
        fabric_bootstrap_identities=identities(),
        maintenance_interval=None,
        vision_detector=FakeVisionDetector(),
    )
    with TestClient(second_app) as client:
        sources = client.get("/api/v1/fabric/media/sources", headers=ADMIN_HEADERS)

    assert sources.status_code == 200
    assert sources.json() == []


def test_tutor_issues_single_use_scoped_meta_camera_pairing(tmp_path: Path) -> None:
    database_path = tmp_path / "fabric.sqlite3"
    current = [NOW]
    app = create_fabric_app(
        database_path=database_path,
        clock=lambda: current[0],
        fabric_bootstrap_identities=identities(),
        maintenance_interval=None,
        vision_detector=FakeVisionDetector(),
        media_ingress_origin="http://192.168.10.20:8766",
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/fabric/media/pairings",
            headers=ADMIN_HEADERS,
            json={"siteId": "cit-site", "roomId": "room-a"},
        )
        pairing_code = created.json()["pairingCode"]
        invalid = client.post(
            "/api/v1/fabric/media/pairings/redeem",
            json={"pairingCode": "x" * 24},
        )
        redeemed = client.post(
            "/api/v1/fabric/media/pairings/redeem",
            json={"pairingCode": pairing_code},
        )
        publisher_token = redeemed.json()["accessToken"]
        publisher_headers = {"Authorization": f"Bearer {publisher_token}"}
        principal = client.get(
            "/api/v1/fabric/auth/whoami",
            headers=publisher_headers,
        )
        registered = client.post(
            "/api/v1/fabric/media/sources",
            headers=publisher_headers,
            json={
                "sourceId": "paired-meta-camera",
                "displayName": "Paired Meta glasses",
                "kind": "meta_glasses",
                "captureMode": "snapshot",
                "siteId": "cit-site",
                "roomId": "room-a",
            },
        )
        wrong_room = client.post(
            "/api/v1/fabric/media/sources",
            headers=publisher_headers,
            json={
                "sourceId": "paired-meta-camera-wrong-room",
                "displayName": "Wrong room",
                "kind": "meta_glasses",
                "captureMode": "snapshot",
                "siteId": "cit-site",
                "roomId": "room-b",
            },
        )
        publisher_read = client.get(
            "/api/v1/fabric/media/sources",
            headers=publisher_headers,
        )
        reused = client.post(
            "/api/v1/fabric/media/pairings/redeem",
            json={"pairingCode": pairing_code},
        )
        current[0] = NOW + timedelta(minutes=6)
        expired_code = client.post(
            "/api/v1/fabric/media/pairings",
            headers=ADMIN_HEADERS,
            json={"siteId": "cit-site", "roomId": "room-a"},
        ).json()["pairingCode"]
        current[0] += timedelta(minutes=6)
        expired = client.post(
            "/api/v1/fabric/media/pairings/redeem",
            json={"pairingCode": expired_code},
        )

    assert created.status_code == 201
    assert created.json()["fabricOrigin"] == "http://192.168.10.20:8766"
    assert created.json()["singleUse"] is True
    assert invalid.status_code == 401
    assert redeemed.status_code == 200
    assert redeemed.json()["permissions"] == ["fabric.media.publish"]
    assert principal.status_code == 200
    assert principal.json()["permissions"] == ["fabric.media.publish"]
    assert principal.json()["siteId"] == "cit-site"
    assert principal.json()["roomId"] == "room-a"
    assert registered.status_code == 201
    assert wrong_room.status_code == 403
    assert publisher_read.status_code == 403
    assert reused.status_code == 401
    assert expired.status_code == 401
    database_bytes = database_path.read_bytes()
    assert pairing_code.encode() not in database_bytes
    assert publisher_token.encode() not in database_bytes
