from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _launcher(name: str) -> str:
    return (REPOSITORY_ROOT / "tools" / "hardware" / name).read_text(encoding="utf-8")


def test_shared_launcher_uses_one_use_fragment_ticket_without_printing_a_token() -> None:
    launcher = _launcher("interaction-fabric-console.ps1")

    assert "/api/v1/fabric/auth/console-tickets" in launcher
    assert "#console-ticket=" in launcher
    assert "accessToken" not in launcher
    assert "Write-Host $ticket" not in launcher
    assert "Write-Host $credential" not in launcher
    assert '"Open"' in launcher


def test_shared_launcher_hides_disconnected_adapter_history_from_live_status() -> None:
    launcher = _launcher("interaction-fabric-console.ps1")

    assert 'Where-Object { $_.connectionState -in @("connected", "degraded") }' in launcher
    assert 'Write-Host "Connected nodes: $($nodes.Count)"' in launcher
    assert 'Write-Host "Offline adapter records hidden: $offlineNodeCount"' in launcher


def test_component_launchers_reopen_the_single_shared_tutor_console() -> None:
    for name in (
        "brain2devices-fabric-adapters.ps1",
        "glasses-agent-hardware-test.ps1",
        "lego-pybricks.ps1",
        "matter-smart-plug.ps1",
        "robomaster-leap-hardware-test.ps1",
    ):
        launcher = _launcher(name)

        assert "interaction-fabric-console.ps1" in launcher
        assert "-Mode Open" in launcher


def test_classroom_launcher_isolates_optional_brain2devices_failure() -> None:
    launcher = _launcher("classroom-devices.ps1")

    assert "try {\n    & $brainLauncher @brainParameters\n  } catch {" in launcher
    assert "The optional Brain2Devices integration is unavailable" in launcher
    assert 'Write-Host "READY. In Classroom Control, choose Find devices."' in launcher


def test_lego_launcher_uses_exact_profile_input_and_unarmed_monitoring() -> None:
    launcher = _launcher("lego-pybricks.ps1")
    probe = _launcher("find-classroom-devices.ps1")

    assert "[Console]::In.ReadToEnd()" in launcher
    assert "/api/v1/fabric/monitoring/session" in launcher
    assert "/roles/$sensorRole" in launcher
    assert '"robot_sensor_$_"' in launcher
    assert "cit_lego_pybricks.fabric_main" in launcher
    assert "--ports-base64" in launcher
    assert "ConvertTo-StartProcessArgument" in launcher
    assert "Invoke-Expression" not in launcher
    assert "download_program" not in launcher
    assert '"/arm"' not in launcher
    assert "$nodes = @(Expand-Sequence (Invoke-JsonApi" in launcher
    assert '.PSObject.Properties["nodeId"]' in launcher
    assert '.PSObject.Properties["connectionState"]' in launcher
    assert "paired LEGO/Pybricks" not in probe
    assert "Do not pair the hub in Windows Bluetooth Settings" in probe


def test_matter_launcher_and_probe_expose_wifi_readiness_before_commissioning() -> None:
    launcher = _launcher("matter-smart-plug.ps1")
    probe = _launcher("find-classroom-devices.ps1")

    assert '"ConfigureWifi"' in launcher
    assert "[Console]::In.ReadToEnd()" in launcher
    assert "wifiCredentialsSet" in launcher
    assert "MATTER_WIFI_NOT_CONFIGURED" in launcher
    assert '"matter-controller-wifi"' in probe
    assert "cit_matter_smart_plug.admin discover" in probe
    assert "wifiCredentialsSet" in probe
    assert "Running Fabric adapters:" in launcher
    assert "Offline Fabric adapter records:" in launcher
    assert "Test-ExactProcess $record.adapterPid $adapterMarker" in launcher


