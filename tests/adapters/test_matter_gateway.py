from __future__ import annotations

from pathlib import Path

import pytest
from cit_matter_smart_plug import gateway
from cit_matter_smart_plug.gateway import (
    GatewayConfiguration,
    _adapter_environment,
    _wait_for_new_available_endpoint,
)
from cit_matter_smart_plug.matter_client import MatterEndpoint


def configuration(tmp_path: Path) -> GatewayConfiguration:
    return GatewayConfiguration(
        adapter_url="ws://127.0.0.1:8766/api/v1/adapters/connect",
        adapter_token="adapter-" + "a" * 40,
        matter_server_url="ws://127.0.0.1:5580/ws",
        site_id="citcoding-academy",
        room_id="plug-room",
        host_id="cit-linux",
        activation_root=tmp_path,
    )


def matter_endpoint(*, available: bool) -> MatterEndpoint:
    return MatterEndpoint(
        matter_node_id=19,
        endpoint_id=1,
        available=available,
        vendor_name="TP-Link",
        product_name="Tapo P110M",
        node_label="Front lamps",
        electrical_telemetry=True,
    )


def test_gateway_passes_only_scoped_adapter_secret_to_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CITXR_FABRIC_BOOTSTRAP_TOKEN", "admin-" + "x" * 40)
    monkeypatch.setenv("CITXR_MATTER_ADAPTER_TOKEN", "parent-adapter-secret")
    endpoint = matter_endpoint(available=True)

    environment = _adapter_environment(
        configuration(tmp_path),
        endpoint,
        tmp_path / "matter-13-ep1.flag",
    )

    assert "CITXR_FABRIC_BOOTSTRAP_TOKEN" not in environment
    assert "CITXR_MATTER_ADAPTER_TOKEN" not in environment
    assert environment["CIT_FABRIC_ADAPTER_TOKEN"] == "adapter-" + "a" * 40
    assert environment["CIT_MATTER_CIT_NODE_ID"] == "matter-13-ep1"
    assert environment["CIT_MATTER_DISPLAY_NAME"] == "Front lamps"


@pytest.mark.parametrize(
    "adapter_url",
    (
        "wss://gateway.example.ts.net/api/v1/adapters/connect",
        "ws://172.30.1.10:8766/api/v1/adapters/connect",
        "ws://127.0.0.1:8766/other",
        "ws://user@127.0.0.1:8766/api/v1/adapters/connect",
    ),
)
def test_gateway_rejects_non_loopback_adapter_endpoints(
    tmp_path: Path,
    adapter_url: str,
) -> None:
    candidate = configuration(tmp_path)
    candidate = GatewayConfiguration(
        adapter_url=adapter_url,
        adapter_token=candidate.adapter_token,
        matter_server_url=candidate.matter_server_url,
        site_id=candidate.site_id,
        room_id=candidate.room_id,
        host_id=candidate.host_id,
        activation_root=candidate.activation_root,
    )

    with pytest.raises(ValueError, match="exact loopback"):
        candidate.validate()


@pytest.mark.parametrize(
    "server_url",
    (
        "wss://matter.example.ts.net/ws",
        "ws://172.30.1.10:5580/ws",
        "ws://localhost:5580/ws",
        "ws://127.0.0.1:5580/other",
        "ws://user@127.0.0.1:5580/ws",
    ),
)
def test_gateway_rejects_non_loopback_matter_endpoints(
    tmp_path: Path,
    server_url: str,
) -> None:
    candidate = configuration(tmp_path)
    candidate = GatewayConfiguration(
        adapter_url=candidate.adapter_url,
        adapter_token=candidate.adapter_token,
        matter_server_url=server_url,
        site_id=candidate.site_id,
        room_id=candidate.room_id,
        host_id=candidate.host_id,
        activation_root=candidate.activation_root,
    )

    with pytest.raises(ValueError, match="exact loopback Matter"):
        candidate.validate()


@pytest.mark.asyncio
async def test_gateway_notices_a_recovered_unmanaged_plug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventories = iter(
        (
            (matter_endpoint(available=False),),
            (matter_endpoint(available=True),),
        )
    )

    async def inventory(_server_url: str) -> tuple[MatterEndpoint, ...]:
        return next(inventories)

    monkeypatch.setattr(gateway, "_inventory", inventory)

    await _wait_for_new_available_endpoint(
        "ws://127.0.0.1:5580/ws",
        frozenset(),
        interval_seconds=0,
    )
