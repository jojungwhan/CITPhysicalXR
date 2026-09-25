from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from cit_runtime.fabric_auth import FABRIC_PERMISSIONS, FabricBootstrapIdentity
from cit_runtime.fabric_plug_gateways import (
    GatewayConfiguration,
    GatewayKnownPlug,
    PlugGatewayService,
)
from cit_runtime.fabric_service import create_fabric_app
from cit_runtime.fabric_unlock_automation import (
    RemotePlugPowerRequest,
    UnlockAutomationConfigurationRequest,
    UnlockAutomationError,
    UnlockAutomationService,
    UnlockEventRequest,
    UnlockPowerResult,
    sign_remote_power_event,
    sign_unlock_event,
)
from fastapi.testclient import TestClient

TOKEN = "gateway-test-" + "x" * 40
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def configuration() -> GatewayConfiguration:
    return GatewayConfiguration(
        siteId="academy",
        displayName="Academy",
        origin="https://academy.example.ts.net",
        deviceId="desktop-0123456789abcdef",
        secret="s" * 43,
    )


def identity(*, room_id: str | None = None) -> FabricBootstrapIdentity:
    return FabricBootstrapIdentity(
        identity_id="test",
        token=TOKEN,
        actor_type="administrator",
        roles=("administrator",),
        permissions=tuple(FABRIC_PERMISSIONS),
        room_id=room_id,
    )


