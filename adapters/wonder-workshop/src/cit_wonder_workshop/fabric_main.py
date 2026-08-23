"""CLI entry point for one independently supervised Dash or Dot node."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit

from cit_integration_sdk import FabricConnectionConfiguration

from .fabric_bridge import FabricWonderBridge, FabricWonderConfiguration
from .models import WonderRobotModel
from .transport import BleakWonderTransport, FakeWonderTransport


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cit-wonder-workshop")
    parser.add_argument("--adapter-url", required=True)
    parser.add_argument("--adapter-token", default=os.environ.get("CIT_FABRIC_ADAPTER_TOKEN"))
    parser.add_argument("--fabric-origin")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--room-id", required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--activation-file", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--model", choices=("dash", "dot"), required=True)
    parser.add_argument("--mode", choices=("simulation", "bleak"), default="simulation")
    return parser


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.hostname is None:
        raise ValueError("Adapter URL must include a hostname")
    scheme = "https" if parsed.scheme == "wss" else "http"
    authority = parsed.hostname if parsed.port is None else f"{parsed.hostname}:{parsed.port}"
    return f"{scheme}://{authority}"


async def _run(arguments: argparse.Namespace) -> None:
    if not arguments.adapter_token:
        raise ValueError("A scoped Fabric adapter credential is required")
    model = WonderRobotModel(arguments.model)
    transport = (
        FakeWonderTransport(model)
        if arguments.mode == "simulation"
        else BleakWonderTransport(arguments.candidate_id, model)
    )
    connection = FabricConnectionConfiguration(
        adapter_url=arguments.adapter_url,
        adapter_token=arguments.adapter_token,
        fabric_origin=arguments.fabric_origin or _origin(arguments.adapter_url),
        session_id=arguments.session_id,
        site_id=arguments.site_id,
        room_id=arguments.room_id,
    )
    await FabricWonderBridge(
        FabricWonderConfiguration(
            connection=connection,
            host_id=arguments.host_id,
            node_id=arguments.node_id,
            display_name=arguments.display_name,
            model=model,
            activation_file=arguments.activation_file.resolve(),
            simulated=arguments.mode == "simulation",
        ),
        transport,
    ).run()


def main() -> None:
    try:
        asyncio.run(_run(_parser().parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
