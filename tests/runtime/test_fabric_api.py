from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from cit_runtime.fabric_auth import FABRIC_PERMISSIONS, FabricAuthService, FabricBootstrapIdentity
from cit_runtime.fabric_repository import SQLiteFabricRepository
from cit_runtime.fabric_service import create_fabric_app
from fastapi.testclient import TestClient

NOW = datetime(2026, 8, 21, 3, 0, 0, tzinfo=UTC)
ADMIN_TOKEN = "cit-admin-" + "a" * 40
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def admin_identity() -> FabricBootstrapIdentity:
    return FabricBootstrapIdentity(
        identity_id="admin-a",
        token=ADMIN_TOKEN,
        actor_type="administrator",
        roles=("administrator",),
        permissions=tuple(sorted(FABRIC_PERMISSIONS)),
    )


def test_fabric_requires_independent_bearer_and_sets_security_headers(tmp_path: Path) -> None:
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=(admin_identity(),),
            maintenance_interval=None,
        )
    ) as client:
        missing = client.get("/api/v1/fabric/nodes")
        query_token = client.get(
            "/api/v1/fabric/nodes",
            params={"token": ADMIN_TOKEN},
        )
        authenticated = client.get("/api/v1/fabric/nodes", headers=ADMIN_HEADERS)
        health = client.get("/api/v1/fabric/healthz")

    assert missing.status_code == 401
    assert query_token.status_code == 401
    assert authenticated.status_code == 200
    assert authenticated.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in authenticated.headers["content-security-policy"]
    assert authenticated.headers["x-content-type-options"] == "nosniff"
    assert health.json() == {
        "status": "ok",
        "physicalActuation": "disabled",
        "mediaIngress": "disabled",
        "mediaIngressOrigin": None,
    }


def test_explicit_physical_mode_and_robot_course_are_visible(tmp_path: Path) -> None:
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=(admin_identity(),),
            allow_physical_fabric=True,
            maintenance_interval=None,
        )
    ) as client:
        health = client.get("/api/v1/fabric/healthz")
        course_packs = client.get(
            "/api/v1/fabric/course-packs",
            headers=ADMIN_HEADERS,
        )

    assert health.json() == {
        "status": "ok",
        "physicalActuation": "enabled",
        "mediaIngress": "disabled",
        "mediaIngressOrigin": None,
    }
    assert course_packs.status_code == 200
    assert {course_pack["coursePackId"] for course_pack in course_packs.json()} == {
        "gesture-ground-robot",
        "glasses-agent-control",
        "smart-plug-control",
    }


def test_fabric_console_serves_its_favicon_from_the_same_origin(tmp_path: Path) -> None:
    studio_path = tmp_path / "studio"
    (studio_path / "assets").mkdir(parents=True)
    (studio_path / "index.html").write_text("<!doctype html><title>Fabric</title>")
    (studio_path / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>',
        encoding="utf-8",
    )

    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=(admin_identity(),),
            maintenance_interval=None,
            studio_directory=studio_path,
        )
    ) as client:
        console = client.get("/fabric")
        favicon = client.get("/favicon.svg")

    assert console.status_code == 200
    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")


