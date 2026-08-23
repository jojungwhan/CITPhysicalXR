"""CLI entry point for the independent Tello Fabric adapter."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit

from cit_integration_sdk import FabricConnectionConfiguration

from .backend import (
    Brain2DevicesApiTelloBackend,
    Brain2DevicesTelloConfiguration,
    Brain2DevicesTelloProcess,
    SimulatedTelloBackend,
    TelloBackend,
)
from .bridge import BridgeConfiguration, FabricTelloBridge
from .media import TelloMediaPublisher


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cit-tello")
    parser.add_argument("--adapter-url", required=True)
    parser.add_argument("--adapter-token", default=os.environ.get("CIT_FABRIC_ADAPTER_TOKEN"))
    parser.add_argument("--fabric-origin")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--room-id", required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--node-id", default="tello-01")
    parser.add_argument("--activation-file", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("simulation", "brain2devices", "brain2devices-api"),
        default="simulation",
    )
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--external-python", type=Path)
    parser.add_argument("--ip-address")
    parser.add_argument("--brain2devices-origin", default="http://127.0.0.1:8765")
    parser.add_argument("--brain2devices-drone-id", default="primary")
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
    backend: TelloBackend
    if arguments.mode == "brain2devices":
        if arguments.repository is None or arguments.external_python is None:
            raise ValueError("Physical mode requires --repository and --external-python")
        backend = Brain2DevicesTelloProcess(
            Brain2DevicesTelloConfiguration(
                repository=arguments.repository,
                python_executable=arguments.external_python,
                ip_address=arguments.ip_address,
            )
        )
    elif arguments.mode == "brain2devices-api":
        backend = Brain2DevicesApiTelloBackend(
            origin=arguments.brain2devices_origin,
            drone_id=arguments.brain2devices_drone_id,
        )
    else:
        backend = SimulatedTelloBackend()
    connection = FabricConnectionConfiguration(
        adapter_url=arguments.adapter_url,
        adapter_token=arguments.adapter_token,
        fabric_origin=arguments.fabric_origin or _origin(arguments.adapter_url),
        session_id=arguments.session_id,
        site_id=arguments.site_id,
        room_id=arguments.room_id,
    )
    media_publisher = (
        TelloMediaPublisher(
            fabric_origin=connection.fabric_origin,
            credential=arguments.adapter_token,
            site_id=arguments.site_id,
            room_id=arguments.room_id,
            node_id=arguments.node_id,
            activation_file=arguments.activation_file.resolve(),
            simulated=arguments.mode == "simulation",
            brain2devices_origin=arguments.brain2devices_origin,
            brain2devices_drone_id=arguments.brain2devices_drone_id,
        )
        if arguments.mode in {"simulation", "brain2devices-api"}
        else None
    )
    bridge = FabricTelloBridge(
        BridgeConfiguration(
            connection=connection,
            host_id=arguments.host_id,
            node_id=arguments.node_id,
            activation_file=arguments.activation_file.resolve(),
            simulated=arguments.mode == "simulation",
            ip_address=arguments.ip_address,
            brain2devices_drone_id=arguments.brain2devices_drone_id,
            media_publisher=media_publisher,
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
