from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, cast

import pytest
from cit_protocol import IntegrationNode
from cit_runtime.fabric_auth import FABRIC_PERMISSIONS, FabricBootstrapIdentity
from cit_runtime.fabric_course import load_builtin_course_pack
from cit_runtime.fabric_discovery import (
    FabricDiscoveryCandidate,
    FabricDiscoveryError,
    FabricDiscoveryReport,
    FabricDiscoveryService,
    FabricDiscoverySessionTarget,
    FabricRememberedConnection,
    LegoConnectionConfiguration,
    MatterWifiConfiguration,
    PowerShellDiscoveryRunner,
    SpheroBoltConnectionConfiguration,
    SpheroOllieConnectionConfiguration,
    WonderWorkshopConnectionConfiguration,
    _Brain2DevicesClient,
    _ProcessOutputTooLarge,
    _read_bounded_stream,
    _run_with_bounded_file_output,
    initial_discovery_report,
    remembered_connection_policies_for_nodes,
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
        self.session_targets: list[FabricDiscoverySessionTarget] = []
        self.matter_codes: list[str] = []
        self.matter_wifi_configurations: list[tuple[str, str]] = []
        self.lego_configurations: list[LegoConnectionConfiguration] = []
        self.wonder_configurations: list[WonderWorkshopConnectionConfiguration] = []
        self.sphero_configurations: list[SpheroBoltConnectionConfiguration] = []
        self.ollie_configurations: list[SpheroOllieConnectionConfiguration] = []

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

    async def perform(
        self,
        action_id: str,
        *,
        confirm_grounded: bool,
        session_target: FabricDiscoverySessionTarget | None = None,
    ) -> str:
        self.actions.append((action_id, confirm_grounded))
        if session_target is not None:
            self.session_targets.append(session_target)
        if action_id == "brain2devices.tello.connect-all" and not confirm_grounded:
            raise FabricDiscoveryError(
                "GROUNDED_CONFIRMATION_REQUIRED",
                "Grounded confirmation is required",
            )
        if action_id not in {
            "brain2devices.tello.connect-all",
            "brain2devices.mindwave.connect",
            "cit.glasses-device-control.connect",
            "cit.synchronized-mindwave.connect",
        }:
            raise FabricDiscoveryError(
                "DISCOVERY_ACTION_NOT_ALLOWED",
                "Action is not allowlisted",
            )
        return "Connection started; no actuation command was sent."

    async def commission_matter(self, setup_code: str) -> str:
        self.matter_codes.append(setup_code)
        return "Matter plug commissioned locally."

    async def configure_matter_wifi(self, configuration: MatterWifiConfiguration) -> str:
        self.matter_wifi_configurations.append(
            (configuration.ssid, configuration.password.get_secret_value())
        )
        return "Matter controller Wi-Fi configured locally."

    async def connect_lego(self, configuration: LegoConnectionConfiguration) -> str:
        self.lego_configurations.append(configuration)
        return "LEGO hub connected for sensor monitoring."

    async def connect_wonder_workshop(
        self, configuration: WonderWorkshopConnectionConfiguration
    ) -> str:
        self.wonder_configurations.append(configuration)
        return "Selected Dash and Dot robots connected for sensor monitoring."

    async def connect_sphero_bolts(self, configuration: SpheroBoltConnectionConfiguration) -> str:
        self.sphero_configurations.append(configuration)
        return "Selected Sphero BOLT robots connected for sensor monitoring."

    async def connect_sphero_ollies(self, configuration: SpheroOllieConnectionConfiguration) -> str:
        self.ollie_configurations.append(configuration)
        return "Selected Sphero Ollie robots connected for sensor monitoring."


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


def r1_node() -> IntegrationNode:
    value = leap_node().model_dump(mode="json")
    value.update(
        {
            "nodeId": "even-r1-test",
            "pluginId": "cit.agent-mesh-bridge",
            "displayName": "Test Even R1",
            "publishedCapabilities": [
                {
                    "name": "interaction.gesture.smart_ring",
                    "version": "1.0",
                    "direction": "publish",
                    "latencyClass": "interactive",
                    "safetyClassification": "informational",
                    "dataClassification": "operational",
                    "constraints": {"gestures": ["tap", "double_tap"]},
                }
            ],
            "metadata": {"model": "even-realities-r1", "inputOnly": True},
        }
    )
    return IntegrationNode.model_validate(value)


def g2_node() -> IntegrationNode:
    value = leap_node().model_dump(mode="json")
    value.update(
        {
            "nodeId": "even-g2-test",
            "pluginId": "cit.agent-mesh-bridge",
            "displayName": "Test Even G2",
            "publishedCapabilities": [
                {
                    "name": "interaction.intent.agent_prompt",
                    "version": "1.0",
                    "direction": "publish",
                    "latencyClass": "interactive",
                    "safetyClassification": "informational",
                    "dataClassification": "voice_transcript",
                    "constraints": {},
                }
            ],
            "metadata": {"model": "even-realities-g2"},
        }
    )
    return IntegrationNode.model_validate(value)


def test_discovery_overlays_live_nodes_without_claiming_other_devices() -> None:
    runner = FakeDiscoveryRunner()
    service = FabricDiscoveryService(runner, clock=lambda: NOW)

    initial = service.current((leap_node(),))

    leap = next(item for item in initial.integrations if item.integrationId == "leap-motion")
    robot = next(item for item in initial.integrations if item.integrationId == "robomaster-s1")
    sphero = next(item for item in initial.integrations if item.integrationId == "sphero-bolt")
    assert leap.status == "connected"
    assert leap.ioType == "input"
    assert leap.imagePath == "./device-images/leap-motion.webp"
    assert leap.connectedNodeIds == ["leap-motion-test"]
    assert robot.status == "not_scanned"
    assert robot.ioType == "bidirectional"
    assert sphero.status == "not_scanned"
    assert sphero.ioType == "bidirectional"
    assert sphero.icon == "sphero"


def test_live_physical_nodes_become_remembered_profiles_but_simulators_do_not() -> None:
    physical_matches = remembered_connection_policies_for_nodes((leap_node(),))
    simulated = leap_node().model_copy(update={"physical": False, "simulated": True})

    assert [(policy.action_id, seen_at) for policy, seen_at in physical_matches] == [
        ("cit.robomaster-leap.connect", NOW)
    ]
    assert remembered_connection_policies_for_nodes((simulated,)) == ()


def test_live_r1_node_uses_its_input_only_reconnect_action() -> None:
    physical_matches = remembered_connection_policies_for_nodes((r1_node(),))

    assert [(policy.action_id, seen_at) for policy, seen_at in physical_matches] == [
        ("cit.even-r1.connect", NOW)
    ]


def test_live_g2_node_reconnects_without_requiring_a_coding_agent() -> None:
    physical_matches = remembered_connection_policies_for_nodes((g2_node(),))

    assert [(policy.action_id, seen_at) for policy, seen_at in physical_matches] == [
        ("cit.even-g2.connect", NOW)
    ]


def test_remembered_reconnect_does_not_restart_an_already_connected_profile() -> None:
    runner = FakeDiscoveryRunner()
    service = FabricDiscoveryService(runner, clock=lambda: NOW)

    result = asyncio.run(
        service.reconnect_remembered(
            (
                FabricRememberedConnection(
                    actionId="cit.robomaster-leap.connect",
                    requiresGroundedConfirmation=False,
                    rememberedAt=NOW,
                ),
            ),
            confirm_grounded=False,
            nodes=lambda: (leap_node(),),
        )
    )

    assert result.connectedCount == 0
    assert result.alreadyConnectedCount == 1
    assert result.outcomes[0].status == "already_connected"
    assert runner.actions == []
    assert runner.scans == 0


def test_allowlisted_connection_does_not_repeat_the_broad_host_scan() -> None:
    runner = FakeDiscoveryRunner()
    service = FabricDiscoveryService(runner, clock=lambda: NOW)

    async def scenario() -> FabricDiscoveryReport:
        await service.scan(())
        result = await service.perform(
            "brain2devices.mindwave.connect",
            confirm_grounded=False,
            nodes=lambda: (),
        )
        return result.report

    report = asyncio.run(scenario())

    assert runner.scans == 1
    assert report.scanId == "scan-1"


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


@pytest.mark.asyncio
async def test_detached_launcher_output_uses_files_instead_of_inherited_pipes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DetachedChildLauncherProcess:
        def __init__(self) -> None:
            self.stdin = None
            self.returncode: int | None = None
            self.killed = False

        async def wait(self) -> int:
            self.returncode = 0
            return self.returncode

        def kill(self) -> None:
            self.killed = True

    process = DetachedChildLauncherProcess()

    async def create_process(*command: str, **options: object) -> asyncio.subprocess.Process:
        del command
        assert options["stdout"] != asyncio.subprocess.PIPE
        assert options["stderr"] != asyncio.subprocess.PIPE
        stdout = cast(BinaryIO, options["stdout"])
        stdout.write(b"launcher-complete")
        return cast(asyncio.subprocess.Process, process)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    returncode, stdout, stderr = await _run_with_bounded_file_output(
        "pwsh",
        "-File",
        "launcher.ps1",
        timeout_seconds=0.1,
    )

    assert returncode == 0
    assert stdout == b"launcher-complete"
    assert stderr == b""
    assert process.killed is False


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
        await runner.perform("cit.even-g2.connect", confirm_grounded=False)
        await runner.perform("cit.even-r1.connect", confirm_grounded=False)
        await runner.perform("cit.robomaster-leap.connect", confirm_grounded=False)
        await runner.perform("cit.matter-smart-plug.connect", confirm_grounded=False)
        await runner.perform("cit.wonder-workshop.reconnect", confirm_grounded=False)
        await runner.perform("cit.sphero-bolt.reconnect", confirm_grounded=False)
        await runner.perform("cit.sphero-ollie.reconnect", confirm_grounded=False)

    asyncio.run(connect())

    assert launches[0][0] == "glasses-agent-hardware-test.ps1"
    assert "-SelectMostRecentAgentSession" in launches[0][1]
    assert launches[1][0] == "glasses-agent-hardware-test.ps1"
    assert "-SelectMostRecentAgentSession" not in launches[1][1]
    assert launches[2][0] == "glasses-agent-hardware-test.ps1"
    assert "-SelectMostRecentAgentSession" not in launches[2][1]
    assert launches[3][0] == "robomaster-leap-hardware-test.ps1"
    assert "-ConnectOnly" in launches[3][1]
    assert "-Live" in launches[3][1]
    assert launches[4][0] == "matter-smart-plug.ps1"
    assert "-SkipBuild" in launches[4][1]
    assert launches[5][0] == "wonder-workshop.ps1"
    assert launches[5][1][launches[5][1].index("-Mode") + 1] == "Start"
    assert launches[6][0] == "sphero-bolt.ps1"
    assert launches[6][1][launches[6][1].index("-Mode") + 1] == "Start"
    assert launches[7][0] == "sphero-ollie.ps1"
    assert launches[7][1][launches[7][1].index("-Mode") + 1] == "Start"
    assert all("-NoOpenConsole" in arguments for _, arguments in launches)
    component_state_roots = []
    for _, arguments in launches[:4]:
        state_index = arguments.index("-StateRoot")
        component_state_roots.append(Path(arguments[state_index + 1]))
    assert component_state_roots == [
        tmp_path / "glasses-agent",
        tmp_path / "glasses-agent",
        tmp_path / "glasses-agent",
        tmp_path / "robomaster-leap",
    ]


def test_glasses_device_control_launcher_targets_the_exact_lesson(
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
    target = FabricDiscoverySessionTarget(
        sessionId="glasses-control-01",
        coursePackId="glasses-device-control",
        siteId="cit-business",
        roomId="robot-room",
    )

    asyncio.run(
        runner.perform(
            "cit.glasses-device-control.connect",
            confirm_grounded=False,
            session_target=target,
        )
    )

    assert len(launches) == 1
    script_name, arguments = launches[0]
    assert script_name == "glasses-agent-hardware-test.ps1"
    assert "-DeviceControlInputOnly" in arguments
    assert arguments[arguments.index("-FabricSessionId") + 1] == "glasses-control-01"
    assert arguments[arguments.index("-SiteId") + 1] == "cit-business"
    assert arguments[arguments.index("-RoomId") + 1] == "robot-room"
    assert "-SelectMostRecentAgentSession" not in arguments


def test_synchronized_control_launcher_attaches_g2_meta_and_r1_inputs(
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
    target = FabricDiscoverySessionTarget(
        sessionId="synchronized-control-01",
        coursePackId="synchronized-motor-control",
        siteId="cit-business",
        roomId="robot-room",
    )

    asyncio.run(
        runner.perform(
            "cit.glasses-device-control.connect",
            confirm_grounded=False,
            session_target=target,
        )
    )

    assert len(launches) == 1
    script_name, arguments = launches[0]
    assert script_name == "glasses-agent-hardware-test.ps1"
    assert "-FleetInputOnly" in arguments
    assert "-DeviceControlInputOnly" not in arguments
    assert "-DoNotStartSession" in arguments
    assert arguments[arguments.index("-FabricSessionId") + 1] == "synchronized-control-01"


def test_synchronized_mindwave_launcher_targets_only_the_explicit_session(
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
    brain_calls: list[str] = []

    async def capture_launcher(script_name: str, *arguments: str) -> None:
        launches.append((script_name, arguments))

    async def capture_post(path: str) -> dict[str, object]:
        brain_calls.append(path)
        return {"accepted": True}

    async def capture_wait(device: str) -> None:
        brain_calls.append(device)

    async def capture_connected(device: str) -> bool:
        brain_calls.append(f"connected:{device}")
        return True

    monkeypatch.setattr(runner, "_run_launcher", capture_launcher)
    monkeypatch.setattr(runner._brain, "post", capture_post)
    monkeypatch.setattr(runner._brain, "wait_for", capture_wait)
    monkeypatch.setattr(runner._brain, "is_connected", capture_connected)
    target = FabricDiscoverySessionTarget(
        sessionId="synchronized-control-01",
        coursePackId="synchronized-motor-control",
        siteId="cit-business",
        roomId="robot-room",
    )

    asyncio.run(
        runner.perform(
            "cit.synchronized-mindwave.connect",
            confirm_grounded=False,
            session_target=target,
        )
    )

    assert brain_calls == ["connected:mindwave", "mindwave"]
    assert len(launches) == 1
    script_name, arguments = launches[0]
    assert script_name == "brain2devices-fabric-adapters.ps1"
    assert arguments[arguments.index("-Device") + 1] == "MindWave"
    assert arguments[arguments.index("-MindWaveNodeId") + 1] == "mindwave-synchronized-01"
    assert "-DoNotStartSession" in arguments
    assert arguments[arguments.index("-FabricSessionId") + 1] == "synchronized-control-01"


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
        await runner.perform("cit.even-g2.connect", confirm_grounded=False)
        await runner.perform("cit.even-r1.connect", confirm_grounded=False)
        await runner.perform("cit.robomaster-leap.connect", confirm_grounded=False)

    asyncio.run(connect())

    for _, arguments in launches:
        assert "-FleetInputOnly" in arguments
        assert arguments[arguments.index("-FabricSessionId") + 1] == "monitoring-session-01"
        assert arguments[arguments.index("-SiteId") + 1] == "cit-business"
        assert arguments[arguments.index("-RoomId") + 1] == "flight-room"
    assert launches[0][0] == "glasses-agent-hardware-test.ps1"
    assert "-SelectMostRecentAgentSession" not in launches[0][1]
    assert launches[1][0] == "glasses-agent-hardware-test.ps1"
    assert "-SelectMostRecentAgentSession" not in launches[1][1]
    assert launches[2][0] == "glasses-agent-hardware-test.ps1"
    assert "-SelectMostRecentAgentSession" not in launches[2][1]
    assert launches[3][0] == "robomaster-leap-hardware-test.ps1"
    assert "-ConnectOnly" not in launches[3][1]
    assert "-Live" in launches[3][1]


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


def test_tello_connect_recovers_an_orphaned_managed_wifi_route_without_flight(
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
    posts: list[str] = []
    launches: list[tuple[str, tuple[str, ...]]] = []

    class FakeBrain:
        async def post(self, path: str) -> None:
            posts.append(path)
            if path == "/api/fleet/local-radios/auto-connect":
                raise FabricDiscoveryError(
                    "BRAIN2DEVICES_CONNECTION_REJECTED",
                    "Interface 'Wi-Fi' still has a Brain2Devices-managed static IPv4 "
                    "assignment. Include every managed adapter or restore DHCP first.",
                )

        async def wait_for(self, device: str) -> None:
            assert device == "tello"

        async def adapter_device_group(self) -> str:
            return "Tello"

    async def capture_launcher(script_name: str, *arguments: str) -> None:
        launches.append((script_name, arguments))

    monkeypatch.setattr(runner, "_brain", FakeBrain())
    monkeypatch.setattr(runner, "_run_launcher", capture_launcher)

    result = asyncio.run(runner.perform("brain2devices.tello.connect-all", confirm_grounded=True))

    assert posts == [
        "/api/fleet/local-radios/auto-connect",
        "/api/fleet/local-radios/fully-automatic/prepare",
    ]
    assert len(launches) == 1
    assert "No takeoff command was sent" in result


@pytest.mark.parametrize(
    ("rejection_message", "fallback_operation"),
    [
        pytest.param(
            (
                "Automatic fleet setup found 3 visible aircraft but could safely "
                "assign only 1. Unassigned: TELLO-DC5E0F, TELLO-FDA963. "
                "3 aircraft are visible but Windows reports only 1 physical Wi-Fi "
                "adapter(s); each standard Tello needs its own adapter. No Wi-Fi "
                "association, IPv4 setting, SDK command, or flight command was changed."
            ),
            "/api/fleet/local-radios/fully-automatic/prepare",
            id="radio-capacity",
        ),
        pytest.param(
            (
                "Interface 'Wi-Fi 2' is already imported for 'TELLO-58C5B7'. "
                "Remove that disconnected mapping before assigning a different Tello."
            ),
            "/api/fleet/local-radios/sequential-switch",
            id="disconnected-imported-route",
        ),
    ],
)
def test_tello_connect_api_prepares_one_safe_route_when_broad_assignment_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rejection_message: str,
    fallback_operation: str,
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
    posts: list[str] = []

    class FakeBrain:
        async def post(self, path: str) -> None:
            posts.append(path)
            if path == "/api/fleet/local-radios/auto-connect":
                raise FabricDiscoveryError(
                    "BRAIN2DEVICES_CONNECTION_REJECTED",
                    rejection_message,
                )

        async def wait_for(self, device: str) -> None:
            assert device == "tello"

        async def reconnect_first_visible_tello(self) -> None:
            posts.append("/api/fleet/local-radios/sequential-switch")

        async def adapter_device_group(self) -> str:
            return "Tello"

    async def capture_launcher(_script_name: str, *_arguments: str) -> None:
        return None

    monkeypatch.setattr(runner, "_brain", FakeBrain())
    monkeypatch.setattr(runner, "_run_launcher", capture_launcher)
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
        response = client.post(
            "/api/v1/fabric/discovery/actions/brain2devices.tello.connect-all",
            headers=ADMIN_HEADERS,
            json={"confirmGrounded": True},
        )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert "prepared the first available Tello" in response.json()["message"]
    assert posts == [
        "/api/fleet/local-radios/auto-connect",
        fallback_operation,
    ]


def test_tello_connect_api_keeps_an_existing_landed_session_when_route_changes_are_rejected(
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
    posts: list[str] = []

    class FakeBrain:
        async def post(self, path: str) -> None:
            posts.append(path)
            raise FabricDiscoveryError(
                "BRAIN2DEVICES_CONNECTION_REJECTED",
                "Local Wi-Fi routes cannot change while an affected aircraft session may "
                "be active: [TELLO-DC5E0F] currently uses Wi-Fi 2 (connected, landed). "
                "Land and disconnect any connected or busy affected sessions first.",
            )

        async def wait_for(self, device: str) -> None:
            assert device == "tello"

        async def adapter_device_group(self) -> str:
            return "Tello"

    async def capture_launcher(_script_name: str, *_arguments: str) -> None:
        return None

    monkeypatch.setattr(runner, "_brain", FakeBrain())
    monkeypatch.setattr(runner, "_run_launcher", capture_launcher)
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
        response = client.post(
            "/api/v1/fabric/discovery/actions/brain2devices.tello.connect-all",
            headers=ADMIN_HEADERS,
            json={"confirmGrounded": True},
        )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert "already connected and landed" in response.json()["message"]
    assert posts == ["/api/fleet/local-radios/auto-connect"]


def test_brain2devices_reconnect_selects_a_visible_tello_without_flight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Brain2DevicesClient("http://127.0.0.1:8765")
    requests: list[tuple[str, dict[str, object]]] = []

    def fake_post_json(path: str, payload: dict[str, object]) -> dict[str, object]:
        requests.append((path, payload))
        if path == "/api/fleet/local-radios/scan":
            return {
                "accepted": True,
                "adapters": [
                    {
                        "interface_name": "Wi-Fi 2",
                        "interface_index": 12,
                        "recommended_tello_network": "TELLO-FDA963",
                    }
                ],
            }
        return {"accepted": True}

    monkeypatch.setattr(client, "_post_json_sync", fake_post_json, raising=False)

    asyncio.run(client.reconnect_first_visible_tello())

    assert requests == [
        ("/api/fleet/local-radios/scan", {}),
        (
            "/api/fleet/local-radios/sequential-switch",
            {
                "interface_name": "Wi-Fi 2",
                "ssid": "TELLO-FDA963",
                "label": "TELLO-FDA963",
                "accept_loss_of_link": True,
            },
        ),
    ]


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
    assert len(scanned.json()["integrations"]) == 14
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


def test_glasses_connection_is_scoped_to_the_selected_physical_lesson(
    tmp_path: Path,
) -> None:
    runner = FakeDiscoveryRunner()
    discovery = FabricDiscoveryService(runner, clock=lambda: NOW)
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=(admin_identity(),),
            maintenance_interval=None,
            discovery_service=discovery,
            allow_physical_fabric=True,
        )
    ) as client:
        pack = load_builtin_course_pack("glasses-device-control")
        synchronized_pack = load_builtin_course_pack("synchronized-motor-control")
        installed = client.post(
            "/api/v1/fabric/course-packs",
            headers=ADMIN_HEADERS,
            json=pack.model_dump(mode="json", exclude_none=True),
        )
        synchronized_installed = client.post(
            "/api/v1/fabric/course-packs",
            headers=ADMIN_HEADERS,
            json=synchronized_pack.model_dump(mode="json", exclude_none=True),
        )
        created = client.post(
            "/api/v1/fabric/sessions",
            headers=ADMIN_HEADERS,
            json={
                "coursePackId": "glasses-device-control",
                "coursePackVersion": "1.0.0",
                "siteId": "local-site",
                "roomId": "local-room",
                "mode": "physical",
            },
        )
        session_id = created.json()["sessionId"]
        synchronized_created = client.post(
            "/api/v1/fabric/sessions",
            headers=ADMIN_HEADERS,
            json={
                "coursePackId": "synchronized-motor-control",
                "coursePackVersion": "1.0.0",
                "siteId": "local-site",
                "roomId": "local-room",
                "mode": "physical",
            },
        )
        synchronized_session_id = synchronized_created.json()["sessionId"]
        connected = client.post(
            "/api/v1/fabric/discovery/actions/cit.glasses-device-control.connect",
            headers=ADMIN_HEADERS,
            json={"confirmGrounded": False, "sessionId": session_id},
        )
        wrong_action = client.post(
            "/api/v1/fabric/discovery/actions/brain2devices.mindwave.connect",
            headers=ADMIN_HEADERS,
            json={"confirmGrounded": False, "sessionId": session_id},
        )
        synchronized_connected = client.post(
            "/api/v1/fabric/discovery/actions/cit.glasses-device-control.connect",
            headers=ADMIN_HEADERS,
            json={
                "confirmGrounded": False,
                "sessionId": synchronized_session_id,
            },
        )
        synchronized_mindwave = client.post(
            "/api/v1/fabric/discovery/actions/cit.synchronized-mindwave.connect",
            headers=ADMIN_HEADERS,
            json={
                "confirmGrounded": False,
                "sessionId": synchronized_session_id,
            },
        )

    assert installed.status_code == 201
    assert synchronized_installed.status_code == 201
    assert created.status_code == 201
    assert synchronized_created.status_code == 201
    assert connected.status_code == 200
    assert connected.json()["accepted"] is True
    assert synchronized_connected.status_code == 200
    assert synchronized_connected.json()["accepted"] is True
    assert synchronized_mindwave.status_code == 200
    assert synchronized_mindwave.json()["accepted"] is True
    assert [target.model_dump() for target in runner.session_targets] == [
        {
            "sessionId": session_id,
            "coursePackId": "glasses-device-control",
            "siteId": "local-site",
            "roomId": "local-room",
        },
        {
            "sessionId": synchronized_session_id,
            "coursePackId": "synchronized-motor-control",
            "siteId": "local-site",
            "roomId": "local-room",
        },
        {
            "sessionId": synchronized_session_id,
            "coursePackId": "synchronized-motor-control",
            "siteId": "local-site",
            "roomId": "local-room",
        },
    ]
    assert wrong_action.status_code == 403
    assert wrong_action.json()["code"] == "DISCOVERY_SESSION_TARGET_DENIED"


def test_remembered_connection_is_persisted_and_reconnects_without_a_scan(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "fabric.sqlite3"
    runner = FakeDiscoveryRunner()
    discovery = FabricDiscoveryService(runner, clock=lambda: NOW)
    with TestClient(
        create_fabric_app(
            database_path=database_path,
            clock=lambda: NOW,
            fabric_bootstrap_identities=(admin_identity(),),
            maintenance_interval=None,
            discovery_service=discovery,
        )
    ) as client:
        connected = client.post(
            "/api/v1/fabric/discovery/actions/brain2devices.mindwave.connect",
            headers=ADMIN_HEADERS,
            json={"confirmGrounded": False},
        )
        remembered = client.get(
            "/api/v1/fabric/discovery/remembered",
            headers=ADMIN_HEADERS,
        )
        scans_before_reconnect = runner.scans
        reconnected = client.post(
            "/api/v1/fabric/discovery/remembered/connect",
            headers=ADMIN_HEADERS,
            json={"confirmGrounded": False},
        )

    assert connected.status_code == 200
    assert remembered.status_code == 200
    assert remembered.json()["connections"] == [
        {
            "actionId": "brain2devices.mindwave.connect",
            "requiresGroundedConfirmation": False,
            "rememberedAt": NOW.isoformat().replace("+00:00", "Z"),
        }
    ]
    assert reconnected.status_code == 200
    assert reconnected.json()["connectedCount"] == 1
    assert reconnected.json()["failedCount"] == 0
    assert runner.scans == scans_before_reconnect
    assert runner.actions[-1] == ("brain2devices.mindwave.connect", False)

    reopened_discovery = FabricDiscoveryService(runner, clock=lambda: NOW)
    with TestClient(
        create_fabric_app(
            database_path=database_path,
            clock=lambda: NOW,
            fabric_bootstrap_identities=(admin_identity(),),
            maintenance_interval=None,
            discovery_service=reopened_discovery,
        )
    ) as client:
        persisted = client.get(
            "/api/v1/fabric/discovery/remembered",
            headers=ADMIN_HEADERS,
        )
    assert persisted.status_code == 200
    assert [item["actionId"] for item in persisted.json()["connections"]] == [
        "brain2devices.mindwave.connect"
    ]


def test_unattended_remembered_reconnect_skips_aircraft(tmp_path: Path) -> None:
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
            "/api/v1/fabric/discovery/actions/brain2devices.tello.connect-all",
            headers=ADMIN_HEADERS,
            json={"confirmGrounded": True},
        )
        actions_before_reconnect = tuple(runner.actions)
        scans_before_reconnect = runner.scans
        skipped = client.post(
            "/api/v1/fabric/discovery/remembered/connect",
            headers=ADMIN_HEADERS,
            json={"confirmGrounded": False},
        )

    assert connected.status_code == 200
    assert skipped.status_code == 200
    assert skipped.json()["connectedCount"] == 0
    assert skipped.json()["skippedCount"] == 1
    assert skipped.json()["outcomes"][0]["code"] == "GROUNDED_CONFIRMATION_REQUIRED"
    assert tuple(runner.actions) == actions_before_reconnect
    assert runner.scans == scans_before_reconnect


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


def test_matter_wifi_configuration_is_authenticated_and_secret_is_not_audited(
    tmp_path: Path,
) -> None:
    runner = FakeDiscoveryRunner()
    ssid = "CIT-Classroom-2G"
    password = "do-not-store-this-wifi-password"
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
        unauthenticated = client.post(
            "/api/v1/fabric/matter/wifi",
            json={"ssid": ssid, "password": password},
        )
        configured = client.post(
            "/api/v1/fabric/matter/wifi",
            headers=ADMIN_HEADERS,
            json={"ssid": ssid, "password": password},
        )
        audit = client.get("/api/v1/fabric/audit?limit=50", headers=ADMIN_HEADERS)

    assert unauthenticated.status_code == 401
    assert configured.status_code == 200
    assert configured.json()["actionId"] == "cit.matter-smart-plug.configure-wifi"
    assert runner.matter_wifi_configurations == [(ssid, password)]
    assert password not in configured.text
    assert password not in audit.text
    wifi_record = next(
        record for record in audit.json() if record["action"] == "fabric.matter.configure_wifi"
    )
    assert wifi_record["outcome"] == "succeeded"
    assert wifi_record["details"] == {
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


def test_sphero_connection_accepts_only_exact_opaque_candidates(tmp_path: Path) -> None:
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
            "/api/v1/fabric/sphero-bolt/connect",
            headers=ADMIN_HEADERS,
            json={
                "robots": [
                    {"candidateId": "sphero-aabbccddeeff"},
                    {"candidateId": "sphero-001122334455"},
                ]
            },
        )
        invalid = client.post(
            "/api/v1/fabric/sphero-bolt/connect",
            headers=ADMIN_HEADERS,
            json={"robots": [{"candidateId": "nearest-bluetooth-robot"}]},
        )
        duplicate = client.post(
            "/api/v1/fabric/sphero-bolt/connect",
            headers=ADMIN_HEADERS,
            json={
                "robots": [
                    {"candidateId": "sphero-001122334455"},
                    {"candidateId": "sphero-001122334455"},
                ]
            },
        )

    assert connected.status_code == 200
    assert connected.json()["actionId"] == "cit.sphero-bolt.configure-connect"
    assert [robot.candidateId for robot in runner.sphero_configurations[0].robots] == [
        "sphero-aabbccddeeff",
        "sphero-001122334455",
    ]
    assert invalid.status_code == 422
    assert duplicate.status_code == 422


def test_ollie_connection_uses_its_own_exact_candidate_namespace(tmp_path: Path) -> None:
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
            "/api/v1/fabric/sphero-ollie/connect",
            headers=ADMIN_HEADERS,
            json={"robots": [{"candidateId": "sphero-ollie-aabbccddeeff"}]},
        )
        bolt_candidate = client.post(
            "/api/v1/fabric/sphero-ollie/connect",
            headers=ADMIN_HEADERS,
            json={"robots": [{"candidateId": "sphero-aabbccddeeff"}]},
        )

    assert connected.status_code == 200
    assert connected.json()["actionId"] == "cit.sphero-ollie.configure-connect"
    assert [robot.candidateId for robot in runner.ollie_configurations[0].robots] == [
        "sphero-ollie-aabbccddeeff"
    ]
    assert bolt_candidate.status_code == 422


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
