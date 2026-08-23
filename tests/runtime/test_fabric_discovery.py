from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cit_protocol import IntegrationNode
from cit_runtime.fabric_auth import FABRIC_PERMISSIONS, FabricBootstrapIdentity
from cit_runtime.fabric_discovery import (
    FabricDiscoveryCandidate,
    FabricDiscoveryError,
    FabricDiscoveryReport,
    FabricDiscoveryService,
    LegoConnectionConfiguration,
    PowerShellDiscoveryRunner,
    WonderWorkshopConnectionConfiguration,
    _ProcessOutputTooLarge,
    _read_bounded_stream,
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
        self.matter_codes: list[str] = []
        self.lego_configurations: list[LegoConnectionConfiguration] = []
        self.wonder_configurations: list[WonderWorkshopConnectionConfiguration] = []

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

    async def commission_matter(self, setup_code: str) -> str:
        self.matter_codes.append(setup_code)
        return "Matter plug commissioned locally."

    async def connect_lego(self, configuration: LegoConnectionConfiguration) -> str:
        self.lego_configurations.append(configuration)
        return "LEGO hub connected for sensor monitoring."

    async def connect_wonder_workshop(
        self, configuration: WonderWorkshopConnectionConfiguration
    ) -> str:
        self.wonder_configurations.append(configuration)
        return "Selected Dash and Dot robots connected for sensor monitoring."


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
    sphero = next(item for item in initial.integrations if item.integrationId == "sphero-bolt")
    assert leap.status == "connected"
    assert leap.ioType == "input"
    assert leap.connectedNodeIds == ["leap-motion-test"]
    assert robot.status == "not_scanned"
    assert robot.ioType == "bidirectional"
    assert sphero.status == "not_scanned"
    assert sphero.ioType == "bidirectional"
    assert sphero.icon == "sphero"


def test_discovery_candidate_preserves_bounded_connection_evidence() -> None:
    candidate = FabricDiscoveryCandidate.model_validate(
        {
            "candidateId": "android-bridge-1",
            "displayName": "Android phone",
            "transport": "Android phone / Wi-Fi",
            "status": "found",
            "detail": "An approved companion is available.",
            "connectionPath": "android_wifi",
            "linkState": "connected",
        }
    )

    assert candidate.connectionPath == "android_wifi"
    assert candidate.linkState == "connected"


def test_discovery_candidate_rejects_unbounded_connection_labels() -> None:
    with pytest.raises(ValueError):
        FabricDiscoveryCandidate.model_validate(
            {
                "candidateId": "unsafe-candidate",
                "displayName": "Untrusted result",
                "transport": "unknown",
                "status": "found",
                "detail": "An invalid caller-defined state.",
                "connectionPath": "arbitrary_vendor_tunnel",
                "linkState": "definitely_safe",
            }
        )


@pytest.mark.asyncio
async def test_launcher_output_is_rejected_while_streaming_past_its_limit() -> None:
    stream = asyncio.StreamReader()
    stream.feed_data(b"diagnostic-output")
    stream.feed_eof()

    with pytest.raises(_ProcessOutputTooLarge):
        await _read_bounded_stream(stream, limit=8)


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
        agent_mesh_root=tmp_path / "agent-mesh",
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
        await runner.perform("cit.matter-smart-plug.connect", confirm_grounded=False)

    asyncio.run(connect())

    assert launches[0][0] == "glasses-agent-hardware-test.ps1"
    assert "-SelectMostRecentAgentSession" in launches[0][1]
    assert launches[1][0] == "robomaster-leap-hardware-test.ps1"
    assert "-ConnectOnly" in launches[1][1]
    assert "-Live" in launches[1][1]
    assert launches[2][0] == "matter-smart-plug.ps1"
    assert "-SkipBuild" in launches[2][1]
    assert all("-NoOpenConsole" in arguments for _, arguments in launches)
    component_state_roots = []
    for _, arguments in launches[:2]:
        state_index = arguments.index("-StateRoot")
        component_state_roots.append(Path(arguments[state_index + 1]))
    assert component_state_roots == [
        tmp_path / "glasses-agent",
        tmp_path / "robomaster-leap",
    ]


def test_input_connection_actions_join_the_existing_fleet_monitoring_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brain_state_root = tmp_path / "brain2devices-fabric"
    brain_state_root.mkdir()
    (brain_state_root / "state.json").write_text(
        json.dumps(
            {
                "sessionId": "monitoring-session-01",
                "fleetNodeId": "brain2devices-fleet-01",
                "siteId": "cit-business",
                "roomId": "flight-room",
            }
        ),
        encoding="utf-8",
    )
    runner = PowerShellDiscoveryRunner(
        script_path=Path(__file__).resolve().parents[2]
        / "tools"
        / "hardware"
        / "find-classroom-devices.ps1",
        state_root=tmp_path / "fabric",
        brain2devices_root=tmp_path / "brain",
        robomaster_root=tmp_path / "robot",
        agent_mesh_root=tmp_path / "agent-mesh",
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

    asyncio.run(connect())

    for _, arguments in launches:
        assert "-FleetInputOnly" in arguments
        assert arguments[arguments.index("-FabricSessionId") + 1] == "monitoring-session-01"
        assert arguments[arguments.index("-SiteId") + 1] == "cit-business"
        assert arguments[arguments.index("-RoomId") + 1] == "flight-room"
    assert launches[0][0] == "glasses-agent-hardware-test.ps1"
    assert "-SelectMostRecentAgentSession" not in launches[0][1]
    assert launches[1][0] == "robomaster-leap-hardware-test.ps1"
    assert "-ConnectOnly" not in launches[1][1]
    assert "-Live" in launches[1][1]


def test_brain_device_actions_reconcile_all_adapters_after_both_devices_connect(
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
        agent_mesh_root=tmp_path / "agent-mesh",
        fabric_port=9876,
        powershell_path="pwsh",
    )
    launches: list[tuple[str, tuple[str, ...]]] = []

    class FakeBrain:
        def __init__(self) -> None:
            self.connected: set[str] = set()

        async def post(self, path: str) -> None:
            if path == "/api/headset/connect":
                self.connected.add("mindwave")
            else:
                self.connected.add("tello")

        async def wait_for(self, device: str) -> None:
            assert device in self.connected

        async def adapter_device_group(self) -> str:
            if self.connected == {"mindwave", "tello"}:
                return "All"
            return "MindWave" if "mindwave" in self.connected else "Tello"

    async def capture_launcher(script_name: str, *arguments: str) -> None:
        launches.append((script_name, arguments))

    monkeypatch.setattr(runner, "_brain", FakeBrain())
    monkeypatch.setattr(runner, "_run_launcher", capture_launcher)

    async def connect() -> None:
        await runner.perform("brain2devices.mindwave.connect", confirm_grounded=False)
        await runner.perform("brain2devices.tello.connect-all", confirm_grounded=True)

    asyncio.run(connect())

    selected_devices = [arguments[arguments.index("-Device") + 1] for _, arguments in launches]
    assert selected_devices == ["MindWave", "All"]
    for _, arguments in launches:
        assert arguments[arguments.index("-StateRoot") + 1] == str(
            tmp_path / "brain2devices-fabric"
        )


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
    assert len(scanned.json()["integrations"]) == 12
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


def test_matter_commissioning_code_is_not_written_to_audit(tmp_path: Path) -> None:
    runner = FakeDiscoveryRunner()
    setup_code = "MT:Y.K9042C00KA0648G00"
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
        commissioned = client.post(
            "/api/v1/fabric/matter/commission",
            headers=ADMIN_HEADERS,
            json={"setupCode": setup_code},
        )
        rejected_value = " MT:do-not-reflect-this-value "
        rejected = client.post(
            "/api/v1/fabric/matter/commission",
            headers=ADMIN_HEADERS,
            json={"setupCode": rejected_value},
        )
        audit = client.get("/api/v1/fabric/audit?limit=50", headers=ADMIN_HEADERS)

    assert commissioned.status_code == 200
    assert commissioned.json()["actionId"] == "cit.matter-smart-plug.commission"
    assert runner.matter_codes == [setup_code]
    assert rejected.status_code == 409
    assert rejected_value not in rejected.text
    assert setup_code not in audit.text
    matter_record = next(
        record
        for record in audit.json()
        if record["action"] == "fabric.matter.commission" and record["outcome"] == "succeeded"
    )
    assert matter_record["details"] == {
        "inputRetained": False,
        "vendorAccountUsed": False,
    }


def test_removed_legacy_smart_plug_routes_are_not_exposed(tmp_path: Path) -> None:
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
        responses = [
            client.post(path, headers=ADMIN_HEADERS, json={})
            for path in (
                "/api/v1/fabric/smart-plugs/tuya/connect",
                "/api/v1/fabric/smart-plugs/tasmota/connect",
                "/api/v1/fabric/smart-plugs/tasmota/discover",
            )
        ]

    assert [response.status_code for response in responses] == [404, 404, 404]


def test_lego_profile_is_validated_and_hub_name_is_not_audited(tmp_path: Path) -> None:
    runner = FakeDiscoveryRunner()
    discovery = FabricDiscoveryService(runner, clock=lambda: NOW)
    hub_name = "CIT LEGO Tutor A"
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=(admin_identity(),),
            maintenance_interval=None,
            discovery_service=discovery,
        )
    ) as client:
        connected = client.post(
            "/api/v1/fabric/lego/connect",
            headers=ADMIN_HEADERS,
            json={
                "hubName": hub_name,
                "hubModel": "spike-prime",
                "ports": {"A": "motor", "B": "motor", "C": "distance"},
            },
        )
        invalid = client.post(
            "/api/v1/fabric/lego/connect",
            headers=ADMIN_HEADERS,
            json={
                "hubName": "CIT LEGO B",
                "hubModel": "spike-essential",
                "ports": {"A": "motor", "C": "motor"},
            },
        )
        audit = client.get("/api/v1/fabric/audit?limit=50", headers=ADMIN_HEADERS)

    assert connected.status_code == 200
    assert connected.json()["actionId"] == "cit.lego-pybricks.configure-connect"
    assert runner.lego_configurations[0].hubName == hub_name
    assert invalid.status_code == 422
    assert hub_name not in audit.text
    lego_record = next(
        record for record in audit.json() if record["action"] == "fabric.lego.connect"
    )
    assert lego_record["details"] == {
        "configuredPortCount": 3,
        "hubModel": "spike-prime",
        "motorCommandIssued": False,
    }


