from __future__ import annotations

import json
import os
import shutil
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


def test_component_launchers_reopen_the_single_shared_tutor_console() -> None:
    for name in (
        "glasses-agent-hardware-test.ps1",
        "robomaster-leap-hardware-test.ps1",
        "smart-plug-hardware-test.ps1",
    ):
        launcher = _launcher(name)

        assert "interaction-fabric-console.ps1" in launcher
        assert "-Mode Open" in launcher


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
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    report = json.loads(completed.stdout)

    assert report["schemaVersion"] == "1.0"
    assert len(report["integrations"]) == 8
    assert completed.stderr == ""