@pytest.mark.asyncio
async def test_gateway_reads_do_not_switch_and_sequences_survive_restart(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def transport(
        config: GatewayConfiguration, route: str, body: dict[str, object], signature: str
    ) -> dict[str, object]:
        assert route == "state"
        assert len(signature) == 64
        calls.append(body)
        return {
            "siteId": config.siteId,
            "displayName": "Academy",
            "generatedAt": datetime.now(UTC).isoformat(),
            "plugs": [{"nodeId": "plug-a", "displayName": "Lamp", "available": True, "on": False}],
        }

    service = PlugGatewayService(
        [configuration()], tmp_path / "sequences.sqlite3", transport=transport
    )
    snapshots = await service.snapshots()
    assert snapshots[0].connected is True
    assert snapshots[0].plugs[0].on is False
    assert "secret" not in snapshots[0].model_dump_json()
    restored = PlugGatewayService(
        [configuration()], tmp_path / "sequences.sqlite3", transport=transport
    )
    await restored.snapshots()
    assert calls[1]["sequence"] > calls[0]["sequence"]  # type: ignore[operator]


@pytest.mark.asyncio
async def test_gateway_timeout_clears_stale_states_and_never_retries_power(tmp_path: Path) -> None:
    calls: list[str] = []

    def transport(
        config: GatewayConfiguration, route: str, body: dict[str, object], signature: str
    ) -> dict[str, object]:
        calls.append(route)
        raise TimeoutError("private diagnostic and credential must not leak")

    service = PlugGatewayService(
        [configuration()], tmp_path / "sequences.sqlite3", transport=transport
    )
    snapshot = (await service.snapshots())[0]
    assert snapshot.connected is False
    assert snapshot.plugs == []
    assert "credential" not in snapshot.model_dump_json()
    with pytest.raises(UnlockAutomationError, match="unknown"):
        await service.power("academy", True, ["plug-a"])
    assert calls == ["state", "power"]


def test_gateway_routes_require_authentication_scope_and_physical_enablement(
    tmp_path: Path,
) -> None:
    service = PlugGatewayService([configuration()], tmp_path / "sequences.sqlite3")
    for scope in ({}, {"room_id": "room-a"}):
        app = create_fabric_app(
            plug_gateway_service=service,
            fabric_bootstrap_identities=[identity(**scope)],
            maintenance_interval=None,
        )
        with TestClient(app) as client:
            assert client.get("/api/v1/fabric/plug-gateways").status_code == 401
            response = client.post(
                "/api/v1/fabric/plug-gateways/academy/power",
                headers=HEADERS,
                json={"on": True, "selectedNodeIds": ["plug-a"]},
            )
            assert response.status_code == 403
            if scope:
                assert (
                    client.get("/api/v1/fabric/plug-gateways", headers=HEADERS).status_code == 403
                )


@pytest.mark.asyncio
async def test_desktop_selection_is_signed_and_limited_to_saved_plugs(tmp_path: Path) -> None:
    service = UnlockAutomationService(
        state_path=tmp_path / "remote.json",
        lan_origin=None,
        remote_origin="https://academy.example.ts.net",
    )
    phone = service.create_pairing("Existing phone")
    service.commit_pairing(phone)
    desktop = service.create_pairing("Windows", device_kind="desktop")
    service.commit_pairing(desktop)
    service.configure(
        UnlockAutomationConfigurationRequest(enabled=False, selectedNodeIds=["plug-a", "plug-b"]),
        known_node_ids=["plug-a", "plug-b"],
    )
    calls: list[tuple[str, ...]] = []

    async def run(nodes: tuple[str, ...], actor: str, event: str, on: bool) -> UnlockPowerResult:
        calls.append(nodes)
        return UnlockPowerResult(
            requestedCount=len(nodes),
            acceptedCount=len(nodes),
            failedNodeIds=[],
            on=on,
            message="Accepted",
        )

    request = RemotePlugPowerRequest(
        deviceId=desktop.device_id,
        eventId=uuid4(),
        sequence=1,
        occurredAtEpochMs=int(datetime.now(UTC).timestamp() * 1000),
        on=False,
        selectedNodeIds=["plug-a"],
    )
    signature = sign_remote_power_event(request, desktop.secret)
    with pytest.raises(UnlockAutomationError, match="signature"):
        await service.accept_remote_power(
            request.model_copy(update={"selectedNodeIds": ["plug-b"]}), signature, run
        )
    result = await service.accept_remote_power(request, signature, run)
    assert result.accepted
    assert calls == [("plug-a",)]
    foreign = request.model_copy(update={"sequence": 2, "selectedNodeIds": ["foreign"]})
    with pytest.raises(UnlockAutomationError, match="saved"):
        await service.accept_remote_power(
            foreign, sign_remote_power_event(foreign, desktop.secret), run
        )
    assert calls == [("plug-a",)]
    assert len(service.snapshot(can_manage=True, can_install_and_pair=False).companions) == 2


def test_desktop_pairing_requires_local_unscoped_administrator(tmp_path: Path) -> None:
    service = UnlockAutomationService(
        state_path=tmp_path / "remote.json",
        lan_origin=None,
        remote_origin="https://academy.example.ts.net",
    )
    service.commit_pairing(service.create_pairing("Phone"))
    app = create_fabric_app(
        unlock_automation_service=service,
        fabric_bootstrap_identities=[identity()],
        maintenance_interval=None,
    )
    route = "/api/v1/fabric/unlock-automation/desktop-pairings"
    with TestClient(app, client=("127.0.0.1", 1234)) as client:
        assert client.post(route, json={"displayName": "Windows"}).status_code == 401
        paired = client.post(route, headers=HEADERS, json={"displayName": "Windows"})
        assert paired.status_code == 201
        assert paired.json()["deviceId"].startswith("desktop-")
        assert len(paired.json()["secret"]) >= 43
        snapshot = client.get("/api/v1/fabric/unlock-automation", headers=HEADERS)
        assert paired.json()["secret"] not in snapshot.text
    with TestClient(app, client=("192.168.1.9", 1234)) as client:
        assert (
            client.post(route, headers=HEADERS, json={"displayName": "Windows"}).status_code == 403
        )


@pytest.mark.parametrize(
    "origin",
    [
        "http://academy.example.ts.net",
        "https://example.com",
        "https://academy.example.ts.net/extra",
    ],
)
def test_gateway_origins_are_fixed_private_https(origin: str) -> None:
    with pytest.raises(ValueError):
        GatewayConfiguration.model_validate({**configuration().model_dump(), "origin": origin})


@pytest.mark.parametrize("unavailable", [False, True])
def test_global_stop_sends_off_once_and_reports_unreachable_gateways(
    tmp_path: Path, unavailable: bool
) -> None:
    calls: list[dict[str, object]] = []

    def transport(
        config: GatewayConfiguration, route: str, body: dict[str, object], signature: str
    ) -> dict[str, object]:
        assert route == "power"
        calls.append(body)
        if unavailable:
            raise TimeoutError()
        return {
            "siteId": config.siteId,
            "displayName": "Academy",
            "accepted": True,
            "outcome": "succeeded",
            "requestedCount": 4,
            "acceptedCount": 4,
            "on": False,
            "message": "OFF accepted",
        }

    service = PlugGatewayService(
        [configuration()], tmp_path / "sequences.sqlite3", transport=transport
    )
    app = create_fabric_app(
        plug_gateway_service=service,
        fabric_bootstrap_identities=[identity()],
        allow_physical_fabric=True,
        maintenance_interval=None,
    )
    with TestClient(app) as client:
        result = client.post("/api/v1/fabric/safety/stop-all", headers=HEADERS).json()
    assert result["status"] == ("partial" if unavailable else "completed")
    assert result["failedGatewayIds"] == (["academy"] if unavailable else [])
    assert result["stoppedGatewayIds"] == ([] if unavailable else ["academy"])
    assert len(calls) == 1
    assert calls[0]["on"] is False
    assert calls[0]["selectedNodeIds"] is None


@pytest.mark.asyncio
async def test_initial_offline_gateway_keeps_remembered_plugs_visible(tmp_path: Path) -> None:
    config = configuration().model_copy(
        update={"knownPlugs": [GatewayKnownPlug(nodeId="plug-a", displayName="Lamp")]}
    )

    def transport(
        config: GatewayConfiguration, route: str, body: dict[str, object], signature: str
    ) -> dict[str, object]:
        raise OSError("Offline")

    service = PlugGatewayService([config], tmp_path / "sequences.sqlite3", transport=transport)
    snapshot = (await service.snapshots())[0]
    assert snapshot.connected is False
    assert snapshot.plugs[0].displayName == "Lamp"
    assert snapshot.plugs[0].available is False
    assert snapshot.plugs[0].on is None


@pytest.mark.asyncio
async def test_desktop_pairing_cannot_trigger_phone_automation(tmp_path: Path) -> None:
    service = UnlockAutomationService(
        state_path=tmp_path / "remote.json",
        lan_origin=None,
        remote_origin="https://academy.example.ts.net",
    )
    desktop = service.create_pairing("Windows", device_kind="desktop")
    service.commit_pairing(desktop)
    event = UnlockEventRequest(
        deviceId=desktop.device_id,
        eventId=uuid4(),
        sequence=1,
        occurredAtEpochMs=int(datetime.now(UTC).timestamp() * 1000),
    )

    async def run(nodes: tuple[str, ...], actor: str, event_id: str) -> UnlockPowerResult:
        raise AssertionError("Desktop credentials must not trigger automation")

    with pytest.raises(UnlockAutomationError, match="only access remote"):
        await service.accept_event(event, sign_unlock_event(event, desktop.secret), run)