def test_independent_monitoring_launchers_join_one_shared_session() -> None:
    for name in ("brain2devices-fabric-adapters.ps1", "lego-pybricks.ps1"):
        launcher = _launcher(name)

        assert "/api/v1/fabric/monitoring/session" in launcher
        assert 'coursePackId = "device-monitoring"' not in launcher
        assert "must not stop LEGO or another monitoring node" in launcher or (
            "This component owns only its adapter process" in launcher
        )


def test_classroom_device_launcher_starts_discovery_hosts_without_actuation() -> None:
    launcher = _launcher("classroom-devices.ps1")
    brain = _launcher("brain2devices-hardware.ps1")
    probe = _launcher("find-classroom-devices.ps1")

    assert "interaction-fabric-console.ps1" in launcher
    assert "brain2devices-hardware.ps1" in launcher
    assert "find-classroom-devices.ps1" in launcher
    assert '"--no-browser", "--web-port"' in brain
    assert "--self-test" in brain
    assert "/api/state" in brain
    for forbidden in (
        "/api/drone/takeoff",
        "/api/drone/land",
        "/api/drone/move",
        "/api/drone/emergency",
        "/api/fleet/command",
    ):
        assert forbidden not in brain
        assert forbidden not in probe
    assert ".Send(" not in probe


def test_business_install_uses_one_profiled_managed_brain2devices_checkout() -> None:
    installer = _launcher("install-business-site.ps1")
    devices = _launcher("classroom-devices.ps1")
    fabric = _launcher("interaction-fabric-console.ps1")

    assert "brainSource.localDirectory" in installer
    assert "brain2devicesRoot" in installer
    assert "brain2devicesRoot" in devices
    assert "$fabricParameters.Brain2DevicesRoot" in devices
    assert "CITXR_BRAIN2DEVICES_ROOT" in fabric
    assert "$classroomLauncher -Mode Enable -AllowPhysical" in installer


def test_classroom_start_button_runs_only_the_fixed_disarmed_host_launcher() -> None:
    button = _launcher("classroom-control-button.ps1")
    devices = _launcher("classroom-devices.ps1")
    installer = _launcher("install-classroom-control-button.ps1")

    assert "Start classroom devices" in button
    assert 'Join-Path $PSScriptRoot "classroom-devices.ps1"' in button
    assert '$startInfo.ArgumentList.Add("-AllowPhysical")' in button
    assert '[ValidateSet("Start", "Enable", "Open")]' in button
    assert "Read-Host" not in button
    assert "Invoke-Expression" not in button
    assert '"Enable" {' in devices
    assert "physical outputs will remain disarmed" in button
    assert "$event.Cancel = $true" in button
    assert "WScript.Shell" in installer
    assert "CIT Classroom Control.lnk" in installer

    console = (REPOSITORY_ROOT / "apps" / "studio-web" / "src" / "FabricConsole.tsx").read_text(
        encoding="utf-8"
    )
    catalog = (REPOSITORY_ROOT / "apps" / "studio-web" / "src" / "fabric-i18n.ts").read_text(
        encoding="utf-8"
    )
    assert 't("login.useButtonHelp")' in console
    assert "Windows Desktop or" in catalog
    assert "Start classroom devices" in catalog
    assert "Windows 바탕 화면이나 시작 메뉴" in catalog
    assert "pnpm hardware:fabric:windows -- -Mode Open" not in console


@pytest.mark.skipif(os.name != "nt" or shutil.which("pwsh") is None, reason="Windows UI")
def test_classroom_start_button_describes_an_offline_host_without_showing_ui() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    button = REPOSITORY_ROOT / "tools" / "hardware" / "classroom-control-button.ps1"
    completed = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(button),
            "-Mode",
            "Describe",
            "-FabricPort",
            str(port),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )

    description = json.loads(completed.stdout)
    assert description["state"] == "offline"
    assert description["primaryAction"] == "Start"
    assert description["primaryLabel"] == "Start classroom devices"
    assert completed.stderr == ""


