from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cit_integration_sdk import FabricConnectionConfiguration
from cit_matter_smart_plug import (
    PLUGIN_ID,
    MatterSmartPlug,
    MatterSmartPlugConfiguration,
    build_manifest,
    build_node,
    discover_plug_endpoints,
)
from cit_matter_smart_plug.bridge import BridgeConfiguration, FabricMatterBridge
from cit_matter_smart_plug.matter_client import validate_setup_code

NOW = datetime(2026, 8, 22, 8, 0, tzinfo=UTC)


def test_inventory_exposes_only_standard_on_off_plugin_unit_endpoints() -> None:
    endpoints = discover_plug_endpoints(
        [
            {
                "node_id": 12345678901234567,
                "available": True,
                "attributes": {
                    "0/40/1": "Cloudless Co",
                    "0/40/3": "Classroom Outlet",
                    "0/40/5": "Science lamp",
                    "1/29/0": [{"deviceType": 0x010A, "revision": 2}],
                    "1/6/0": False,
                    "2/29/0": [{"deviceType": 0x0100, "revision": 3}],
                    "2/6/0": False,
                    "3/6/0": False,
                },
            }
        ]
    )

    assert len(endpoints) == 1
    endpoint = endpoints[0]
    assert endpoint.matter_node_id == 12345678901234567
    assert endpoint.endpoint_id == 1
    assert endpoint.cit_node_id == "matter-2bdc545d6b4b87-ep1"
    assert endpoint.display_name == "Science lamp"


def test_contract_declares_no_vendor_cloud_or_arbitrary_cluster_access() -> None:
    manifest = build_manifest()
    node = build_node(
        at=NOW,
        host_id="host-a",
        site_id="site-a",
        room_id="room-a",
        node_id="matter-abcd-ep1",
        matter_node_id=43981,
        endpoint_id=1,
        display_name="Lab lamp",
        vendor_name="Matter vendor",
        product_name="Wi-Fi plug",
    )

    assert manifest.pluginId == PLUGIN_ID
    assert [item.name for item in manifest.consumedCapabilities] == ["power.switch.set"]
    assert [item.name for item in manifest.publishedCapabilities] == ["power.switch.state"]
    assert node.metadata.model_dump()["cloudDependency"] is False
    assert node.metadata.model_dump()["vendorAccountRequired"] is False
    assert node.metadata.model_dump()["arbitraryClustersExposed"] is False


class FakeMatterClient:
    def __init__(self) -> None:
        self.nodes = {7: {"available": True, "attributes": {"1/6/0": False}}}
        self.state = False
        self.commands: list[bool] = []
        self.closed = False

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True

    async def refresh_node(self, node_id: int) -> dict[str, object]:
        return self.nodes[node_id]

    async def read_on_off(self, node_id: int, endpoint_id: int) -> bool:
        assert (node_id, endpoint_id) == (7, 1)
        return self.state

    async def set_on_off(self, node_id: int, endpoint_id: int, on: bool) -> None:
        assert (node_id, endpoint_id) == (7, 1)
        self.commands.append(on)
        self.state = on


def test_backend_suppresses_duplicate_physical_actions_and_verifies_state() -> None:
    async def scenario() -> None:
        client = FakeMatterClient()
        plug = MatterSmartPlug(
            MatterSmartPlugConfiguration(
                server_url="ws://127.0.0.1:5580/ws",
                matter_node_id=7,
                endpoint_id=1,
            ),
            client=client,
        )
        assert await plug.start() is False
        assert await plug.set_power(False) is False
        assert client.commands == []
        assert await plug.set_power(True) is True
        assert client.commands == [True]
        await plug.close()
        assert client.closed is True

    asyncio.run(scenario())


def test_unstarted_session_publishes_no_event_and_activation_removal_ends_state_loop(
    tmp_path: Path,
) -> None:
    class RecordingFabricClient:
        def __init__(self) -> None:
            self.events: list[dict[str, object]] = []

        async def publish_event(self, **event: object) -> None:
            self.events.append(event)

    async def scenario() -> None:
        activation_file = tmp_path / "matter-active.flag"
        activation_file.write_text("connected\n", encoding="ascii")
        backend = MatterSmartPlug(
            MatterSmartPlugConfiguration(
                server_url="ws://127.0.0.1:5580/ws",
                matter_node_id=7,
                endpoint_id=1,
            ),
            client=FakeMatterClient(),
        )
        await backend.start()
        bridge = FabricMatterBridge(
            BridgeConfiguration(
                connection=FabricConnectionConfiguration(
                    adapter_url="ws://127.0.0.1:8766/api/v1/adapters/connect",
                    adapter_token="test-adapter-token",
                    fabric_origin="http://127.0.0.1:8766",
                    session_id="session-a",
                    site_id="site-a",
                    room_id="room-a",
                ),
                host_id="host-a",
                node_id="matter-7-ep1",
                activation_file=activation_file,
                matter_node_id=7,
                endpoint_id=1,
                display_name="Test plug",
                vendor_name="Matter",
                product_name="On/Off Plug-in Unit",
                poll_interval_seconds=1,
            ),
            backend=backend,
        )
        client = RecordingFabricClient()
        state_task = asyncio.create_task(bridge._publish_state_changes(client))  # type: ignore[arg-type]
        await asyncio.sleep(0.05)
        activation_file.unlink()
        await asyncio.wait_for(state_task, timeout=1)
        assert client.events == []
        await backend.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "code",
    ["MT:Y.K9042C00KA0648G00", "3497-701-1232", "123456789012345678901"],
)
def test_setup_code_accepts_qr_and_manual_forms(code: str) -> None:
    assert validate_setup_code(code) == code


@pytest.mark.parametrize("code", ["", "MT:short", "3497-701", "not-a-code"])
def test_setup_code_rejects_non_matter_values(code: str) -> None:
    with pytest.raises(ValueError, match="Matter"):
        validate_setup_code(code)
