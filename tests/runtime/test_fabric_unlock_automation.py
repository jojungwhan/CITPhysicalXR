from __future__ import annotations

import base64
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from cit_matter_smart_plug import build_manifest, build_node
from cit_protocol import FabricResolvedCommand
from cit_runtime.fabric import FabricDispatchOutcome, InteractionFabric
from cit_runtime.fabric_android import AndroidControllerService
from cit_runtime.fabric_auth import FABRIC_PERMISSIONS, FabricBootstrapIdentity
from cit_runtime.fabric_course import smart_plug_course_pack
from cit_runtime.fabric_lan_access import LanMacAccessPolicy
from cit_runtime.fabric_repository import SQLiteFabricRepository
from cit_runtime.fabric_service import create_fabric_app
from cit_runtime.fabric_unlock_automation import (
    ToggleEventRequest,
    UnlockAutomationConfigurationRequest,
    UnlockAutomationError,
    UnlockAutomationService,
    UnlockEventRequest,
    UnlockPowerResult,
    sign_toggle_event,
    sign_unlock_event,
    toggle_configured_smart_plugs,
    turn_on_configured_smart_plugs,
)
from fastapi.testclient import TestClient

NOW = datetime(2026, 9, 10, 5, 0, 0, tzinfo=UTC)
ADMIN_TOKEN = "cit-admin-" + "a" * 40
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
PHONE_MAC = "02:11:22:33:44:55"


def admin_identity() -> FabricBootstrapIdentity:
    return FabricBootstrapIdentity(
        identity_id="admin-a",
        token=ADMIN_TOKEN,
        actor_type="administrator",
        roles=("administrator",),
        permissions=tuple(sorted(FABRIC_PERMISSIONS)),
    )


class PairingAdb:
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
                f'Wifi is connected to "Classroom"\nWifiInfo: MAC: {PHONE_MAC}, Security type: 2\n'
            )
        elif "install" in arguments or arguments[-3:] == (
            "pm",
            "clear",
            "com.cit.controltower.companion",
        ):
            output = "Success\n"
        else:
            output = ""
        return subprocess.CompletedProcess(arguments, 0, output, "")


def event(device_id: str, *, sequence: int = 1, at: datetime = NOW) -> UnlockEventRequest:
    return UnlockEventRequest(
        deviceId=device_id,
        eventId=uuid4(),
        sequence=sequence,
        occurredAtEpochMs=int(at.timestamp() * 1_000),
    )


def toggle_event(
    device_id: str,
    *,
    sequence: int = 1,
    at: datetime = NOW,
) -> ToggleEventRequest:
    return ToggleEventRequest(
        deviceId=device_id,
        eventId=uuid4(),
        sequence=sequence,
        occurredAtEpochMs=int(at.timestamp() * 1_000),
    )


@pytest.mark.asyncio
async def test_signed_unlock_is_one_shot_and_never_exposes_pairing_secret(
    tmp_path: Path,
) -> None:
    calls: list[tuple[tuple[str, ...], str, str]] = []

    async def run(
        node_ids: tuple[str, ...],
        actor_id: str,
        event_id: str,
    ) -> UnlockPowerResult:
        calls.append((node_ids, actor_id, event_id))
        return UnlockPowerResult(
            requestedCount=len(node_ids),
            acceptedCount=len(node_ids),
            failedNodeIds=[],
            message="accepted",
        )

    service = UnlockAutomationService(
        state_path=tmp_path / "unlock.json",
        lan_origin="http://192.168.50.10:8766",
        clock=lambda: NOW,
    )
    pairing = service.create_pairing("Spare phone")
    assert "?" not in pairing.provisioning_uri
    assert "&" not in pairing.provisioning_uri
    encoded_pairing = pairing.provisioning_uri.rsplit("/", maxsplit=1)[1]
    decoded_pairing = json.loads(
        base64.urlsafe_b64decode(encoded_pairing + "=" * (-len(encoded_pairing) % 4))
    )
    assert decoded_pairing == {
        "origin": "http://192.168.50.10:8766",
        "deviceId": pairing.device_id,
        "secret": pairing.secret,
        "name": "Spare phone",
    }
    service.commit_pairing(pairing)
    with pytest.raises(UnlockAutomationError) as already_paired:
        service.create_pairing("Another phone")
    assert already_paired.value.code == "UNLOCK_AUTOMATION_PHONE_ALREADY_PAIRED"
    service.configure(
        UnlockAutomationConfigurationRequest(
            enabled=True,
            selectedNodeIds=["plug-a", "plug-b"],
        ),
        known_node_ids=("plug-a", "plug-b"),
    )
    unlock = event(pairing.device_id)

    result = await service.accept_event(unlock, sign_unlock_event(unlock, pairing.secret), run)
    snapshot = service.snapshot(can_manage=True, can_install_and_pair=False)

    assert result.accepted is True
    assert result.outcome == "succeeded"
    assert calls == [(("plug-a", "plug-b"), pairing.device_id, str(unlock.eventId))]
    assert snapshot.companion is not None
    assert snapshot.companion.lastSeenAt == NOW
    assert pairing.secret not in snapshot.model_dump_json()
    assert pairing.secret not in repr(pairing)

    with pytest.raises(UnlockAutomationError) as replayed:
        await service.accept_event(unlock, sign_unlock_event(unlock, pairing.secret), run)
    assert replayed.value.code == "UNLOCK_AUTOMATION_EVENT_REPLAYED"
    assert len(calls) == 1

    disabled_with_offline_targets = service.configure(
        UnlockAutomationConfigurationRequest(
            enabled=False,
            selectedNodeIds=["plug-a", "plug-b"],
        ),
        known_node_ids=(),
    )
    assert disabled_with_offline_targets.enabled is False
    assert disabled_with_offline_targets.selectedNodeIds == ["plug-a", "plug-b"]


