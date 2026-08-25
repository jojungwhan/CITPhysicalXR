"""Read-only BLE discovery for exact Sphero Ollie selection.

Discovery never connects, pairs, wakes, aims, lights, or rolls a robot. BLE
addresses stay inside the local launcher boundary; the browser sees only a
stable one-way identifier and the exact advertised ``2B-XXXX`` name.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from .models import SpheroAdvertisement, SpheroOllieCandidate

_OLLIE_NAME_PATTERN = re.compile(r"^2B-[0-9A-Z]{4}$", re.IGNORECASE)
Discoverer = Callable[[float], Awaitable[Iterable[SpheroAdvertisement]]]


def candidate_id(address: str) -> str:
    digest = hashlib.sha256(f"sphero-ollie\0{address.casefold()}".encode()).hexdigest()[:12]
    return f"sphero-ollie-{digest}"


def is_ollie_name(name: str) -> bool:
    return _OLLIE_NAME_PATTERN.fullmatch(name.strip()) is not None


def signal_percent(rssi: int | None) -> int | None:
    if rssi is None:
        return None
    return max(0, min(100, round((rssi + 100) * 2)))


def candidates_from_advertisements(
    advertisements: Iterable[SpheroAdvertisement],
) -> list[SpheroOllieCandidate]:
    found: dict[str, SpheroOllieCandidate] = {}
    for advertisement in advertisements:
        display_name = advertisement.name.strip()
        if not is_ollie_name(display_name):
            continue
        opaque_id = candidate_id(advertisement.address)
        candidate = SpheroOllieCandidate(
            candidate_id=opaque_id,
            display_name=display_name.upper(),
            signal_percent=signal_percent(advertisement.rssi),
            address=advertisement.address,
            device=advertisement.device,
        )
        previous = found.get(opaque_id)
        if previous is None or (candidate.signal_percent or -1) > (previous.signal_percent or -1):
            found[opaque_id] = candidate
    return sorted(found.values(), key=lambda item: (item.display_name, item.candidate_id))


async def _bleak_discover(timeout_seconds: float) -> Iterable[SpheroAdvertisement]:
    try:
        from bleak import BleakScanner
    except ImportError as error:
        raise RuntimeError(
            "Sphero Ollie Bluetooth support is not installed; run the CIT business installer"
        ) from error
    discovered: dict[str, tuple[Any, Any]] = await BleakScanner.discover(
        timeout=timeout_seconds,
        return_adv=True,
    )
    return [
        SpheroAdvertisement(
            name=str(advertisement.local_name or device.name or "").strip(),
            address=str(device.address),
            rssi=int(advertisement.rssi) if advertisement.rssi is not None else None,
            service_uuids=tuple(str(value) for value in advertisement.service_uuids),
            device=device,
        )
        for device, advertisement in discovered.values()
    ]


async def scan_sphero_ollies(
    timeout_seconds: float = 4.0,
    *,
    discoverer: Discoverer | None = None,
) -> list[SpheroOllieCandidate]:
    if not 0.5 <= timeout_seconds <= 20:
        raise ValueError("Sphero Ollie scan duration must be between 0.5 and 20 seconds")
    advertisements = await (discoverer or _bleak_discover)(timeout_seconds)
    return candidates_from_advertisements(advertisements)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cit-sphero-ollie-discover")
    parser.add_argument("--duration", type=float, default=4.0)
    parser.add_argument("--include-address", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


async def _run(arguments: argparse.Namespace) -> None:
    robots = await scan_sphero_ollies(arguments.duration)
    payload = []
    for robot in robots:
        item = robot.public_dict()
        if arguments.include_address:
            item["address"] = robot.address
        payload.append(item)
    print(
        json.dumps(
            payload,
            separators=(",", ":") if arguments.json else None,
            indent=None if arguments.json else 2,
        )
    )


def main() -> None:
    asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    main()
