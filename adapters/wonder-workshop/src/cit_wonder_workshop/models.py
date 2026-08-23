"""Transport-neutral Dash and Dot model types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class WonderRobotModel(StrEnum):
    DASH = "dash"
    DOT = "dot"


@dataclass(frozen=True, slots=True)
class WonderAdvertisement:
    name: str
    address: str
    rssi: int | None = None
    service_uuids: tuple[str, ...] = ()
    device: Any = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class WonderRobotCandidate:
    candidate_id: str
    display_name: str
    model: WonderRobotModel
    signal_percent: int | None
    address: str = field(repr=False)
    device: Any = field(default=None, compare=False, repr=False)

    def public_dict(self) -> dict[str, object]:
        return {
            "candidateId": self.candidate_id,
            "displayName": self.display_name,
            "model": self.model.value,
            "signalPercent": self.signal_percent,
        }


@dataclass(frozen=True, slots=True)
class WonderSensorSnapshot:
    sequence: int
    values: Mapping[str, object]

    @classmethod
    def from_values(cls, sequence: int, values: Mapping[str, object]) -> WonderSensorSnapshot:
        return cls(sequence=sequence, values=MappingProxyType(dict(values)))