@pytest.mark.asyncio
async def test_disabled_stale_and_forged_unlock_events_never_run_commands(
    tmp_path: Path,
) -> None:
    calls = 0

    async def run(
        _node_ids: tuple[str, ...],
        _actor_id: str,
        _event_id: str,
    ) -> UnlockPowerResult:
        nonlocal calls
        calls += 1
        raise AssertionError("disabled or invalid events must not dispatch")

    service = UnlockAutomationService(
        state_path=tmp_path / "unlock.json",
        lan_origin="http://192.168.50.10:8766",
        clock=lambda: NOW,
    )
    pairing = service.create_pairing("Spare phone")
    service.commit_pairing(pairing)
    disabled_event = event(pairing.device_id)

    disabled = await service.accept_event(
        disabled_event,
        sign_unlock_event(disabled_event, pairing.secret),
        run,
    )
    assert disabled.outcome == "disabled"

    forged_event = event(pairing.device_id, sequence=2)
    with pytest.raises(UnlockAutomationError) as forged:
        await service.accept_event(forged_event, "0" * 64, run)
    assert forged.value.code == "UNLOCK_AUTOMATION_SIGNATURE_INVALID"

    stale_at = NOW - timedelta(minutes=3)
    stale_event = event(pairing.device_id, sequence=2, at=stale_at)
    with pytest.raises(UnlockAutomationError) as stale:
        await service.accept_event(stale_event, sign_unlock_event(stale_event, pairing.secret), run)
    assert stale.value.code == "UNLOCK_AUTOMATION_EVENT_STALE"
    assert calls == 0


@pytest.mark.asyncio
async def test_signed_phone_toggle_is_domain_separated_and_shares_replay_sequence(
    tmp_path: Path,
) -> None:
    calls: list[tuple[tuple[str, ...], str, str]] = []

    async def run(
        node_ids: tuple[str, ...],
        actor_id: str,
        event_id: str,
    ) -> UnlockPowerResult:
        calls.append((node_ids, actor_id, event_id))
        return UnlockPowerResult(
            requestedCount=len(node_ids),
            acceptedCount=len(node_ids),
            failedNodeIds=[],
            on=False,
            message="turned off",
        )

    service = UnlockAutomationService(
        state_path=tmp_path / "unlock.json",
        lan_origin="http://192.168.50.10:8766",
        clock=lambda: NOW,
    )
    pairing = service.create_pairing("Spare phone")
    service.commit_pairing(pairing)
    service.configure(
        UnlockAutomationConfigurationRequest(
            enabled=False,
            selectedNodeIds=["plug-a", "plug-b"],
        ),
        known_node_ids=("plug-a", "plug-b"),
    )
    toggle = toggle_event(pairing.device_id)

    with pytest.raises(UnlockAutomationError) as wrong_domain:
        await service.accept_toggle(toggle, sign_unlock_event(toggle, pairing.secret), run)
    assert wrong_domain.value.code == "UNLOCK_AUTOMATION_SIGNATURE_INVALID"

    result = await service.accept_toggle(toggle, sign_toggle_event(toggle, pairing.secret), run)

    assert result.accepted is True
    assert result.on is False
    assert calls == [(("plug-a", "plug-b"), pairing.device_id, str(toggle.eventId))]
    replayed_unlock = event(pairing.device_id, sequence=1)
    with pytest.raises(UnlockAutomationError) as replayed:
        await service.accept_event(
            replayed_unlock,
            sign_unlock_event(replayed_unlock, pairing.secret),
            run,
        )
    assert replayed.value.code == "UNLOCK_AUTOMATION_EVENT_REPLAYED"


