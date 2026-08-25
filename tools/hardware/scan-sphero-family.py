"""One read-only BLE pass for independently filtered Sphero integrations."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class Advertisement:
    name: str
    address: str
    rssi: int | None = None
    service_uuids: tuple[str, ...] = ()
    device: Any = field(default=None, compare=False, repr=False)


class Candidate(Protocol):
    def public_dict(self) -> dict[str, object]: ...


async def _discover(duration: float) -> list[Advertisement]:
    from bleak import BleakScanner

    discovered: dict[str, tuple[Any, Any]] = await BleakScanner.discover(
        timeout=duration,
        return_adv=True,
    )
    return [
        Advertisement(
            name=str(advertisement.local_name or device.name or "").strip(),
            address=str(device.address),
            rssi=int(advertisement.rssi) if advertisement.rssi is not None else None,
            service_uuids=tuple(str(value) for value in advertisement.service_uuids),
            device=device,
        )
        for device, advertisement in discovered.values()
    ]


async def _run(duration: float) -> None:
    if not 0.5 <= duration <= 20:
        raise ValueError("Sphero family scan duration must be between 0.5 and 20 seconds")
    filters: dict[str, Any] = {}
    for name, module_name in (
        ("bolt", "cit_sphero_bolt.discovery"),
        ("ollie", "cit_sphero_ollie.discovery"),
    ):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        filters[name] = module.candidates_from_advertisements
    advertisements = await _discover(duration)
    payload: dict[str, object] = {"available": sorted(filters)}
    for name, convert in filters.items():
        candidates: list[Candidate] = convert(advertisements)
        payload[name] = [candidate.public_dict() for candidate in candidates]
    print(json.dumps(payload, separators=(",", ":")))


def main() -> None:
    parser = argparse.ArgumentParser(prog="scan-sphero-family")
    parser.add_argument("--duration", type=float, default=4.0)
    arguments = parser.parse_args()
    asyncio.run(_run(arguments.duration))


if __name__ == "__main__":
    main()
