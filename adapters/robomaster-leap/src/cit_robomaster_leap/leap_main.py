"""CLI for the independently supervised Leap Motion Fabric adapter."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit

from cit_integration_sdk import FabricConnectionConfiguration

from .backend import VendorConfiguration, VendorLeapProcess
from .independent_bridges import FabricLeapBridge, LeapBridgeConfiguration


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cit-leap-motion")
    parser.add_argument("--adapter-url", required=True)
    parser.add_argument("--adapter-token", default=os.environ.get("CIT_FABRIC_ADAPTER_TOKEN"))
    parser.add_argument("--fabric-origin")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--room-id", required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--node-id", default="leap-motion-01")
    parser.add_argument("--activation-file", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--external-python", type=Path, required=True)
    parser.add_argument("--input-mode", choices=("demo", "leap"), default="demo")
    parser.add_argument("--bridge-dll", type=Path)
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--hand", choices=("left", "right", "any"), default="right")
    parser.add_argument("--max-speed", type=float, default=0.35)
    parser.add_argument("--max-yaw", type=float, default=35.0)
    parser.add_argument("--invert-strafe", action="store_true")
    parser.add_argument("--invert-yaw", action="store_true")
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
    stop_file = arguments.stop_file or arguments.activation_file.with_name("leap-stop.request")
    vendor = VendorConfiguration(
        repository=arguments.repository,
        python_executable=arguments.external_python,
        robot_mode="dry-run",
        bridge_dll=arguments.bridge_dll,
        leap_stop_file=stop_file,
        preferred_hand=arguments.hand,
        max_speed=arguments.max_speed,
        max_yaw_degrees=arguments.max_yaw,
        invert_strafe=arguments.invert_strafe,
        invert_yaw=arguments.invert_yaw,
    )
    connection = FabricConnectionConfiguration(
        adapter_url=arguments.adapter_url,
        adapter_token=arguments.adapter_token,
        fabric_origin=arguments.fabric_origin or _origin(arguments.adapter_url),
        session_id=arguments.session_id,
        site_id=arguments.site_id,
        room_id=arguments.room_id,
    )
    leap = VendorLeapProcess(vendor) if arguments.input_mode == "leap" else None
    await FabricLeapBridge(
        LeapBridgeConfiguration(
            connection=connection,
            host_id=arguments.host_id,
            node_id=arguments.node_id,
            activation_file=arguments.activation_file.resolve(),
            input_mode=arguments.input_mode,
            preferred_hand=arguments.hand,
        ),
        leap=leap,
    ).run()


def main() -> None:
    try:
        asyncio.run(_run(_parser().parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