@pytest.mark.asyncio
async def test_unlock_power_uses_an_armed_session_and_exact_configured_plugs() -> None:
    dispatched: list[FabricResolvedCommand] = []

    async def dispatch(
        command: FabricResolvedCommand,
        _node: object,
    ) -> FabricDispatchOutcome:
        dispatched.append(command)
        return FabricDispatchOutcome(accepted=True)

    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW, allow_physical=True)
        fabric.set_dispatcher(dispatch)
        nodes = tuple(
            build_node(
                at=NOW,
                host_id="edge-a",
                site_id="local-site",
                room_id="local-room",
                node_id=f"plug-{suffix}",
                matter_node_id=matter_id,
                endpoint_id=1,
                display_name=f"Plug {suffix.upper()}",
                vendor_name="Matter",
                product_name="approved-load-plug",
                electrical_telemetry=True,
            )
            for suffix, matter_id in (("a", 11), ("b", 12))
        )
        fabric.register_plugin_and_nodes(build_manifest(), nodes)
        fabric.install_course_pack(smart_plug_course_pack(), actor_id="system.bootstrap")

        result = await turn_on_configured_smart_plugs(
            fabric,
            ("plug-a", "plug-b"),
            "android-0123456789abcdef",
            str(uuid4()),
            clock=lambda: NOW,
        )
        [session] = fabric.list_sessions()

    assert result.acceptedCount == 2
    assert session.state.value == "active"
    assert session.armed is True
    assert session.createdBy == "android-0123456789abcdef"
    assert {command.targetNodeId for command in dispatched} == {"plug-a", "plug-b"}
    assert all(command.parameters.model_dump(mode="json") == {"on": True} for command in dispatched)
    assert all(command.priority.value == "lesson_automation" for command in dispatched)


@pytest.mark.asyncio
async def test_unlock_power_fails_closed_when_any_configured_plug_is_missing() -> None:
    dispatched: list[FabricResolvedCommand] = []

    async def dispatch(
        command: FabricResolvedCommand,
        _node: object,
    ) -> FabricDispatchOutcome:
        dispatched.append(command)
        return FabricDispatchOutcome(accepted=True)

    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW, allow_physical=True)
        fabric.set_dispatcher(dispatch)
        node = build_node(
            at=NOW,
            host_id="edge-a",
            site_id="local-site",
            room_id="local-room",
            node_id="plug-a",
            matter_node_id=11,
            endpoint_id=1,
            display_name="Plug A",
            vendor_name="Matter",
            product_name="approved-load-plug",
            electrical_telemetry=True,
        )
        fabric.register_plugin_and_nodes(build_manifest(), (node,))
        fabric.install_course_pack(smart_plug_course_pack(), actor_id="system.bootstrap")

        result = await turn_on_configured_smart_plugs(
            fabric,
            ("plug-a", "plug-missing"),
            "android-0123456789abcdef",
            str(uuid4()),
            clock=lambda: NOW,
        )

    assert result.acceptedCount == 0
    assert result.failedNodeIds == ["plug-missing"]
    assert dispatched == []


@pytest.mark.parametrize(
    ("reported_states", "expected_on"),
    [((True, True), False), ((True, False), True)],
)
@pytest.mark.asyncio
async def test_phone_toggle_normalizes_the_exact_group_from_reported_power_state(
    reported_states: tuple[bool, bool],
    expected_on: bool,
) -> None:
    dispatched: list[FabricResolvedCommand] = []

    async def dispatch(
        command: FabricResolvedCommand,
        _node: object,
    ) -> FabricDispatchOutcome:
        dispatched.append(command)
        return FabricDispatchOutcome(accepted=True)

    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW, allow_physical=True)
        fabric.set_dispatcher(dispatch)
        nodes = []
        for index, reported_on in enumerate(reported_states, start=1):
            node = build_node(
                at=NOW,
                host_id="edge-a",
                site_id="local-site",
                room_id="local-room",
                node_id=f"plug-{index}",
                matter_node_id=10 + index,
                endpoint_id=1,
                display_name=f"Plug {index}",
                vendor_name="Matter",
                product_name="approved-load-plug",
                electrical_telemetry=True,
            )
            metadata = node.metadata.model_dump(mode="json")
            metadata["healthMetrics"] = {"on": reported_on}
            nodes.append(
                node.model_copy(update={"metadata": type(node.metadata).model_validate(metadata)})
            )
        fabric.register_plugin_and_nodes(build_manifest(), tuple(nodes))
        fabric.install_course_pack(smart_plug_course_pack(), actor_id="system.bootstrap")

        result = await toggle_configured_smart_plugs(
            fabric,
            ("plug-1", "plug-2"),
            "android-0123456789abcdef",
            str(uuid4()),
            clock=lambda: NOW,
        )

    assert result.acceptedCount == 2
    assert result.on is expected_on
    assert all(
        command.parameters.model_dump(mode="json") == {"on": expected_on} for command in dispatched
    )