def test_scoped_observer_token_is_hash_only_and_cannot_mutate(tmp_path: Path) -> None:
    database_path = tmp_path / "fabric.sqlite3"
    with TestClient(
        create_fabric_app(
            database_path=database_path,
            clock=lambda: NOW,
            fabric_bootstrap_identities=(admin_identity(),),
            maintenance_interval=None,
        )
    ) as client:
        issued = client.post(
            "/api/v1/fabric/auth/identities",
            headers=ADMIN_HEADERS,
            json={
                "identityId": "observer-a",
                "actorType": "observer",
                "roles": ["observer"],
                "permissions": [
                    "fabric.course.read",
                    "fabric.nodes.read",
                    "fabric.sessions.read",
                ],
                "siteId": "local-site",
                "roomId": "local-room",
                "ttlSeconds": 3600,
            },
        )
        assert issued.status_code == 201
        observer_token = issued.json()["token"]
        observer_headers = {"Authorization": f"Bearer {observer_token}"}
        visible = client.get("/api/v1/fabric/nodes", headers=observer_headers)
        denied = client.post(
            "/api/v1/fabric/sessions",
            headers=observer_headers,
            json={
                "coursePackId": "glasses-agent-control",
                "coursePackVersion": "1.0.0",
                "siteId": "local-site",
                "roomId": "local-room",
                "mode": "simulation",
            },
        )

    with SQLiteFabricRepository(database_path) as repository:
        stored = repository.find_fabric_identity_by_hash(
            FabricAuthService.hash_token(observer_token)
        )

    assert visible.status_code == 200
    assert denied.status_code == 403
    assert stored is not None
    assert stored.token_hash != observer_token


def test_launcher_console_ticket_is_short_lived_single_use_and_tutor_scoped(
    tmp_path: Path,
) -> None:
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=(admin_identity(),),
            maintenance_interval=None,
        )
    ) as client:
        created = client.post(
            "/api/v1/fabric/auth/console-tickets",
            headers=ADMIN_HEADERS,
        )
        ticket = created.json()["ticket"]
        ticket_as_bearer = client.get(
            "/api/v1/fabric/auth/whoami",
            headers={"Authorization": f"Bearer {ticket}"},
        )
        redeemed = client.post(
            "/api/v1/fabric/auth/console-tickets/redeem",
            json={"ticket": ticket},
        )
        second_redemption = client.post(
            "/api/v1/fabric/auth/console-tickets/redeem",
            json={"ticket": ticket},
        )
        tutor_token = redeemed.json()["accessToken"]
        tutor_headers = {"Authorization": f"Bearer {tutor_token}"}
        tutor = client.get("/api/v1/fabric/auth/whoami", headers=tutor_headers)
        cannot_issue_identity = client.post(
            "/api/v1/fabric/auth/identities",
            headers=tutor_headers,
            json={
                "identityId": "should-not-exist",
                "actorType": "observer",
                "roles": ["observer"],
                "permissions": ["fabric.nodes.read"],
            },
        )

    assert created.status_code == 201
    assert created.json()["singleUse"] is True
    assert "accessToken" not in created.json()
    assert ticket_as_bearer.status_code == 401
    assert redeemed.status_code == 200
    assert second_redemption.status_code == 401
    assert tutor.status_code == 200
    assert tutor.json()["roles"] == ["instructor"]
    assert "fabric.sessions.manage" in tutor.json()["permissions"]
    assert "fabric.auth.issue" not in tutor.json()["permissions"]
    assert cannot_issue_identity.status_code == 403


def test_launcher_console_ticket_expires_before_redemption(tmp_path: Path) -> None:
    current = [NOW]
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: current[0],
            fabric_bootstrap_identities=(admin_identity(),),
            maintenance_interval=None,
        )
    ) as client:
        created = client.post(
            "/api/v1/fabric/auth/console-tickets",
            headers=ADMIN_HEADERS,
        )
        current[0] = NOW + timedelta(seconds=91)
        expired = client.post(
            "/api/v1/fabric/auth/console-tickets/redeem",
            json={"ticket": created.json()["ticket"]},
        )

    assert expired.status_code == 401


def test_session_request_rejects_duplicate_participants(tmp_path: Path) -> None:
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=(admin_identity(),),
            maintenance_interval=None,
        )
    ) as client:
        response = client.post(
            "/api/v1/fabric/sessions",
            headers=ADMIN_HEADERS,
            json={
                "coursePackId": "glasses-agent-control",
                "coursePackVersion": "1.0.0",
                "siteId": "local-site",
                "roomId": "local-room",
                "mode": "simulation",
                "participantIds": ["student-a", "student-a"],
            },
        )

    assert response.status_code == 422
