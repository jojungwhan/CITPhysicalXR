from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cit_protocol import IntegrationNode
from cit_runtime.fabric_auth import FABRIC_PERMISSIONS, FabricBootstrapIdentity
from cit_runtime.fabric_discovery import (
    FabricDiscoveryError,
    FabricDiscoveryReport,
    FabricDiscoveryService,
    PowerShellDiscoveryRunner,
    initial_discovery_report,
)
from cit_runtime.fabric_service import create_fabric_app
from fastapi.testclient import TestClient

NOW = datetime(2026, 8, 21, 7, 0, 0, tzinfo=UTC)
ADMIN_TOKEN = "cit-discovery-admin-" + "a" * 40
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


class FakeDiscoveryRunner:
    def __init__(self) -> None:
        self.scans = 0
        self.actions: list[tuple[str, bool]] = []

    async def scan(self) -> FabricDiscoveryReport:
        self.scans += 1
        report = initial_discovery_report(at=NOW)
        integrations = [
            integration.model_copy(
                update={
                    "status": "found",
                    "summary": "A test device was found.",
                }
            )
            if integration.integrationId == "leap-motion"
            else integration
            for integration in report.integrations
        ]
        return report.model_copy(
            update={
                "scanId": f"scan-{self.scans}",
                "integrations": integrations,
            }
        )

    async def perform(self, action_id: str, *, confirm_grounded: bool) -> str:
        self.actions.append((action_id, confirm_grounded))
        if action_id == "brain2devices.tello.connect-all" and not confirm_grounded:
            raise FabricDiscoveryError(
                "GROUNDED_CONFIRMATION_REQUIRED",
                "Grounded confirmation is required",
            )
        if action_id not in {
            "brain2devices.tello.connect-all",
            "brain2devices.mindwave.connect",
        }:
            raise FabricDiscoveryError(
                "DISCOVERY_ACTION_NOT_ALLOWED",
                "Action is not allowlisted",
            )
        return "Connection started; no actuation command was sent."


def admin_identity() -> FabricBootstrapIdentity:
    return FabricBootstrapIdentity(
        identity_id="discovery-admin",
        token=ADMIN_TOKEN,
        actor_type="administrator",
        roles=("administrator",),
        permissions=tuple(sorted(FABRIC_PERMISSIONS)),
    )


def leap_node() -> IntegrationNode:
    return IntegrationNode.model_validate(
        {
            "schemaVersion": "1.0",
            "nodeId": "leap-motion-test",
            "pluginId": "cit.robomaster-gesture-control",
            "pluginVersion": "0.1.0",
            "runtimeVersion": "python-3.11",
            "displayName": "Test Leap Motion",
            "hostId": "test-host",
            "siteId": "local-site",
            "roomId": "local-room",
            "connectionState": "connected",
            "healthState": "healthy",
            "physical": True,
            "simulated": False,
            "publishedCapabilities": [],
            "consumedCapabilities": [],
            "configurationSchema": {},
            "safetyClassification": "informational",
            "dataClassifications": ["operational"],
            "simulatorAvailable": True,
            "requiredPermissions": [],
            "lastSeenAt": NOW,
            "metadata": {"model": "ultraleap-leap-motion"},
        }
    )


def test_discovery_overlays_live_nodes_without_claiming_other_devices() -> None:
    runner = FakeDiscoveryRunner()
    service = FabricDiscoveryService(runner, clock=lambda: NOW)

    initial = service.current((leap_node(),))

    leap = next(item for item in initial.integrations if item.integrationId == "leap-motion")
    robot = next(item for item in initial.integrations if item.integrationId == "robomaster-s1")
    assert leap.status == "connected"
    assert leap.connectedNodeIds == ["leap-motion-test"]
    assert robot.status == "not_scanned"


