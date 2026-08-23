"""CLI entry point for the independent bounded fleet-sequence controller."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit

from cit_integration_sdk import FabricConnectionConfiguration

from .fleet_backend import (
    Brain2DevicesApiFleetSequenceBackend,
    Brain2DevicesLocalFleetApi,
    FleetSequenceBackend,
    SimulatedFleetSequenceBackend,
)
from .fleet_bridge import BridgeConfiguration, FabricFleetSequenceBridge


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cit-brain2devices-fleet")
    parser.add_argument("--adapter-url", required=True)
    parser.add_argument("--adapter-token", default=os.environ.get("CIT_FABRIC_ADAPTER_TOKEN"))
    parser.add_argument("--fabric-origin")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--room-id", required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--node-id", default="brain2devices-fleet-01")
    parser.add_argument("--activation-file", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("simulation", "brain2devices-api"),
        default="simulation",
    )
    parser.add_argument("--brain2devices-origin", default="http://127.0.0.1:8765")
    parser.add_argument("--allowed-drone-id", action="append", default=[])
    parser.add_argument(
        "--simulation-drone-count",
        type=int,
        choices=range(2, 9),
        default=3,
        metavar="2..8",
    )
    return parser


def _origin(adapter_url: str) -> str:
    parsed = urlsplit(adapter_url)
    if parsed.hostname is None:
        raise ValueError("Adapter URL must include a hostname")
    scheme = "https" if parsed.scheme == "wss" else "http"
    authority = parsed.hostname if parsed.port is None else f"{parsed.hostname}:{parsed.port}"
    return f"{scheme}://{authority}"


async def _run(arguments: argparse.Namespace) -> None:
    if not arguments.adapter_token:
        raise ValueError("A scoped Fabric adapter credential is required")
    backend: FleetSequenceBackend
    if arguments.mode == "brain2devices-api":
        backend = Brain2DevicesApiFleetSequenceBackend(
            api=Brain2DevicesLocalFleetApi(origin=arguments.brain2devices_origin),
            allowed_drone_ids=(
                tuple(arguments.allowed_drone_id) if arguments.allowed_drone_id else None
            ),
        )
    else:
        drone_ids = tuple(
            "primary" if index == 0 else f"drone-{index + 1}"
            for index in range(arguments.simulation_drone_count)
        )
        backend = SimulatedFleetSequenceBackend(drone_ids=drone_ids)
    connection = FabricConnectionConfiguration(
        adapter_url=arguments.adapter_url,
        adapter_token=arguments.adapter_token,
        fabric_origin=arguments.fabric_origin or _origin(arguments.adapter_url),
        session_id=arguments.session_id,
        site_id=arguments.site_id,
        room_id=arguments.room_id,
    )
    bridge = FabricFleetSequenceBridge(
        BridgeConfiguration(
            connection=connection,
            host_id=arguments.host_id,
            node_id=arguments.node_id,
            activation_file=arguments.activation_file.resolve(),
            simulated=arguments.mode == "simulation",
        ),
        backend=backend,
    )
    await bridge.run()


def main() -> None:
    arguments = _parser().parse_args()
    try:
        asyncio.run(_run(arguments))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
