from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from cit_runtime.fabric_android import AndroidControllerService
from cit_runtime.fabric_auth import FABRIC_PERMISSIONS, FabricBootstrapIdentity
from cit_runtime.fabric_lan_access import (
    LanMacAccessPolicy,
    WindowsArpMacResolver,
    normalize_mac_address,
)
from cit_runtime.fabric_service import create_fabric_app
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

NOW = datetime(2026, 9, 10, 3, 0, 0, tzinfo=UTC)
ADMIN_TOKEN = "cit-admin-" + "a" * 40
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
PHONE_IP = "192.168.50.23"
PHONE_MAC = "02:11:22:33:44:55"


class StaticResolver:
    def __init__(self, addresses: dict[str, str | None]) -> None:
        self.addresses = addresses
        self.requests: list[str] = []

    def resolve(self, address: str) -> str | None:
        self.requests.append(address)
        return self.addresses.get(address)


class RecordingAdb:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def __call__(
        self,
        arguments: tuple[str, ...],
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        self.commands.append(arguments)
        if arguments[1:] == ("devices", "-l"):
            output = (
                "List of devices attached\n"
                "PHONE device product:d1 model:SM_N971N device:d1 transport_id:1\n"
            )
        elif arguments[-3:] == ("shell", "getprop", "ro.product.model"):
            output = "SM-N971N\n"
        elif arguments[-4:] == ("shell", "cmd", "wifi", "status"):
            output = (
                'Wifi is connected to "Classroom"\n'
                'WifiInfo: SSID: "Classroom", BSSID: 02:aa:bb:cc:dd:ee, '
                f"MAC: {PHONE_MAC}, Security type: 2\n"
            )
        else:
            output = ""
        return subprocess.CompletedProcess(arguments, 0, output, "")


def admin_identity() -> FabricBootstrapIdentity:
    return FabricBootstrapIdentity(
        identity_id="admin-a",
        token=ADMIN_TOKEN,
        actor_type="administrator",
        roles=("administrator",),
        permissions=tuple(sorted(FABRIC_PERMISSIONS)),
    )


def test_mac_normalization_accepts_common_forms_and_rejects_group_addresses() -> None:
    assert normalize_mac_address("02-11-22-33-44-55") == PHONE_MAC
    assert normalize_mac_address("0211.2233.4455") == PHONE_MAC

    for invalid in ("", "00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff", "01:00:5e:00:00:01"):
        try:
            normalize_mac_address(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected {invalid!r} to be rejected")


def test_windows_arp_resolver_uses_an_exact_argument_list_and_exact_ip_row() -> None:
    calls: list[tuple[tuple[str, ...], float]] = []

    def run(
        arguments: tuple[str, ...],
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((arguments, timeout))
        return subprocess.CompletedProcess(
            arguments,
            0,
            (
                "Interface: 172.30.1.4 --- 0x12\n"
                "  Internet Address      Physical Address      Type\n"
                "  172.30.1.5            00-11-22-33-44-55     dynamic\n"
                f"  {PHONE_IP}          02-11-22-33-44-55     dynamic\n"
            ),
            "",
        )

    resolver = WindowsArpMacResolver(run_process=run)

    assert resolver.resolve(PHONE_IP) == PHONE_MAC
    assert resolver.resolve(PHONE_IP) == PHONE_MAC
    assert calls == [(("arp.exe", "-a", PHONE_IP), 2.0)]


def test_remote_requests_fail_closed_and_ignore_forwarded_client_headers(tmp_path: Path) -> None:
    resolver = StaticResolver({PHONE_IP: PHONE_MAC})
    policy = LanMacAccessPolicy(
        state_path=tmp_path / "lan-access.json",
        enabled=True,
        resolver=resolver,
        clock=lambda: NOW,
    )
    app = create_fabric_app(
        database_path=tmp_path / "fabric.sqlite3",
        clock=lambda: NOW,
        fabric_bootstrap_identities=(admin_identity(),),
        lan_access_policy=policy,
        maintenance_interval=None,
    )

    with TestClient(app, client=(PHONE_IP, 50000)) as remote:
        denied = remote.get(
            "/api/v1/fabric/healthz",
            headers={"X-Forwarded-For": "127.0.0.1"},
        )
        with pytest.raises(WebSocketDisconnect) as socket_denied:
            with remote.websocket_connect(
                "/api/v1/adapters/connect",
                headers={"X-Forwarded-For": "127.0.0.1"},
            ):
                pass
        policy.add_device("Demo phone", PHONE_MAC)
        allowed = remote.get("/api/v1/fabric/healthz")

    assert denied.status_code == 403
    assert denied.json()["code"] == "LAN_ACCESS_DENIED"
    assert denied.headers["cache-control"] == "no-store"
    assert socket_denied.value.code == 1008
    assert allowed.status_code == 200
    assert resolver.requests == [PHONE_IP, PHONE_IP, PHONE_IP]


def test_allowlist_management_is_local_authenticated_and_persistent(tmp_path: Path) -> None:
    state_path = tmp_path / "lan-access.json"
    resolver = StaticResolver({PHONE_IP: PHONE_MAC})
    policy = LanMacAccessPolicy(
        state_path=state_path,
        enabled=True,
        resolver=resolver,
        lan_origin="http://172.30.1.4:8766",
        clock=lambda: NOW,
    )
    app = create_fabric_app(
        database_path=tmp_path / "fabric.sqlite3",
        clock=lambda: NOW,
        fabric_bootstrap_identities=(admin_identity(),),
        lan_access_policy=policy,
        maintenance_interval=None,
    )

    with TestClient(app, client=("127.0.0.1", 50000)) as local:
        unauthenticated = local.get("/api/v1/fabric/lan-access")
        added = local.post(
            "/api/v1/fabric/lan-access/devices",
            headers=ADMIN_HEADERS,
            json={"displayName": "Spare phone", "macAddress": "02-11-22-33-44-55"},
        )
        linked = local.post(
            f"/api/v1/fabric/lan-access/devices/{PHONE_MAC}/access-link",
            headers=ADMIN_HEADERS,
        )
        linked_url = urlsplit(linked.json()["accessUrl"])
        linked_ticket = parse_qs(linked_url.fragment)["android-console-ticket"][0]
        redeemed = local.post(
            "/api/v1/fabric/auth/console-tickets/redeem",
            json={"ticket": linked_ticket},
        )
        remote_principal = local.get(
            "/api/v1/fabric/auth/whoami",
            headers={"Authorization": f"Bearer {redeemed.json()['accessToken']}"},
        )

    reloaded = LanMacAccessPolicy(
        state_path=state_path,
        enabled=True,
        resolver=resolver,
        clock=lambda: NOW,
    )

    assert unauthenticated.status_code == 401
    assert added.status_code == 200
    assert linked.status_code == 200
    assert linked_url.scheme == "http"
    assert linked_url.netloc == "172.30.1.4:8766"
    assert linked_url.path == "/fabric"
    assert redeemed.status_code == 200
    assert remote_principal.json()["actorType"] == "android_controller"
    assert "fabric.lan_access.manage" not in remote_principal.json()["permissions"]
    assert added.json()["snapshot"] == {
        "schemaVersion": "1.0",
        "enabled": True,
        "lanOrigin": "http://172.30.1.4:8766",
        "devices": [
            {
                "displayName": "Spare phone",
                "macAddress": PHONE_MAC,
                "addedAt": NOW.isoformat().replace("+00:00", "Z"),
            }
        ],
        "operations": {"manage": True, "enrollUsbAndroid": False},
    }
    assert reloaded.allows(PHONE_IP) is True

    with TestClient(app, client=(PHONE_IP, 50001)) as remote:
        remote_management = remote.get(
            "/api/v1/fabric/lan-access",
            headers=ADMIN_HEADERS,
        )

    assert remote_management.status_code == 403
    assert remote_management.json()["code"] == "LAN_ACCESS_LOCAL_ONLY"


def test_local_manager_can_enroll_current_usb_android_wifi_mac(tmp_path: Path) -> None:
    adb = RecordingAdb()
    policy = LanMacAccessPolicy(
        state_path=tmp_path / "lan-access.json",
        enabled=True,
        resolver=StaticResolver({PHONE_IP: PHONE_MAC}),
        lan_origin="http://192.168.50.10:8766",
        clock=lambda: NOW,
    )
    android = AndroidControllerService(
        port=8766,
        adb_path="adb-test",
        run_process=adb,
        monitor_interval=None,
        clock=lambda: NOW,
    )
    app = create_fabric_app(
        database_path=tmp_path / "fabric.sqlite3",
        clock=lambda: NOW,
        fabric_bootstrap_identities=(admin_identity(),),
        android_controller_service=android,
        lan_access_policy=policy,
        maintenance_interval=None,
    )

    with TestClient(app, client=("127.0.0.1", 50000)) as local:
        enrolled = local.post(
            "/api/v1/fabric/lan-access/enroll-usb-android",
            headers=ADMIN_HEADERS,
        )

    assert enrolled.status_code == 200
    assert enrolled.json()["snapshot"]["devices"] == [
        {
            "displayName": "SM-N971N (Wi-Fi)",
            "macAddress": PHONE_MAC,
            "addedAt": NOW.isoformat().replace("+00:00", "Z"),
        }
    ]
    launch = next(command for command in adb.commands if "android.intent.action.VIEW" in command)
    launched_url = urlsplit(launch[-1])
    assert launched_url.scheme == "http"
    assert launched_url.netloc == "192.168.50.10:8766"
    assert launched_url.path == "/fabric"
    ticket = parse_qs(launched_url.fragment)["android-console-ticket"][0]
    assert len(ticket) >= 32
