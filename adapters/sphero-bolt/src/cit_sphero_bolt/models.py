"""Transport-neutral Sphero BOLT model types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class SpheroAdvertisement:
    name: str
    address: str
    rssi: int | None = None
    service_uuids: tuple[str, ...] = ()
    device: Any = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class SpheroBoltCandidate:
    candidate_id: str
    display_name: str
    signal_percent: int | None
    address: str = field(repr=False)
    device: Any = field(default=None, compare=False, repr=False)

    def public_dict(self) -> dict[str, object]:
        return {
            "candidateId": self.candidate_id,
            "displayName": self.display_name,
            "model": "sphero-bolt",
            "signalPercent": self.signal_percent,
        }


@dataclass(frozen=True, slots=True)
class SpheroSensorSnapshot:
    sequence: int
    values: Mapping[str, object]

    @classmethod
    def from_values(cls, sequence: int, values: Mapping[str, object]) -> SpheroSensorSnapshot:
        return cls(sequence=sequence, values=MappingProxyType(dict(values)))
