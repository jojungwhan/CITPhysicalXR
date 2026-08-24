from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from cit_integration_sdk import FabricAdapterClient, FabricConnectionConfiguration
from cit_matter_smart_plug import (
    ELECTRICAL_STATE_CAPABILITY,
    PLUGIN_ID,
    ElectricalMeasurements,
    MatterSmartPlug,
    MatterSmartPlugConfiguration,
    build_manifest,
    build_node,
    discover_plug_endpoints,
    extract_electrical_measurements,
)
from cit_matter_smart_plug.bridge import BridgeConfiguration, FabricMatterBridge
from cit_matter_smart_plug.matter_client import MatterServerClient, validate_setup_code
from cit_protocol import FabricResolvedCommand

NOW = datetime(2026, 8, 22, 8, 0, tzinfo=UTC)


def test_commissionable_discovery_returns_only_sanitized_nearby_devices() -> None:
    class DiscoveryClient(MatterServerClient):
        async def command(
            self,
            command: str,
            arguments: object,
            *,
            timeout_seconds: float | None = None,
        ) -> object:
            assert command == "discover_commissionable_nodes"
            assert arguments == {}
            assert timeout_seconds is None
            return [
                {
                    "instance_name": "A private rotating instance",
                    "host_name": "private-host.local.",
                    "addresses": ["fe80::private"],
                    "rotating_id": "private-rotating-id",
                    "long_discriminator": 1234,
                    "vendor_id": 4996,
                    "product_id": 387,
                    "device_name": "Tapo P110M",
                    "commissioning_mode": 1,
                },
                {"device_name": "Incomplete advertisement"},
            ]

    devices = asyncio.run(
        DiscoveryClient("ws://127.0.0.1:5580/ws").discover_commissionable_devices()
    )

    assert len(devices) == 1
    [device] = devices
    assert device.candidate_id.startswith("matter-")
    assert device.display_name == "Tapo P110M"
    assert device.vendor_id == 4996
    assert device.product_id == 387
    assert device.long_discriminator == 1234
    assert "private" not in repr(device)


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
    assert endpoint.electrical_telemetry is False


def test_inventory_accepts_matter_server_numeric_device_type_fields() -> None:
    [endpoint] = discover_plug_endpoints(
        [
            {
                "node_id": 8,
                "available": True,
                "attributes": {
                    "1/29/0": [{"0": 0x010A, "1": 1}],
                    "1/6/0": False,
                },
            }
        ]
    )

    assert endpoint.matter_node_id == 8
    assert endpoint.endpoint_id == 1


def test_tapo_p110m_exposes_standard_matter_13_electrical_measurements() -> None:
    attributes: dict[object, object] = {
        "0/40/1": "TP-Link",
        "0/40/3": "Tapo P110M",
        "0/40/5": "",
        "1/29/0": [{"deviceType": 0x010A, "revision": 2}],
        "1/6/0": False,
        "1/144/4": 230_100,
        "1/144/5": 537,
        "1/144/8": 12_345,
        "1/144/14": 50_000,
        "1/144/17": 9_876,
        "1/145/1": {"energy": 12_345_678},
    }
    [endpoint] = discover_plug_endpoints(
        [{"node_id": 110, "available": True, "attributes": attributes}]
    )

    assert endpoint.display_name == "Tapo P110M"
    assert endpoint.vendor_name == "TP-Link"
    assert endpoint.electrical_telemetry is True
    measurements = extract_electrical_measurements(attributes, endpoint.endpoint_id)
    assert measurements is not None
    assert measurements.active_power_watts == pytest.approx(12.345)
    assert measurements.voltage_volts == pytest.approx(230.1)
    assert measurements.active_current_amperes == pytest.approx(0.537)
    assert measurements.cumulative_energy_kilowatt_hours == pytest.approx(12.345678)
    assert measurements.frequency_hertz == pytest.approx(50.0)
    assert measurements.power_factor_ratio == pytest.approx(0.9876)


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
        product_name="Tapo P110M",
        electrical_telemetry=True,
    )

    assert manifest.pluginId == PLUGIN_ID
    assert [item.name for item in manifest.consumedCapabilities] == ["power.switch.set"]
    assert [item.name for item in manifest.publishedCapabilities] == [
        "power.switch.state",
        ELECTRICAL_STATE_CAPABILITY,
    ]
    assert [item.name for item in node.publishedCapabilities] == [
        "power.switch.state",
        ELECTRICAL_STATE_CAPABILITY,
    ]
    assert node.metadata.model_dump()["cloudDependency"] is False
    assert node.metadata.model_dump()["vendorAccountRequired"] is False
    assert node.metadata.model_dump()["arbitraryClustersExposed"] is False
    assert node.metadata.model_dump()["electricalTelemetry"] is True


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

    async def read_electrical_measurements(
        self, node_id: int, endpoint_id: int
    ) -> ElectricalMeasurements | None:
        assert (node_id, endpoint_id) == (7, 1)
        return None

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


