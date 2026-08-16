"""Which LEGO hubs this adapter claims, and what each one actually has.

FR-045 names the three hubs version 1 supports and FR-054 puts Robot Inventor on
the same Pybricks path as SPIKE Prime. The two are the same board for Pybricks
purposes, so they differ here only in the name a classroom uses.

Nothing in this module flashes anything. FR-046 requires firmware installation
to be an explicit, instructor-performed, documented, reversible act, so what
lives here is the *requirement* a hub must already meet, and the sentence the
runtime says when it does not. The procedure is `docs/LEGO_SETUP.md`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class PortKind(StrEnum):
    """What is plugged into a port. ``EMPTY`` is a first-class answer."""

    EMPTY = "empty"
    MOTOR = "motor"
    DISTANCE = "distance"
    COLOR = "color"
    FORCE = "force"


@dataclass(frozen=True, slots=True)
class HubModel:
    """One supported hub. ``model_id`` is what a device descriptor carries."""

    model_id: str
    display_name: str
    #: The Pybricks class a downloaded program imports for this hub.
    pybricks_hub_class: str
    ports: tuple[str, ...]
    has_imu: bool
    display_kind: str
    #: The lowest Pybricks firmware this adapter is written against.
    minimum_firmware: str
    #: The lowest Pybricks BLE profile version the transport requires.
    minimum_profile: str
    notes: str

    def has_port(self, port: str) -> bool:
        return port in self.ports


#: Recent SPIKE Prime and Robot Inventor hubs ship a different microcontroller
#: than the original run. Pybricks builds for it separately, and a hub of that
#: revision will refuse older firmware, so the revision has to be read off the
#: hub before anyone installs anything.
STM32H5_NOTE = (
    "Check the hub revision before installing firmware: recent hubs use the "
    "STM32H5 microcontroller and need the Pybricks 4.1 beta build. Installing "
    "the older build on one of those hubs fails rather than bricking it, but "
    "the failure is confusing if nobody checked first."
)

SPIKE_PRIME = HubModel(
    model_id="spike-prime",
    display_name="LEGO SPIKE Prime Hub",
    pybricks_hub_class="PrimeHub",
    ports=("A", "B", "C", "D", "E", "F"),
    has_imu=True,
    display_kind="matrix_5x5",
    minimum_firmware="3.3.0",
    minimum_profile="1.2.0",
    notes=STM32H5_NOTE,
)

SPIKE_ESSENTIAL = HubModel(
    model_id="spike-essential",
    display_name="LEGO SPIKE Essential Hub",
    pybricks_hub_class="EssentialHub",
    ports=("A", "B"),
    has_imu=True,
    display_kind="matrix_3x3",
    minimum_firmware="3.3.0",
    minimum_profile="1.2.0",
    notes="Two ports only. A two-motor drive base uses both, leaving no sensor port.",
)

ROBOT_INVENTOR = HubModel(
    model_id="robot-inventor",
    display_name="LEGO MINDSTORMS Robot Inventor Hub",
    pybricks_hub_class="InventorHub",
    ports=("A", "B", "C", "D", "E", "F"),
    has_imu=True,
    display_kind="matrix_5x5",
    minimum_firmware="3.3.0",
    minimum_profile="1.2.0",
    notes=(
        "The same board as SPIKE Prime for Pybricks purposes (FR-054); it is a "
        "separate entry so a classroom sees the name printed on its own box. " + STM32H5_NOTE
    ),
)

HUB_MODELS: Mapping[str, HubModel] = {
    model.model_id: model for model in (SPIKE_PRIME, SPIKE_ESSENTIAL, ROBOT_INVENTOR)
}


class UnknownHubModel(KeyError):
    pass


def hub_model(model_id: str) -> HubModel:
    try:
        return HUB_MODELS[model_id]
    except KeyError as error:
        supported = ", ".join(sorted(HUB_MODELS))
        raise UnknownHubModel(
            f"Unknown LEGO hub model {model_id!r}. Supported models: {supported}."
        ) from error


#: A frame argument is 24 characters, so the port report is positional: one
#: letter per port of the hub, in port order. ``mmd---`` is motors on A and B, a
#: distance sensor on C, and nothing else.
PORT_CODES: Mapping[PortKind, str] = {
    PortKind.EMPTY: "-",
    PortKind.MOTOR: "m",
    PortKind.DISTANCE: "d",
    PortKind.COLOR: "c",
    PortKind.FORCE: "f",
}
_CODE_TO_KIND: Mapping[str, PortKind] = {code: kind for kind, code in PORT_CODES.items()}


def encode_ports(model: HubModel, ports: Mapping[str, PortKind]) -> str:
    return "".join(PORT_CODES[ports.get(port, PortKind.EMPTY)] for port in model.ports)


def decode_ports(model: HubModel, encoded: str) -> dict[str, PortKind]:
    """Read a hub's own port report. A hub that miscounts is not trusted."""

    if len(encoded) != len(model.ports):
        raise ValueError(
            f"{model.display_name} has {len(model.ports)} ports; the hub reported "
            f"{len(encoded)} ({encoded!r})"
        )
    parsed: dict[str, PortKind] = {}
    for port, code in zip(model.ports, encoded, strict=True):
        kind = _CODE_TO_KIND.get(code)
        if kind is None:
            raise ValueError(f"Hub reported unknown port code {code!r} on port {port}")
        parsed[port] = kind
    return parsed


def parse_port_map(model: HubModel, ports: Mapping[str, str]) -> dict[str, PortKind]:
    """Validate a configured port map against what the hub physically has.

    FR-053 wants port validation. Doing it here means a typo in a class
    configuration is a startup error naming the hub and the port, not a motor
    that silently never turns.
    """

    parsed: dict[str, PortKind] = {port: PortKind.EMPTY for port in model.ports}
    for port, kind in ports.items():
        letter = port.upper()
        if not model.has_port(letter):
            available = ", ".join(model.ports)
            raise ValueError(f"{model.display_name} has no port {port!r}. Ports: {available}.")
        try:
            parsed[letter] = PortKind(kind)
        except ValueError as error:
            supported = ", ".join(sorted(item.value for item in PortKind))
            raise ValueError(
                f"Port {letter} is configured as {kind!r}; expected one of {supported}."
            ) from error
    return parsed
