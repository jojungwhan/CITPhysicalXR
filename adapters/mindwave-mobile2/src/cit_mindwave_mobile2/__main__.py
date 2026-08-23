"""CLI entry point for the independent MindWave Fabric adapter."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit

from cit_integration_sdk import FabricConnectionConfiguration

from .backend import (
    Brain2DevicesApiMindWaveBackend,
    Brain2DevicesMindWaveConfiguration,
    Brain2DevicesMindWaveProcess,
    MindWaveBackend,
    SimulatedMindWaveBackend,
)
from .bridge import BridgeConfiguration, FabricMindWaveBridge


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cit-mindwave-mobile2")
    parser.add_argument("--adapter-url", required=True)
    parser.add_argument("--adapter-token", default=os.environ.get("CIT_FABRIC_ADAPTER_TOKEN"))
    parser.add_argument("--fabric-origin")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--room-id", required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--node-id", default="mindwave-mobile2-01")
    parser.add_argument("--activation-file", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("simulation", "brain2devices", "brain2devices-api"),
        default="simulation",
    )
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--external-python", type=Path)
    parser.add_argument("--attempts", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--timeout-seconds", type=int, choices=range(5, 61), default=15)
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
    backend: MindWaveBackend
    if arguments.mode == "brain2devices":
        if arguments.repository is None or arguments.external_python is None:
            raise ValueError("Physical mode requires --repository and --external-python")
        backend = Brain2DevicesMindWaveProcess(
            Brain2DevicesMindWaveConfiguration(
                repository=arguments.repository,
                python_executable=arguments.external_python,
                attempts=arguments.attempts,
                timeout_seconds=arguments.timeout_seconds,
            )
        )
    elif arguments.mode == "brain2devices-api":
        backend = Brain2DevicesApiMindWaveBackend(origin=arguments.brain2devices_origin)
    else:
        backend = SimulatedMindWaveBackend()
    connection = FabricConnectionConfiguration(
        adapter_url=arguments.adapter_url,
        adapter_token=arguments.adapter_token,
        fabric_origin=arguments.fabric_origin or _origin(arguments.adapter_url),
        session_id=arguments.session_id,
        site_id=arguments.site_id,
        room_id=arguments.room_id,
    )
    bridge = FabricMindWaveBridge(
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