@pytest.mark.skipif(os.name != "nt" or shutil.which("pwsh") is None, reason="Windows UI")
def test_classroom_button_installer_creates_user_shortcuts_in_exact_roots(
    tmp_path: Path,
) -> None:
    installer = REPOSITORY_ROOT / "tools" / "hardware" / "install-classroom-control-button.ps1"
    desktop = tmp_path / "desktop"
    programs = tmp_path / "programs"
    completed = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(installer),
            "-Mode",
            "Install",
            "-DesktopRoot",
            str(desktop),
            "-ProgramsRoot",
            str(programs),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert (desktop / "CIT Classroom Control.lnk").is_file()
    assert (programs / "CIT Classroom" / "CIT Classroom Control.lnk").is_file()
    assert "Desktop and Start menu" in completed.stdout
    assert completed.stderr == ""


def test_ui_started_physical_adapters_support_a_disarmed_connect_only_mode() -> None:
    robot = _launcher("robomaster-leap-hardware-test.ps1")
    probe = _launcher("find-classroom-devices.ps1")

    assert "[switch]$ConnectOnly" in robot
    assert "CONNECTED AND DISARMED" in robot
    assert "[IO.File]::Delete" in robot
    assert '"--publish-camera"' in robot
    assert "import cv2, robomaster" in robot
    assert '"fabric.media.publish"' in robot
    assert '"cit.robomaster-leap.connect"' in probe


def test_legacy_smart_plug_launchers_are_removed() -> None:
    hardware = REPOSITORY_ROOT / "tools" / "hardware"

    assert not (hardware / "smart-plug-hardware-test.ps1").exists()
    assert not (hardware / "tasmota-smart-plug.ps1").exists()


def test_windows_transfer_installer_has_a_versioned_fail_closed_boundary() -> None:
    builder = (
        REPOSITORY_ROOT / "tools" / "release" / "build-windows-transfer-bundle.ps1"
    ).read_text(encoding="utf-8-sig")
    bootstrap = (REPOSITORY_ROOT / "tools" / "release" / "windows" / "Install-CIT.ps1").read_text(
        encoding="utf-8-sig"
    )
    business_installer = _launcher("install-business-site.ps1")

    assert "git -C $sourceRoot status --porcelain=v1" in builder
    assert "source tree has uncommitted files" in builder
    assert "Assert-RelativeSourcePath" in builder
    assert '".env"' in builder
    assert '"node_modules"' in builder
    assert '"artifacts"' in builder
    assert "Get-FileHash -LiteralPath $payloadPath -Algorithm SHA256" in bootstrap
    assert "Assert-VerifiedSourceTree" in bootstrap
    assert "sourceManifestSha256" in builder
    assert "[switch]$ValidateOnly" in bootstrap
    assert 'Join-Path $env:LOCALAPPDATA "CITPhysicalXR\\app"' in bootstrap
    assert "controller databases and operational keys must not be copied" in (
        REPOSITORY_ROOT / "tools" / "release" / "windows" / "INSTALL-EN.txt"
    ).read_text(encoding="utf-8")
    assert '"release:windows:bundle"' in business_installer


def test_glasses_and_leap_launchers_can_attach_inputs_to_a_shared_fleet_session() -> None:
    glasses = _launcher("glasses-agent-hardware-test.ps1")
    leap = _launcher("robomaster-leap-hardware-test.ps1")

    for launcher in (glasses, leap):
        assert "[string]$FabricSessionId" in launcher
        assert "[switch]$FleetInputOnly" in launcher
        assert 'coursePackId -ne "device-monitoring"' in launcher
        assert '"fleet_sequence_input_$_"' in launcher
        assert "interaction.intent.flight_sequence_start" in launcher

    assert "$State.bridgeSessionId -eq $SessionId" in glasses
    assert "cit_robomaster_leap.robot_main" in leap
    assert "if (-not $FleetInputOnly)" in leap
    assert leap.count("Start-Sleep -Milliseconds 1200") >= 2