def test_lego_profile_allows_sensor_only_monitoring() -> None:
    configuration = LegoConnectionConfiguration.model_validate(
        {
            "hubName": "CIT Sensor Hub",
            "hubModel": "spike-essential",
            "ports": {"A": "distance", "B": "empty"},
        }
    )

    assert configuration.ports == {"A": "distance", "B": "empty"}


def test_dash_dot_connection_accepts_only_exact_opaque_candidates(tmp_path: Path) -> None:
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
        connected = client.post(
            "/api/v1/fabric/wonder-workshop/connect",
            headers=ADMIN_HEADERS,
            json={
                "robots": [
                    {"candidateId": "wonder-aabbccddeeff", "model": "dash"},
                    {"candidateId": "wonder-001122334455", "model": "dot"},
                ]
            },
        )
        invalid = client.post(
            "/api/v1/fabric/wonder-workshop/connect",
            headers=ADMIN_HEADERS,
            json={"robots": [{"candidateId": "nearest-bluetooth-robot", "model": "dash"}]},
        )
        duplicate = client.post(
            "/api/v1/fabric/wonder-workshop/connect",
            headers=ADMIN_HEADERS,
            json={
                "robots": [
                    {"candidateId": "wonder-001122334455", "model": "dot"},
                    {"candidateId": "wonder-001122334455", "model": "dot"},
                ]
            },
        )

    assert connected.status_code == 200
    assert connected.json()["actionId"] == "cit.wonder-workshop.configure-connect"
    assert [robot.candidateId for robot in runner.wonder_configurations[0].robots] == [
        "wonder-aabbccddeeff",
        "wonder-001122334455",
    ]
    assert invalid.status_code == 422
    assert duplicate.status_code == 422


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
