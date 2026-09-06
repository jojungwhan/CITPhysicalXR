from __future__ import annotations

import argparse
import asyncio
import sys

import pytest
from cit_matter_smart_plug import admin


def test_inventory_reports_that_the_windows_bluetooth_adapter_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeMatterServerClient:
        def __init__(self, _server_url: str, *, timeout_seconds: float) -> None:
            assert timeout_seconds == 30
            self.server_info = {
                "bluetooth_enabled": True,
                "wifi_credentials_set": True,
            }
            self.nodes: dict[int, dict[str, object]] = {}

        async def connect(self) -> None:
            return None

        async def close(self) -> None:
            return None

    async def adapter_missing() -> str:
        return "adapter_missing"

    monkeypatch.setattr(admin, "MatterServerClient", FakeMatterServerClient)
    monkeypatch.setattr(admin, "_local_bluetooth_status", adapter_missing)

    document = asyncio.run(
        admin._run(
            argparse.Namespace(
                operation="inventory",
                server_url="ws://127.0.0.1:5580/ws",
            )
        )
    )

    assert document["controller"] == {
        "connected": True,
        "bluetoothEnabled": True,
        "bluetoothReady": False,
        "bluetoothStatus": "adapter_missing",
        "wifiCredentialsSet": True,
    }


def test_commissioning_stops_immediately_when_no_bluetooth_or_network_device_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeMatterServerClient:
        def __init__(self, _server_url: str, *, timeout_seconds: float) -> None:
            assert timeout_seconds == 30
            self.server_info: dict[str, object] = {}
            self.nodes: dict[int, dict[str, object]] = {}

        async def connect(self) -> None:
            return None

        async def close(self) -> None:
            return None

        async def discover_commissionable_devices(self) -> list[object]:
            return []

        async def commission(self, _setup_code: str) -> dict[str, object]:
            raise AssertionError("commissioning must not start without a rendezvous transport")

    async def adapter_missing() -> str:
        return "adapter_missing"

    monkeypatch.setattr(admin, "MatterServerClient", FakeMatterServerClient)
    monkeypatch.setattr(admin, "_local_bluetooth_status", adapter_missing)
    monkeypatch.setattr(admin, "_stdin_object", lambda: {"setupCode": "34970112332"})

    with pytest.raises(admin.MatterAdminError) as caught:
        asyncio.run(
            admin._run(
                argparse.Namespace(
                    operation="commission",
                    server_url="ws://127.0.0.1:5580/ws",
                )
            )
        )

    assert caught.value.code == "MATTER_BLUETOOTH_ADAPTER_MISSING"
    assert "Bluetooth LE adapter" in str(caught.value)


def test_commissioning_cli_emits_one_redacted_machine_readable_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fail(_arguments: argparse.Namespace) -> dict[str, object]:
        raise admin.MatterAdminError(
            "MATTER_WIFI_JOIN_FAILED",
            "The plug was reached, but it could not join the saved Wi-Fi.",
        )

    monkeypatch.setattr(admin, "_run", fail)
    monkeypatch.setattr(sys, "argv", ["cit-matter-admin", "commission"])

    with pytest.raises(SystemExit) as caught:
        admin.main()

    assert caught.value.code == 1
    assert capsys.readouterr().err.strip() == (
        "CIT_MATTER_ERROR|MATTER_WIFI_JOIN_FAILED|"
        "The plug was reached, but it could not join the saved Wi-Fi."
    )


@pytest.mark.parametrize(
    ("diagnostic", "expected_code"),
    [
        ("PASE failed while using the setup code", "MATTER_SETUP_CODE_REJECTED"),
        ("Network commissioning could not join WiFi", "MATTER_WIFI_JOIN_FAILED"),
        ("Device attestation certificate failed", "MATTER_ATTESTATION_FAILED"),
        ("Controller connection timed out", "MATTER_CONTROLLER_UNAVAILABLE"),
        ("Commissionable node discovery timed out", "MATTER_DEVICE_NOT_FOUND"),
        ("Unclassified controller failure 34970112332", "MATTER_COMMISSIONING_FAILED"),
    ],
)
def test_commissioning_failure_classification_is_stage_specific_and_redacted(
    diagnostic: str,
    expected_code: str,
) -> None:
    classified = admin._commissioning_error(RuntimeError(diagnostic))

    assert classified.code == expected_code
    assert diagnostic not in str(classified)
    assert "34970112332" not in str(classified)