@pytest.mark.skipif(os.name != "nt" or shutil.which("pwsh") is None, reason="Windows probe")
def test_device_probe_captures_a_console_writing_tello_helper_as_one_json_document(
    tmp_path: Path,
) -> None:
    helper = (
        tmp_path
        / "brain2devices"
        / "src"
        / "brain2devices"
        / "scripts"
        / "connect_tello_radios.ps1"
    )
    helper.parent.mkdir(parents=True)
    helper.write_text(
        """
param([string]$Action = 'Scan', [string]$ResultPath = '', [int]$TimeoutSeconds = 20)
$payload = '{"ok":true,"action":"scan","adapters":[]}'
if ($ResultPath) {
  [IO.File]::WriteAllText($ResultPath, $payload, [Text.UTF8Encoding]::new($false))
} else {
  [Console]::Out.WriteLine($payload)
}
""".strip(),
        encoding="utf-8",
    )
    probe = REPOSITORY_ROOT / "tools" / "hardware" / "find-classroom-devices.ps1"
    completed = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(probe),
            "-StateRoot",
            str(tmp_path / "state" / "interaction-fabric"),
            "-Brain2DevicesRoot",
            str(tmp_path / "brain2devices"),
            "-RoboMasterRoot",
            str(tmp_path / "robomaster"),
            "-AgentMeshRoot",
            str(tmp_path / "agent-mesh"),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    report = json.loads(completed.stdout)

    assert report["schemaVersion"] == "1.0"
    assert len(report["integrations"]) == 11
    sphero = next(item for item in report["integrations"] if item["integrationId"] == "sphero-bolt")
    assert sphero["connectionMethod"] == "Local Bluetooth Low Energy (BLE)"
    assert "actionId" not in sphero
    assert "750 ms" in sphero["safetyNote"]
    wonder = next(
        item
        for item in report["integrations"]
        if item["integrationId"] == "wonder-workshop-dash-dot"
    )
    assert wonder["connectionMethod"] == "Local Bluetooth Low Energy (BLE)"
    assert "actionId" not in wonder
    assert "nearest" in wonder["safetyNote"]
    coding_agents = next(
        item for item in report["integrations"] if item["integrationId"] == "coding-agents"
    )
    assert "actionId" not in coding_agents
    assert completed.stderr == ""


def test_wonder_launcher_tolerates_transient_non_node_api_values() -> None:
    launcher = _launcher("wonder-workshop.ps1")

    assert "$nodes = @(Expand-Sequence (Invoke-JsonApi" in launcher
    assert '.PSObject.Properties["nodeId"]' in launcher
    assert '.PSObject.Properties["connectionState"]' in launcher


def test_sphero_launcher_is_exact_selection_and_fail_safe() -> None:
    launcher = _launcher("sphero-bolt.ps1")

    assert "^sphero-[a-f0-9]{12}$" in launcher
    assert "cit_sphero_bolt.fabric_main" in launcher
    assert "Start-Sleep -Milliseconds 900" in launcher
    assert "$nodes = @(Expand-Sequence (Invoke-JsonApi" in launcher
    assert '.PSObject.Properties["nodeId"]' in launcher
    assert '.PSObject.Properties["connectionState"]' in launcher


