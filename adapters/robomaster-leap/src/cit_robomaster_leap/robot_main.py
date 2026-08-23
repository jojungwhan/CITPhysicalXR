"""CLI for the independently supervised RoboMaster S1 Fabric adapter."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit

from cit_integration_sdk import FabricConnectionConfiguration

from .backend import VendorConfiguration, VendorRobotProcess
from .independent_bridges import FabricRoboMasterBridge, RobotBridgeConfiguration


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cit-robomaster-s1")
    parser.add_argument("--adapter-url", required=True)
    parser.add_argument("--adapter-token", default=os.environ.get("CIT_FABRIC_ADAPTER_TOKEN"))
    parser.add_argument("--fabric-origin")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--room-id", required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--node-id", default="robomaster-s1-01")
    parser.add_argument("--activation-file", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--external-python", type=Path, required=True)
    parser.add_argument("--robot-mode", choices=("dry-run", "sdk", "s1-app"), default="dry-run")
    parser.add_argument("--connection", choices=("ap", "sta", "rndis"), default="sta")
    parser.add_argument("--protocol", choices=("tcp", "udp"), default="tcp")
    parser.add_argument("--robot-ip")
    parser.add_argument("--local-ip")
    parser.add_argument("--serial-number")
    parser.add_argument("--max-speed", type=float, default=0.35)
    parser.add_argument("--max-yaw", type=float, default=35.0)
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
    vendor = VendorConfiguration(
        repository=arguments.repository,
        python_executable=arguments.external_python,
        robot_mode=arguments.robot_mode,
        connection=arguments.connection,
        protocol=arguments.protocol,
        robot_ip=arguments.robot_ip,
        local_ip=arguments.local_ip,
        serial_number=arguments.serial_number,
        max_speed=arguments.max_speed,
        max_yaw_degrees=arguments.max_yaw,
    )
    connection = FabricConnectionConfiguration(
        adapter_url=arguments.adapter_url,
        adapter_token=arguments.adapter_token,
        fabric_origin=arguments.fabric_origin or _origin(arguments.adapter_url),
        session_id=arguments.session_id,
        site_id=arguments.site_id,
        room_id=arguments.room_id,
    )
    await FabricRoboMasterBridge(
        RobotBridgeConfiguration(
            connection=connection,
            host_id=arguments.host_id,
            node_id=arguments.node_id,
            activation_file=arguments.activation_file.resolve(),
            robot_mode=arguments.robot_mode,
        ),
        robot=VendorRobotProcess(vendor),
    ).run()


def main() -> None:
    try:
        asyncio.run(_run(_parser().parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
