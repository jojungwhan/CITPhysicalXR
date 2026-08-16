"""Turning a class configuration into hub adapters (FR-005, FR-052).

Discovery here is deliberately dull: a hub is bound by the name written in the
class configuration, and nothing else. There is no "nearest hub", no "the one
that answered first", and no address remembered from last week -- FR-019 forbids
routing by anything but an exact device id, and the same reasoning applies to
deciding which physical object that id refers to.

Discovering a hub does not arm it. It does not even connect it: the registry
connects, an instructor arms, and only then can anything move.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from .adapter import HubSafetyLimits, PybricksHubAdapter
from .hubs import PortKind, hub_model, parse_port_map
from .transport import HubTransport


@dataclass(frozen=True, slots=True)
class HubBinding:
    """One named hub a class expects to find."""

    device_id: str
    display_name: str
    hub_name: str
    model_id: str
    ports: Mapping[str, str]
    safety_profile: str = "lego-student"
    limits: HubSafetyLimits = field(default_factory=HubSafetyLimits)

    def port_map(self) -> dict[str, PortKind]:
        return parse_port_map(hub_model(self.model_id), self.ports)


TransportFactory = Callable[[HubBinding], HubTransport]


def default_transport_factory(binding: HubBinding) -> HubTransport:
    """The real radio. Imported here so a machine without it still starts."""

    from .ble import PybricksdevTransport

    return PybricksdevTransport(hub_name=binding.hub_name)


class PybricksDiscoveryProvider:
    """Yields one adapter per configured hub, built once and reused."""

    provider_id = "lego-pybricks"

    def __init__(
        self,
        bindings: Sequence[HubBinding],
        *,
        transport_factory: TransportFactory = default_transport_factory,
    ) -> None:
        self._bindings = tuple(bindings)
        self._transport_factory = transport_factory
        self._adapters: dict[str, PybricksHubAdapter] = {}

    @property
    def bindings(self) -> tuple[HubBinding, ...]:
        return self._bindings

    def adapter(self, device_id: str) -> PybricksHubAdapter:
        return self._adapters[device_id]

    async def discover(self) -> Sequence[PybricksHubAdapter]:
        for binding in self._bindings:
            if binding.device_id in self._adapters:
                continue
            model = hub_model(binding.model_id)
            self._adapters[binding.device_id] = PybricksHubAdapter(
                device_id=binding.device_id,
                display_name=binding.display_name,
                transport=self._transport_factory(binding),
                model=model,
                ports=binding.port_map(),
                limits=binding.limits,
                safety_profile=binding.safety_profile,
            )
        return tuple(self._adapters[binding.device_id] for binding in self._bindings)
