from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from cit_protocol import FabricEventEnvelope, IntegrationNode, PluginManifest
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
    course_pack_values = course_packs.json()
    assert {course_pack["coursePackId"] for course_pack in course_pack_values} == {
        "device-monitoring",
        "gesture-ground-robot",
        "glasses-agent-control",
        "simultaneous-device-cue",
        "smart-plug-control",
    }
    glasses = next(
        course_pack
        for course_pack in course_pack_values
        if course_pack["coursePackId"] == "glasses-agent-control"
    )
    simultaneous = next(
        course_pack
        for course_pack in course_pack_values
        if course_pack["coursePackId"] == "simultaneous-device-cue"
    )
    assert all("parallelGroup" not in flow for flow in glasses["flows"])
    assert {flow["parallelGroup"] for flow in simultaneous["flows"] if "parallelGroup" in flow} == {
        "simultaneous-classroom-cue"
    }


def test_monitoring_session_is_reused_for_independent_adapters(tmp_path: Path) -> None:
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=(admin_identity(),),
            maintenance_interval=None,
        )
    ) as client:
        request = {
            "siteId": "local-site",
            "roomId": "local-room",
            "mode": "simulation",
        }
        first = client.post(
            "/api/v1/fabric/monitoring/session",
            headers=ADMIN_HEADERS,
            json=request,
        )
        second = client.post(
            "/api/v1/fabric/monitoring/session",
            headers=ADMIN_HEADERS,
            json=request,
        )
        start_policy = client.get(
            f"/api/v1/fabric/sessions/{first.json()['sessionId']}/start-policy",
            headers=ADMIN_HEADERS,
        )
        sessions = client.get("/api/v1/fabric/sessions", headers=ADMIN_HEADERS)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["sessionId"] == second.json()["sessionId"]
    assert start_policy.json() == {
        "sessionId": first.json()["sessionId"],
        "requiresArming": False,
    }
    assert len(sessions.json()) == 1


def test_event_listing_can_return_the_latest_window_in_chronological_order(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "fabric.sqlite3"
    with TestClient(
        create_fabric_app(
            database_path=database_path,
            clock=lambda: NOW,
            fabric_bootstrap_identities=(admin_identity(),),
            maintenance_interval=None,
        )
    ) as client:
        session_response = client.post(
            "/api/v1/fabric/monitoring/session",
            headers=ADMIN_HEADERS,
            json={
                "siteId": "local-site",
                "roomId": "local-room",
                "mode": "simulation",
            },
        )
        session_id = session_response.json()["sessionId"]
        with SQLiteFabricRepository(database_path) as repository:
            capability = {
                "name": "telemetry.test.sequence",
                "version": "1.0",
                "direction": "publish",
                "maximumRateHz": 10,
                "latencyClass": "ui_feedback",
                "safetyClassification": "informational",
                "dataClassification": "operational",
                "constraints": {},
            }
            manifest = PluginManifest.model_validate(
                {
                    "schemaVersion": "1.0",
                    "pluginId": "cit.test-event-source",
                    "pluginVersion": "1.0.0",
                    "runtimeVersion": "1.0.0",
                    "displayName": "Test event source",
                    "adapterMode": "out_of_process",
                    "configurationSchema": {},
                    "publishedCapabilities": [capability],
                    "consumedCapabilities": [],
                    "requiredPermissions": [],
                    "safetyClassification": "informational",
                    "dataClassifications": ["operational"],
                    "simulatorAvailability": "included",
                }
            )
            repository.register_fabric_plugin(manifest, at=NOW)
            repository.upsert_fabric_node(
                IntegrationNode.model_validate(
                    {
                        "schemaVersion": "1.0",
                        "nodeId": "test-node",
                        "pluginId": manifest.pluginId,
                        "pluginVersion": manifest.pluginVersion,
                        "runtimeVersion": manifest.runtimeVersion,
                        "hostId": "test-host",
                        "siteId": "local-site",
                        "roomId": "local-room",
                        "displayName": "Test node",
                        "connectionState": "connected",
                        "healthState": "healthy",
                        "physical": False,
                        "simulated": True,
                        "publishedCapabilities": [capability],
                        "consumedCapabilities": [],
                        "configurationSchema": {},
                        "safetyClassification": "informational",
                        "dataClassifications": ["operational"],
                        "simulatorAvailable": True,
                        "requiredPermissions": [],
                        "lastSeenAt": NOW.isoformat(),
                        "metadata": {},
                    }
                ),
                at=NOW,
                lease_ttl=timedelta(minutes=5),
            )
            for sequence in range(1, 6):
                repository.append_fabric_event(
                    FabricEventEnvelope.model_validate(
                        {
                            "messageId": str(uuid5(NAMESPACE_URL, f"event-{sequence}")),
                            "schemaVersion": "1.0",
                            "messageType": "event",
                            "topic": "telemetry.test.sequence",
                            "sourceNodeId": "test-node",
                            "sourceCapability": "telemetry.test.sequence",
                            "siteId": "local-site",
                            "roomId": "local-room",
                            "sessionId": session_id,
                            "timestamp": NOW.isoformat(),
                            "monotonicTimestamp": sequence,
                            "sequence": sequence,
                            "ttlMs": 60_000,
                            "dataClassification": "operational",
                            "payload": {"sequence": sequence},
                        }
                    ),
                    received_at=NOW,
                )

        response = client.get(
            "/api/v1/fabric/events",
            headers=ADMIN_HEADERS,
            params={"sessionId": session_id, "latest": True, "limit": 3},
        )

    assert response.status_code == 200
    assert [item["event"]["payload"]["sequence"] for item in response.json()] == [3, 4, 5]


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
    assert "fabric.installation.read" in tutor.json()["permissions"]
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