def test_fixed_adapter_connection_actions_use_disarmed_launchers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = PowerShellDiscoveryRunner(
        script_path=Path(__file__).resolve().parents[2]
        / "tools"
        / "hardware"
        / "find-classroom-devices.ps1",
        state_root=tmp_path / "fabric",
        brain2devices_root=tmp_path / "brain",
        robomaster_root=tmp_path / "robot",
        fabric_port=9876,
        powershell_path="pwsh",
    )
    launches: list[tuple[str, tuple[str, ...]]] = []

    async def capture_launcher(script_name: str, *arguments: str) -> None:
        launches.append((script_name, arguments))

    monkeypatch.setattr(runner, "_run_launcher", capture_launcher)

    async def connect() -> None:
        await runner.perform("cit.glasses-agent.connect", confirm_grounded=False)
        await runner.perform("cit.robomaster-leap.connect", confirm_grounded=False)
        await runner.perform("cit.smart-plug.connect", confirm_grounded=False)

    asyncio.run(connect())

    assert launches[0][0] == "glasses-agent-hardware-test.ps1"
    assert "-SelectMostRecentAgentSession" in launches[0][1]
    assert launches[1][0] == "robomaster-leap-hardware-test.ps1"
    assert "-ConnectOnly" in launches[1][1]
    assert "-Live" in launches[1][1]
    assert launches[2][0] == "smart-plug-hardware-test.ps1"
    assert "-ConnectOnly" in launches[2][1]
    assert all("-NoOpenConsole" in arguments for _, arguments in launches)


def test_authenticated_scan_and_allowlisted_connection_are_audited(tmp_path: Path) -> None:
    runner = FakeDiscoveryRunner()
    discovery = FabricDiscoveryService(runner, clock=lambda: NOW)
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=(admin_identity(),),
            maintenance_interval=None,
            discovery_service=discovery,
        )
    ) as client:
        missing = client.post("/api/v1/fabric/discovery/scan")
        not_scanned = client.get(
            "/api/v1/fabric/discovery",
            headers=ADMIN_HEADERS,
        )
        scanned = client.post(
            "/api/v1/fabric/discovery/scan",
            headers=ADMIN_HEADERS,
        )
        unconfirmed = client.post(
            "/api/v1/fabric/discovery/actions/brain2devices.tello.connect-all",
            headers=ADMIN_HEADERS,
            json={"confirmGrounded": False},
        )
        connected = client.post(
            "/api/v1/fabric/discovery/actions/brain2devices.tello.connect-all",
            headers=ADMIN_HEADERS,
            json={"confirmGrounded": True},
        )
        arbitrary = client.post(
            "/api/v1/fabric/discovery/actions/shell.run",
            headers=ADMIN_HEADERS,
            json={"confirmGrounded": True},
        )
        audit = client.get("/api/v1/fabric/audit?limit=50", headers=ADMIN_HEADERS)

    assert missing.status_code == 401
    assert not_scanned.status_code == 200
    assert "actionId" not in not_scanned.json()["integrations"][0]
    assert "setupCommand" not in not_scanned.json()["integrations"][0]
    assert scanned.status_code == 200
    assert scanned.json()["scanId"] == "scan-1"
    assert len(scanned.json()["integrations"]) == 8
    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["code"] == "GROUNDED_CONFIRMATION_REQUIRED"
    assert connected.status_code == 200
    assert connected.json()["accepted"] is True
    assert arbitrary.status_code == 409
    assert arbitrary.json()["code"] == "DISCOVERY_ACTION_NOT_ALLOWED"
    assert runner.actions == [
        ("brain2devices.tello.connect-all", False),
        ("brain2devices.tello.connect-all", True),
        ("shell.run", True),
    ]
    actions = [record["action"] for record in audit.json()]
    assert "fabric.discovery.scan" in actions
    assert "fabric.discovery.connect" in actions


def test_observer_can_scan_but_cannot_start_a_connection(tmp_path: Path) -> None:
    runner = FakeDiscoveryRunner()
    discovery = FabricDiscoveryService(runner, clock=lambda: NOW)
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=(admin_identity(),),
            maintenance_interval=None,
            discovery_service=discovery,
        )
    ) as client:
        issued = client.post(
            "/api/v1/fabric/auth/identities",
            headers=ADMIN_HEADERS,
            json={
                "identityId": "discovery-observer",
                "actorType": "observer",
                "roles": ["observer"],
                "permissions": ["fabric.nodes.read"],
                "ttlSeconds": 3_600,
            },
        )
        observer_headers = {"Authorization": f"Bearer {issued.json()['token']}"}
        scanned = client.post(
            "/api/v1/fabric/discovery/scan",
            headers=observer_headers,
        )
        denied = client.post(
            "/api/v1/fabric/discovery/actions/brain2devices.mindwave.connect",
            headers=observer_headers,
            json={},
        )

    assert scanned.status_code == 200
    assert denied.status_code == 403
    assert runner.actions == []
