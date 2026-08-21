from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from cit_protocol import FabricResolvedCommand
from cit_runtime.fabric_course import load_course_pack
from cit_runtime.fabric_course import smart_plug_course_pack as runtime_course_pack
from cit_tuya_smart_plug import (
    PLUGIN_ID,
    POWER_SET_CAPABILITY,
    POWER_STATE_CAPABILITY,
    SimulatedSmartPlug,
    SmartPlugCommandHandler,
    SmartPlugError,
    TinyTuyaConfiguration,
    TinyTuyaLanPlug,
    build_manifest,
    build_node,
    smart_plug_course_pack,
)

NOW = datetime(2026, 8, 21, 3, 0, 0, tzinfo=UTC)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class FakeOutlet:
    def __init__(self, initially_on: bool = False) -> None:
        self.on = initially_on
        self.set_calls: list[tuple[bool, int]] = []
        self.closed = False

    def status(self) -> dict[str, object]:
        return {"dps": {"1": self.on}}

    def set_status(self, on: bool, *, switch: int) -> dict[str, object]:
        self.set_calls.append((on, switch))
        self.on = on
        return {"dps": {str(switch): on}}

    def close(self) -> None:
        self.closed = True


def resolved_command(*, on: object, action: str = POWER_SET_CAPABILITY) -> FabricResolvedCommand:
    now = datetime.now(UTC)
    return FabricResolvedCommand.model_validate(
        {
            "commandId": str(uuid4()),
            "requestMessageId": str(uuid4()),
            "schemaVersion": "1.0",
            "sessionId": "session-a",
            "targetNodeId": "plug-a",
            "action": action,
            "parameters": {"on": on},
            "priority": "instructor_override",
            "idempotencyKey": str(uuid4()),
            "requestedAt": now,
            "expiresAt": now + timedelta(seconds=2),
            "safetyProfile": "classroom-smart-plug",
            "correlationId": str(uuid4()),
        }
    )


def test_manifest_and_node_expose_only_boolean_power_and_normalized_state() -> None:
    manifest = build_manifest()
    node = build_node(
        at=NOW,
        host_id="edge-a",
        site_id="local-site",
        room_id="local-room",
        node_id="plug-a",
        simulated=False,
        vendor_brand="gosund",
        model="WP3",
        protocol_version="3.3",
        switch_dps=1,
        device_address="192.168.1.40",
    )

    assert manifest.pluginId == PLUGIN_ID
    assert [item.name for item in manifest.publishedCapabilities] == [POWER_STATE_CAPABILITY]
    assert [item.name for item in manifest.consumedCapabilities] == [POWER_SET_CAPABILITY]
    assert node.safetyClassification.value == "electrical"
    assert node.physical is True
    assert node.simulated is False
    assert node.metadata.model_dump(mode="json") == {
        "vendorBrand": "gosund",
        "model": "WP3",
        "transport": "tuya-lan",
        "protocolVersion": "3.3",
        "switchDps": 1,
        "safeState": "off",
        "arbitraryDatapointsExposed": False,
        "deviceAddress": "192.168.1.40",
    }
    serialized = manifest.model_dump_json() + node.model_dump_json()
    assert "localKey" not in serialized
    assert "deviceId" not in serialized


def test_packaged_course_recipe_adapter_and_runtime_do_not_drift() -> None:
    packaged = load_course_pack(
        REPOSITORY_ROOT / "course-packs" / "smart-plug-control" / "course-pack.yaml"
    )

    assert packaged == runtime_course_pack() == smart_plug_course_pack()


@pytest.mark.asyncio
async def test_simulator_and_handler_are_idempotent_and_boolean_only() -> None:
    backend = SimulatedSmartPlug()
    await backend.start()
    handler = SmartPlugCommandHandler(backend, node_id="plug-a")
    command = resolved_command(on=True)

    first = await handler.execute(command)
    duplicate = await handler.execute(command)

    assert first.state is True
    assert first.duplicate is False
    assert duplicate.duplicate is True
    assert backend.commands == [True]
    with pytest.raises(ValueError, match="boolean"):
        handler.validate(resolved_command(on=1))
    with pytest.raises(ValueError, match="Unsupported"):
        handler.validate(resolved_command(on=True, action="power.switch.set_dps"))


@pytest.mark.asyncio
async def test_tinytuya_backend_uses_exact_lan_configuration_and_verifies_state() -> None:
    outlet = FakeOutlet()
    captured: dict[str, Any] = {}

    def factory(device_id: str, **options: Any) -> FakeOutlet:
        captured["device_id"] = device_id
        captured.update(options)
        return outlet

    backend = TinyTuyaLanPlug(
        TinyTuyaConfiguration(
            device_id="device-a",
            local_key="1234567890abcdef",
            device_address="192.168.1.40",
            protocol_version="3.3",
            switch_dps=1,
            timeout_seconds=2.0,
        ),
        device_factory=factory,
    )

    assert await backend.start() is False
    assert await backend.set_power(True) is True
    assert await backend.set_power(True) is True
    await backend.close()

    assert outlet.set_calls == [(True, 1)]
    assert outlet.closed is True
    assert captured == {
        "device_id": "device-a",
        "address": "192.168.1.40",
        "local_key": "1234567890abcdef",
        "connection_timeout": 2.0,
        "connection_retry_limit": 1,
        "version": 3.3,
        "persist": False,
    }


@pytest.mark.parametrize(
    ("configuration", "message"),
    [
        (
            TinyTuyaConfiguration(
                device_id="device-a",
                local_key="short",
                device_address="192.168.1.40",
            ),
            "16 characters",
        ),
        (
            TinyTuyaConfiguration(
                device_id="device-a",
                local_key="1234567890abcdef",
                device_address="8.8.8.8",
            ),
            "private local network",
        ),
    ],
)
def test_lan_configuration_fails_closed(
    configuration: TinyTuyaConfiguration,
    message: str,
) -> None:
    with pytest.raises(SmartPlugError, match=message):
        configuration.validate()


def test_windows_launcher_uses_adapter_route_and_environment_only_secrets() -> None:
    launcher = (REPOSITORY_ROOT / "tools" / "hardware" / "smart-plug-hardware-test.ps1").read_text(
        encoding="utf-8"
    )

    assert "/api/v1/adapters/connect" in launcher
    assert "/api/v1/fabric/adapters/ws" not in launcher
    assert "CIT_TUYA_DEVICE_ID" in launcher
    assert "CIT_TUYA_LOCAL_KEY" in launcher
    assert "--device-id" not in launcher
    assert "--local-key" not in launcher
