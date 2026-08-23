"""Read-only BLE discovery for exact Dash and Dot selection.

Discovery never connects to a robot and never writes a GATT characteristic.
Bluetooth addresses stay inside the local launcher boundary; the browser sees
only a stable, one-way candidate identifier.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from .models import WonderAdvertisement, WonderRobotCandidate, WonderRobotModel

ROBOT_SERVICE_UUID = "af237777-879d-6186-1f49-deca0e85d9c1"
_NAME_PATTERN = re.compile(r"^(dash|dashet|dot)(?:[\s_-].*)?$", re.IGNORECASE)
Discoverer = Callable[[float], Awaitable[Iterable[WonderAdvertisement]]]


def candidate_id(model: WonderRobotModel, address: str) -> str:
    digest = hashlib.sha256(f"{model.value}\0{address.casefold()}".encode()).hexdigest()[:12]
    return f"wonder-{digest}"


def classify_advertisement(advertisement: WonderAdvertisement) -> WonderRobotModel | None:
    match = _NAME_PATTERN.fullmatch(advertisement.name.strip())
    if match is None:
        return None
    # Some Windows backends omit service UUIDs from passive advertisements, so
    # classification deliberately uses the official robot name alone. A fresh
    # exact-ID scan is still required before any connection is attempted.
    return WonderRobotModel.DOT if match.group(1).casefold() == "dot" else WonderRobotModel.DASH


def signal_percent(rssi: int | None) -> int | None:
    if rssi is None:
        return None
    return max(0, min(100, round((rssi + 100) * 2)))


def candidates_from_advertisements(
    advertisements: Iterable[WonderAdvertisement],
) -> list[WonderRobotCandidate]:
    found: dict[str, WonderRobotCandidate] = {}
    for advertisement in advertisements:
        model = classify_advertisement(advertisement)
        if model is None:
            continue
        opaque_id = candidate_id(model, advertisement.address)
        candidate = WonderRobotCandidate(
            candidate_id=opaque_id,
            display_name=advertisement.name.strip(),
            model=model,
            signal_percent=signal_percent(advertisement.rssi),
            address=advertisement.address,
            device=advertisement.device,
        )
        previous = found.get(opaque_id)
        if previous is None or (candidate.signal_percent or -1) > (previous.signal_percent or -1):
            found[opaque_id] = candidate
    return sorted(
        found.values(),
        key=lambda item: (item.model.value, item.display_name, item.candidate_id),
    )


async def _bleak_discover(timeout_seconds: float) -> Iterable[WonderAdvertisement]:
    try:
        from bleak import BleakScanner
    except ImportError as error:
        raise RuntimeError(
            "Wonder Workshop Bluetooth support is not installed; run the CIT business installer"
        ) from error
    discovered: dict[str, tuple[Any, Any]] = await BleakScanner.discover(
        timeout=timeout_seconds,
        return_adv=True,
    )
    return [
        WonderAdvertisement(
            name=str(advertisement.local_name or device.name or "").strip(),
            address=str(device.address),
            rssi=int(advertisement.rssi) if advertisement.rssi is not None else None,
            service_uuids=tuple(str(value) for value in advertisement.service_uuids),
            device=device,
        )
        for device, advertisement in discovered.values()
    ]


async def scan_wonder_robots(
    timeout_seconds: float = 4.0,
    *,
    discoverer: Discoverer | None = None,
) -> list[WonderRobotCandidate]:
    if not 0.5 <= timeout_seconds <= 20:
        raise ValueError("Wonder Workshop scan duration must be between 0.5 and 20 seconds")
    advertisements = await (discoverer or _bleak_discover)(timeout_seconds)
    return candidates_from_advertisements(advertisements)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cit-wonder-workshop-discover")
    parser.add_argument("--duration", type=float, default=4.0)
    parser.add_argument("--include-address", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


async def _run(arguments: argparse.Namespace) -> None:
    robots = await scan_wonder_robots(arguments.duration)
    payload = []
    for robot in robots:
        item = robot.public_dict()
        if arguments.include_address:
            item["address"] = robot.address
        payload.append(item)
    output = (
        json.dumps(payload, separators=(",", ":"))
        if arguments.json
        else json.dumps(payload, indent=2)
    )
    print(output)


def main() -> None:
    asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    main()
