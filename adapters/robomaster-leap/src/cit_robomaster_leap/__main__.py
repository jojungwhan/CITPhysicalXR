"""CLI for the out-of-process RoboMaster/Leap Fabric adapter."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit

from .backend import VendorConfiguration, VendorLeapProcess, VendorRobotProcess
from .bridge import BridgeConfiguration, FabricRobotLeapBridge


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cit-robomaster-leap",
        description=(
            "Expose the existing Leap Motion and RoboMaster S1 implementation as "
            "independent CIT Interaction Fabric nodes."
        ),
    )
    parser.add_argument("--adapter-url", required=True)
    parser.add_argument(
        "--adapter-token",
        default=os.environ.get("CIT_FABRIC_ADAPTER_TOKEN"),
        help="Scoped Fabric adapter credential (prefer CIT_FABRIC_ADAPTER_TOKEN)",
    )
    parser.add_argument("--fabric-origin")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--room-id", required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--leap-node-id", default="leap-motion-01")
    parser.add_argument("--robot-node-id", default="robomaster-s1-01")
    parser.add_argument("--activation-file", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--external-python", type=Path, required=True)
    parser.add_argument("--input-mode", choices=("demo", "leap"), default="demo")
    parser.add_argument("--robot-mode", choices=("dry-run", "sdk", "s1-app"), default="dry-run")
    parser.add_argument("--bridge-dll", type=Path)
    parser.add_argument("--leap-stop-file", type=Path)
    parser.add_argument("--hand", choices=("left", "right", "any"), default="right")
    parser.add_argument("--connection", choices=("ap", "sta", "rndis"), default="sta")
    parser.add_argument("--protocol", choices=("tcp", "udp"), default="tcp")
    parser.add_argument("--robot-ip")
    parser.add_argument("--local-ip")
    parser.add_argument("--serial-number")
    parser.add_argument("--max-speed", type=float, default=0.35)
    parser.add_argument("--max-yaw", type=float, default=35.0)
    parser.add_argument("--invert-strafe", action="store_true")
    parser.add_argument("--invert-yaw", action="store_true")
    return parser


def _origin(adapter_url: str) -> str:
    parsed = urlsplit(adapter_url)
    scheme = "https" if parsed.scheme == "wss" else "http"
    if parsed.hostname is None:
        raise ValueError("Adapter URL must include a hostname")
    authority = parsed.hostname if parsed.port is None else f"{parsed.hostname}:{parsed.port}"
    return f"{scheme}://{authority}"


async def _run(arguments: argparse.Namespace) -> None:
    if not arguments.adapter_token:
        raise ValueError(
            "A scoped adapter credential is required via --adapter-token or "
            "CIT_FABRIC_ADAPTER_TOKEN"
        )
    if (arguments.input_mode == "leap") != (arguments.robot_mode != "dry-run"):
        raise ValueError(
            "The standard launcher pairs demo input with dry-run output and physical "
            "Leap input with a physical robot transport"
        )
    stop_file = arguments.leap_stop_file
    if arguments.input_mode == "leap" and stop_file is None:
        stop_file = arguments.activation_file.with_name("leap-stop.request")
    vendor = VendorConfiguration(
        repository=arguments.repository,
        python_executable=arguments.external_python,
        robot_mode=arguments.robot_mode,
        connection=arguments.connection,
        protocol=arguments.protocol,
        robot_ip=arguments.robot_ip,
        local_ip=arguments.local_ip,
        serial_number=arguments.serial_number,
        bridge_dll=arguments.bridge_dll,
        leap_stop_file=stop_file,
        preferred_hand=arguments.hand,
        max_speed=arguments.max_speed,
        max_yaw_degrees=arguments.max_yaw,
        invert_strafe=arguments.invert_strafe,
        invert_yaw=arguments.invert_yaw,
    )
    bridge_configuration = BridgeConfiguration(
        adapter_url=arguments.adapter_url,
        adapter_token=arguments.adapter_token,
        fabric_origin=arguments.fabric_origin or _origin(arguments.adapter_url),
        session_id=arguments.session_id,
        site_id=arguments.site_id,
        room_id=arguments.room_id,
        host_id=arguments.host_id,
        leap_node_id=arguments.leap_node_id,
        robot_node_id=arguments.robot_node_id,
        activation_file=arguments.activation_file.resolve(),
        input_mode=arguments.input_mode,
        robot_mode=arguments.robot_mode,
        preferred_hand=arguments.hand,
    )
    robot = VendorRobotProcess(vendor)
    leap = VendorLeapProcess(vendor) if arguments.input_mode == "leap" else None
    bridge = FabricRobotLeapBridge(bridge_configuration, robot=robot, leap=leap)
    print(
        f"Registering {arguments.leap_node_id} and {arguments.robot_node_id}; "
        f"input={arguments.input_mode}, robot={arguments.robot_mode}",
        flush=True,
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
