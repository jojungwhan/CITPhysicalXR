"""CLI entry point for the bounded Brain2Devices demo adapter."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit

from cit_integration_sdk import FabricConnectionConfiguration

from .backend import Brain2DevicesApiDemoBackend, BrainDemoBackend, SimulatedBrainDemoBackend
from .bridge import BridgeConfiguration, FabricBrainDemoBridge


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cit-brain2devices-demo")
    parser.add_argument("--adapter-url", required=True)
    parser.add_argument("--adapter-token", default=os.environ.get("CIT_FABRIC_ADAPTER_TOKEN"))
    parser.add_argument("--fabric-origin")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--room-id", required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--node-id", default="brain2devices-demo-01")
    parser.add_argument("--activation-file", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("simulation", "brain2devices-api"),
        default="simulation",
    )
    parser.add_argument("--brain2devices-origin", default="http://127.0.0.1:8765")
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
    backend: BrainDemoBackend
    if arguments.mode == "brain2devices-api":
        backend = Brain2DevicesApiDemoBackend(origin=arguments.brain2devices_origin)
    else:
        backend = SimulatedBrainDemoBackend()
    connection = FabricConnectionConfiguration(
        adapter_url=arguments.adapter_url,
        adapter_token=arguments.adapter_token,
        fabric_origin=arguments.fabric_origin or _origin(arguments.adapter_url),
        session_id=arguments.session_id,
        site_id=arguments.site_id,
        room_id=arguments.room_id,
    )
    bridge = FabricBrainDemoBridge(
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