def test_command_result_state_uses_the_active_command_session(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="cit_matter_smart_plug.bridge")

    class RecordingFabricClient:
        def __init__(self) -> None:
            self.events: list[dict[str, object]] = []
            self.lifecycle: list[tuple[str, dict[str, object]]] = []

        async def publish_event(self, **event: object) -> None:
            self.events.append(event)

        async def publish_lifecycle(
            self,
            command: FabricResolvedCommand,
            stage: str,
            **details: object,
        ) -> None:
            self.lifecycle.append((stage, details))

    async def scenario() -> None:
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
                    session_id="adapter-bootstrap-session",
                    site_id="site-a",
                    room_id="room-a",
                ),
                host_id="host-a",
                node_id="matter-7-ep1",
                activation_file=Path("matter-active.flag"),
                matter_node_id=7,
                endpoint_id=1,
                display_name="Test plug",
                vendor_name="Matter",
                product_name="On/Off Plug-in Unit",
            ),
            backend=backend,
        )
        now = datetime.now(UTC)
        command = FabricResolvedCommand.model_validate(
            {
                "commandId": str(uuid4()),
                "requestMessageId": str(uuid4()),
                "schemaVersion": "1.0",
                "sessionId": "active-control-session",
                "targetNodeId": "matter-7-ep1",
                "action": "power.switch.set",
                "parameters": {"on": True},
                "priority": "instructor_override",
                "idempotencyKey": str(uuid4()),
                "requestedAt": now,
                "expiresAt": now + timedelta(seconds=2),
                "safetyProfile": "classroom-smart-plug",
                "correlationId": str(uuid4()),
            }
        )
        fabric_client = RecordingFabricClient()

        await bridge._handle_command(cast(FabricAdapterClient, fabric_client), command)

        assert fabric_client.lifecycle[-1][0] == "SUCCEEDED"
        assert fabric_client.events == [
            {
                "topic": "power.switch.state",
                "source_node_id": "matter-7-ep1",
                "payload": {
                    "on": True,
                    "source": "command",
                    "vendorBrand": "Matter",
                    "cloudDependency": False,
                },
                "ttl_ms": 5_000,
                "session_id": "active-control-session",
                "correlation_id": str(command.correlationId),
                "causation_id": str(command.commandId),
            }
        ]
        diagnostic = "\n".join(record.getMessage() for record in caplog.records)
        assert (
            "Matter command received node_id=matter-7-ep1 "
            f"command_id={command.commandId} command_session_id=active-control-session "
            "action=power.switch.set requested_on=True"
        ) in diagnostic
        assert (
            "Matter command verified node_id=matter-7-ep1 "
            f"command_id={command.commandId} resulting_on=True duplicate_prevented=False"
        ) in diagnostic
        assert (
            "Matter state event queued node_id=matter-7-ep1 "
            "event_session_id=active-control-session on=True source=command"
        ) in diagnostic
        assert "test-adapter-token" not in diagnostic
        await backend.close()

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


def test_bridge_publishes_changed_standard_electrical_telemetry() -> None:
    class ElectricalMatterClient(FakeMatterClient):
        def __init__(self) -> None:
            super().__init__()
            self.measurements = ElectricalMeasurements(
                active_power_watts=12.345,
                voltage_volts=230.1,
                cumulative_energy_kilowatt_hours=1.25,
            )

        async def read_electrical_measurements(
            self, node_id: int, endpoint_id: int
        ) -> ElectricalMeasurements:
            assert (node_id, endpoint_id) == (7, 1)
            return self.measurements

    class RecordingFabricClient:
        def __init__(self) -> None:
            self.events: list[dict[str, object]] = []

        async def publish_event(self, **event: object) -> None:
            self.events.append(event)

    async def scenario() -> None:
        matter_client = ElectricalMatterClient()
        backend = MatterSmartPlug(
            MatterSmartPlugConfiguration(
                server_url="ws://127.0.0.1:5580/ws",
                matter_node_id=7,
                endpoint_id=1,
            ),
            client=matter_client,
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
                activation_file=Path("matter-active.flag"),
                matter_node_id=7,
                endpoint_id=1,
                display_name="Tapo P110M",
                vendor_name="TP-Link",
                product_name="Tapo P110M",
            ),
            backend=backend,
        )
        bridge._electrical_telemetry_available = True
        fabric_client = RecordingFabricClient()
        bridge_client = cast(FabricAdapterClient, fabric_client)

        await bridge._publish_current_electrical(
            bridge_client,
            source="matter-subscription",
            session_id="session-a",
        )
        await bridge._publish_current_electrical(
            bridge_client,
            source="matter-subscription",
            session_id="session-a",
        )

        assert len(fabric_client.events) == 1
        event = fabric_client.events[0]
        assert event["topic"] == ELECTRICAL_STATE_CAPABILITY
        assert event["payload"] == {
            "activePowerWatts": 12.345,
            "voltageVolts": 230.1,
            "cumulativeEnergyKilowattHours": 1.25,
            "source": "matter-subscription",
            "standard": "Matter 1.3",
            "vendorBrand": "TP-Link",
            "productName": "Tapo P110M",
            "cloudDependency": False,
        }
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
