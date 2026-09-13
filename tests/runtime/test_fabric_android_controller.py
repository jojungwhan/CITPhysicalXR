from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from cit_runtime.fabric_android import AndroidControllerService
from cit_runtime.fabric_auth import FABRIC_PERMISSIONS, FabricBootstrapIdentity
from cit_runtime.fabric_service import create_fabric_app
from fastapi.testclient import TestClient

NOW = datetime(2026, 9, 9, 3, 0, 0, tzinfo=UTC)
ADMIN_TOKEN = "cit-admin-" + "a" * 40
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


class RecordingAdb:
    def __init__(self, devices: str | None = None) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.devices = devices or (
            "List of devices attached\n"
            "R3CMB0ANZYT device product:d1xks model:SM_N971N device:d1x transport_id:7\n"
        )

    def __call__(
        self,
        arguments: tuple[str, ...],
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        self.commands.append(arguments)
        if arguments[1:] == ("devices", "-l"):
            return subprocess.CompletedProcess(arguments, 0, self.devices, "")
        if arguments[-3:] == ("shell", "getprop", "ro.product.model"):
            return subprocess.CompletedProcess(arguments, 0, "SM-N971N\n", "")
        if "install" in arguments:
            return subprocess.CompletedProcess(arguments, 0, "Success\n", "")
        if arguments[-3:] == ("pm", "clear", "com.cit.controltower.companion"):
            return subprocess.CompletedProcess(arguments, 0, "Success\n", "")
        return subprocess.CompletedProcess(arguments, 0, "", "")


def admin_identity() -> FabricBootstrapIdentity:
    return FabricBootstrapIdentity(
        identity_id="admin-a",
        token=ADMIN_TOKEN,
        actor_type="administrator",
        roles=("administrator",),
        permissions=tuple(sorted(FABRIC_PERMISSIONS)),
    )


@pytest.mark.asyncio
async def test_android_controller_uses_one_authorized_usb_phone_and_exact_reverse() -> None:
    adb = RecordingAdb()
    service = AndroidControllerService(
        port=8766,
        adb_path="adb-test",
        run_process=adb,
        monitor_interval=None,
        clock=lambda: NOW,
    )

    snapshot = await service.refresh()

    assert snapshot.state == "ready"
    assert snapshot.phoneConnected is True
    assert snapshot.phoneModel == "SM-N971N"
    assert snapshot.usbReverseReady is True
    assert snapshot.operations.openController is True
    assert (
        "adb-test",
        "-s",
        "R3CMB0ANZYT",
        "reverse",
        "tcp:8766",
        "tcp:8766",
    ) in adb.commands
    assert "R3CMB0ANZYT" not in snapshot.model_dump_json()


@pytest.mark.asyncio
async def test_android_controller_opens_only_the_fixed_loopback_pwa_url() -> None:
    adb = RecordingAdb()
    service = AndroidControllerService(
        port=8766,
        adb_path="adb-test",
        run_process=adb,
        monitor_interval=None,
        clock=lambda: NOW,
    )
    ticket = "t" * 43

    result = await service.open_controller(ticket)

    assert result.accepted is True
    launch = next(command for command in adb.commands if "android.intent.action.VIEW" in command)
    launched_url = launch[-1]
    parsed = urlsplit(launched_url)
    assert parsed.scheme == "http"
    assert parsed.netloc == "127.0.0.1:8766"
    assert parsed.path == "/fabric"
    assert parse_qs(parsed.fragment) == {"android-console-ticket": [ticket]}
    assert "&" not in launched_url


@pytest.mark.asyncio
async def test_android_controller_restores_the_existing_chrome_task_after_camera_work() -> None:
    adb = RecordingAdb()
    service = AndroidControllerService(
        port=8766,
        adb_path="adb-test",
        run_process=adb,
        monitor_interval=None,
        clock=lambda: NOW,
    )

    not_opened = await service.restore_controller_foreground()
    await service.open_controller("t" * 43)
    adb.commands.clear()
    restored = await service.restore_controller_foreground()

    assert not_opened is False
    assert restored is True
    assert adb.commands[-1] == (
        "adb-test",
        "-s",
        "R3CMB0ANZYT",
        "shell",
        "am",
        "start",
        "-n",
        "com.android.chrome/com.google.android.apps.chrome.Main",
    )
    assert not any("android.intent.action.VIEW" in command for command in adb.commands)


@pytest.mark.asyncio
async def test_android_controller_installs_and_provisions_wireless_companion_once(
    tmp_path: Path,
) -> None:
    adb = RecordingAdb()
    service = AndroidControllerService(
        port=8766,
        adb_path="adb-test",
        run_process=adb,
        monitor_interval=None,
        clock=lambda: NOW,
    )
    apk = tmp_path / "control-tower.apk"
    apk.write_bytes(b"APK")
    pairing_uri = "cit-control-tower://pair/" + "e" * 120

    await service.install_unlock_companion(apk, pairing_uri)

    install = next(command for command in adb.commands if "install" in command)
    clear = next(command for command in adb.commands if "pm" in command and "clear" in command)
    launch = next(command for command in adb.commands if pairing_uri in command)
    assert install[-3:] == ("install", "-r", str(apk.resolve()))
    assert clear[-3:] == ("pm", "clear", "com.cit.controltower.companion")
    assert launch[-1] == pairing_uri
    assert "com.cit.controltower.companion/.MainActivity" in launch


@pytest.mark.asyncio
async def test_android_controller_fails_closed_when_usb_phone_is_ambiguous() -> None:
    adb = RecordingAdb(
        "List of devices attached\n"
        "FIRST device product:a model:Phone_A transport_id:1\n"
        "SECOND device product:b model:Phone_B transport_id:2\n"
    )
    service = AndroidControllerService(
        port=8766,
        adb_path="adb-test",
        run_process=adb,
        monitor_interval=None,
        clock=lambda: NOW,
    )

    snapshot = await service.refresh()

    assert snapshot.state == "ambiguous"
    assert snapshot.usbReverseReady is False
    assert snapshot.operations.openController is False
    assert not any("reverse" in command for command in adb.commands)
    assert "FIRST" not in snapshot.model_dump_json()
    assert "SECOND" not in snapshot.model_dump_json()


def test_android_handoff_restores_memory_auth_from_a_path_scoped_cookie(
    tmp_path: Path,
) -> None:
    adb = RecordingAdb()
    android = AndroidControllerService(
        port=8766,
        adb_path="adb-test",
        run_process=adb,
        monitor_interval=None,
        clock=lambda: NOW,
    )
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=(admin_identity(),),
            android_controller_service=android,
            maintenance_interval=None,
        )
    ) as client:
        opened = client.post(
            "/api/v1/fabric/android-controller/open",
            headers=ADMIN_HEADERS,
        )
        launch = next(
            command for command in adb.commands if "android.intent.action.VIEW" in command
        )
        ticket = parse_qs(urlsplit(launch[-1]).fragment)["android-console-ticket"][0]
        redeemed = client.post(
            "/api/v1/fabric/auth/console-tickets/redeem",
            json={"ticket": ticket},
        )
        cookie = redeemed.headers["set-cookie"]
        cookie_only_nodes = client.get("/api/v1/fabric/nodes")
        resumed = client.post("/api/v1/fabric/auth/android-session/resume")
        mobile_token = resumed.json()["accessToken"]
        principal = client.get(
            "/api/v1/fabric/auth/whoami",
            headers={"Authorization": f"Bearer {mobile_token}"},
        )
        signed_out = client.post("/api/v1/fabric/auth/android-session/end")
        resume_after_sign_out = client.post("/api/v1/fabric/auth/android-session/resume")

    assert opened.status_code == 200
    assert "ticket" not in opened.text.casefold()
    assert "token" not in opened.text.casefold()
    assert redeemed.status_code == 200
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/api/v1/fabric/auth/android-session" in cookie
    assert cookie_only_nodes.status_code == 401
    assert resumed.status_code == 200
    assert principal.status_code == 200
    assert principal.json()["actorType"] == "android_controller"
    assert "fabric.console.open_android" not in principal.json()["permissions"]
    assert "fabric.lan_access.manage" not in principal.json()["permissions"]
    assert signed_out.status_code == 204
    assert resume_after_sign_out.status_code == 401


def test_ordinary_console_handoff_does_not_create_an_android_cookie(tmp_path: Path) -> None:
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
        redeemed = client.post(
            "/api/v1/fabric/auth/console-tickets/redeem",
            json={"ticket": created.json()["ticket"]},
        )
        resumed = client.post("/api/v1/fabric/auth/android-session/resume")

    assert redeemed.status_code == 200
    assert "citxr_android_session" not in redeemed.headers.get("set-cookie", "")
    assert resumed.status_code == 401