@pytest.mark.skipif(os.name != "nt" or shutil.which("pwsh") is None, reason="Windows probe")
def test_device_probe_reports_one_authorized_android_usb_phone_without_exposing_serial(
    tmp_path: Path,
) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "adb.cmd").write_text(
        """
@echo off
if "%~1"=="devices" (
  echo List of devices attached
  echo CIT-PRIVATE-SERIAL device usb:1-2 product:cit model:CIT_Test_Phone transport_id:1
  exit /b 0
)
if "%~1"=="-s" if "%~4"=="getprop" (
  echo CIT Test Phone
  exit /b 0
)
if "%~1"=="-s" if "%~4"=="pm" if "%~5"=="path" if "%~6"=="com.even.sg" (
  echo package:/data/app/com.even.sg/base.apk
  exit /b 0
)
if "%~1"=="-s" if "%~4"=="pidof" if "%~5"=="com.even.sg" (
  echo 1234
  exit /b 0
)
exit /b 1
""".strip(),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PATH"] = f"{tools}{os.pathsep}{environment['PATH']}"
    probe = REPOSITORY_ROOT / "tools" / "hardware" / "find-classroom-devices.ps1"

    completed = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(probe),
            "-StateRoot",
            str(tmp_path / "state" / "interaction-fabric"),
            "-Brain2DevicesRoot",
            str(tmp_path / "brain2devices"),
            "-RoboMasterRoot",
            str(tmp_path / "robomaster"),
            "-AgentMeshRoot",
            str(tmp_path / "agent-mesh"),
            "-SkipWifiScan",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )

    report = json.loads(completed.stdout)
    g2 = next(
        item for item in report["integrations"] if item["integrationId"] == "even-realities-g2"
    )
    android = next(
        candidate for candidate in g2["candidates"] if candidate["candidateId"] == "g2-android-1"
    )

    assert android["connectionPath"] == "android_usb"
    assert android["linkState"] == "attached"
    assert android["status"] == "found"
    assert "Even app is installed" in android["detail"]
    assert "CIT-PRIVATE-SERIAL" not in completed.stdout
    assert completed.stderr == ""


@pytest.mark.skipif(os.name != "nt" or shutil.which("pwsh") is None, reason="Windows probe")
def test_device_probe_distinguishes_a_meta_companion_over_wifi_adb(
    tmp_path: Path,
) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "adb.cmd").write_text(
        """
@echo off
if "%~1"=="devices" (
  echo List of devices attached
  echo 192.168.50.44:5555 device product:cit model:CIT_Meta_Phone transport_id:2
  exit /b 0
)
if "%~1"=="-s" if "%~4"=="getprop" (
  echo CIT Meta Phone
  exit /b 0
)
if "%~1"=="-s" if "%~4"=="pm" if "%~5"=="path" if "%~6"=="dev.agentmesh.mobile" (
  echo package:/data/app/dev.agentmesh.mobile/base.apk
  exit /b 0
)
if "%~1"=="-s" if "%~4"=="pidof" if "%~5"=="dev.agentmesh.mobile" (
  echo 2345
  exit /b 0
)
exit /b 1
""".strip(),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PATH"] = f"{tools}{os.pathsep}{environment['PATH']}"
    probe = REPOSITORY_ROOT / "tools" / "hardware" / "find-classroom-devices.ps1"

    completed = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(probe),
            "-StateRoot",
            str(tmp_path / "state" / "interaction-fabric"),
            "-Brain2DevicesRoot",
            str(tmp_path / "brain2devices"),
            "-RoboMasterRoot",
            str(tmp_path / "robomaster"),
            "-AgentMeshRoot",
            str(tmp_path / "agent-mesh"),
            "-SkipWifiScan",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )

    report = json.loads(completed.stdout)
    meta = next(item for item in report["integrations"] if item["integrationId"] == "meta-rayban")
    android = next(
        candidate
        for candidate in meta["candidates"]
        if candidate["candidateId"] == "meta-android-1"
    )
    g2 = next(
        item for item in report["integrations"] if item["integrationId"] == "even-realities-g2"
    )

    assert android["connectionPath"] == "android_wifi"
    assert android["linkState"] == "connected"
    assert android["status"] == "found"
    assert "Agent Mesh companion running" in android["detail"]
    assert g2["candidates"][0]["status"] == "setup_required"
    assert "192.168.50.44" not in completed.stdout
    assert completed.stderr == ""