def test_unlock_automation_administration_pairs_once_without_exposing_secret(
    tmp_path: Path,
) -> None:
    apk = tmp_path / "control-tower.apk"
    apk.write_bytes(b"PK\x03\x04test-apk")
    adb = PairingAdb()
    android = AndroidControllerService(
        port=8766,
        adb_path="adb-test",
        run_process=adb,
        monitor_interval=None,
        clock=lambda: NOW,
    )
    lan_access = LanMacAccessPolicy(
        state_path=tmp_path / "lan-access.json",
        enabled=True,
        lan_origin="http://192.168.50.10:8766",
        clock=lambda: NOW,
    )
    unlock = UnlockAutomationService(
        state_path=tmp_path / "unlock.json",
        lan_origin="http://192.168.50.10:8766",
        companion_apk_path=apk,
        clock=lambda: NOW,
    )
    app = create_fabric_app(
        database_path=tmp_path / "fabric.sqlite3",
        clock=lambda: NOW,
        fabric_bootstrap_identities=(admin_identity(),),
        android_controller_service=android,
        lan_access_policy=lan_access,
        unlock_automation_service=unlock,
        maintenance_interval=None,
    )

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        initial = client.get("/api/v1/fabric/unlock-automation", headers=ADMIN_HEADERS)
        paired = client.post(
            "/api/v1/fabric/unlock-automation/companion/pair-usb",
            headers=ADMIN_HEADERS,
            json={"displayName": "Spare phone"},
        )
        paired_state = json.loads((tmp_path / "unlock.json").read_text(encoding="utf-8"))
        unlock_event = event(paired_state["companion"]["deviceId"])
        triggered_while_disabled = client.post(
            "/api/v1/fabric/unlock-automation/events",
            headers={
                "X-CIT-Unlock-Signature": sign_unlock_event(
                    unlock_event,
                    paired_state["companion"]["secret"],
                )
            },
            json=unlock_event.model_dump(mode="json"),
        )
        phone_toggle = toggle_event(paired_state["companion"]["deviceId"], sequence=2)
        toggled_without_targets = client.post(
            "/api/v1/fabric/unlock-automation/toggle",
            headers={
                "X-CIT-Toggle-Signature": sign_toggle_event(
                    phone_toggle,
                    paired_state["companion"]["secret"],
                )
            },
            json=phone_toggle.model_dump(mode="json"),
        )
        paired_again = client.post(
            "/api/v1/fabric/unlock-automation/companion/pair-usb",
            headers=ADMIN_HEADERS,
            json={"displayName": "Another phone"},
        )

    assert initial.status_code == 200, initial.text
    assert initial.json()["operations"] == {"manage": True, "installAndPair": True}
    assert paired.status_code == 200
    assert paired.json()["snapshot"]["enabled"] is False
    assert paired.json()["snapshot"]["companion"]["displayName"] == "Spare phone"
    assert "secret" not in paired.text.casefold()
    assert triggered_while_disabled.status_code == 200
    assert triggered_while_disabled.json()["outcome"] == "disabled"
    assert toggled_without_targets.status_code == 200
    assert toggled_without_targets.json()["outcome"] == "failed"
    assert toggled_without_targets.json()["requestedCount"] == 0
    assert paired_again.status_code == 409
    assert paired_again.json()["code"] == "UNLOCK_AUTOMATION_PHONE_ALREADY_PAIRED"
    assert (
        lan_access.snapshot(can_manage=True, can_enroll_usb_android=True).devices[0].macAddress
        == PHONE_MAC
    )
    provisioning = next(
        command[-1] for command in adb.commands if command[-1].startswith("cit-control-tower://")
    )
    assert "?" not in provisioning
    assert "&" not in provisioning
