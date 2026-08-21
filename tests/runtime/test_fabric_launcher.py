from __future__ import annotations

from pathlib import Path

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
