"""FR-005 and FR-052: hubs arrive by exact name and nothing else."""

from __future__ import annotations

import pytest
from cit_lego_pybricks import (
    HubBinding,
    PybricksDiscoveryProvider,
    hub_model,
)
from cit_lego_pybricks.fakes import FakeHubTransport
from cit_test_harness import require_device_adapter

BINDINGS = (
    HubBinding(
        device_id="lego-spike-01",
        display_name="Class hub 1",
        hub_name="cit-hub-1",
        model_id="spike-prime",
        ports={"A": "motor", "B": "motor", "C": "distance"},
    ),
    HubBinding(
        device_id="lego-essential-01",
        display_name="Small hub",
        hub_name="cit-hub-2",
        model_id="spike-essential",
        ports={"A": "motor", "B": "motor"},
    ),
)


def fake_factory(binding: HubBinding) -> FakeHubTransport:
    return FakeHubTransport(
        hub_name=binding.hub_name,
        model=hub_model(binding.model_id),
        ports=binding.port_map(),
    )


@pytest.mark.asyncio
async def test_discovery_returns_one_adapter_per_configured_hub() -> None:
    provider = PybricksDiscoveryProvider(BINDINGS, transport_factory=fake_factory)

    adapters = await provider.discover()

    assert [adapter.device_id for adapter in adapters] == [
        "lego-spike-01",
        "lego-essential-01",
    ]
    for adapter in adapters:
        assert require_device_adapter(adapter) is adapter


@pytest.mark.asyncio
async def test_discovery_does_not_connect_or_arm_anything() -> None:
    provider = PybricksDiscoveryProvider(BINDINGS, transport_factory=fake_factory)

    adapters = await provider.discover()

    assert all(adapter.connected is False for adapter in adapters)


@pytest.mark.asyncio
async def test_discovering_twice_returns_the_same_adapters() -> None:
    """A rediscovery must not orphan a live hub link."""

    provider = PybricksDiscoveryProvider(BINDINGS, transport_factory=fake_factory)

    first = await provider.discover()
    second = await provider.discover()

    assert [id(adapter) for adapter in first] == [id(adapter) for adapter in second]


def test_a_binding_whose_ports_do_not_fit_its_hub_is_refused() -> None:
    binding = HubBinding(
        device_id="lego-essential-02",
        display_name="Small hub",
        hub_name="cit-hub-3",
        model_id="spike-essential",
        ports={"F": "motor"},
    )

    with pytest.raises(ValueError, match="has no port"):
        binding.port_map()
