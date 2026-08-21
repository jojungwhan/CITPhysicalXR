"""CLI for the local smart-plug Fabric adapter."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from .backend import (
    SimulatedSmartPlug,
    SmartPlugBackend,
    TinyTuyaConfiguration,
    TinyTuyaLanPlug,
)
from .bridge import BridgeConfiguration, FabricSmartPlugBridge


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cit-tuya-smart-plug",
        description=(
            "Expose one approved Tuya-LAN-compatible smart plug through exact "
            "CIT power.switch capabilities."
        ),
    )
    parser.add_argument("--adapter-url", required=True)
    parser.add_argument(
        "--adapter-token",
        default=os.environ.get("CIT_FABRIC_ADAPTER_TOKEN"),
        help="Scoped Fabric credential (prefer CIT_FABRIC_ADAPTER_TOKEN)",
    )
    parser.add_argument("--fabric-origin")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--room-id", required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--node-id", default="smart-plug-01")
    parser.add_argument("--activation-file", type=Path, required=True)
    parser.add_argument("--mode", choices=("simulation", "lan"), default="simulation")
    parser.add_argument("--vendor", choices=("tuya", "gosund"), default="tuya")
    parser.add_argument(
        "--model",
        default=os.environ.get("CIT_TUYA_MODEL", "Tuya-compatible outlet"),
    )
    parser.add_argument("--device-address")
    parser.add_argument(
        "--protocol-version",
        choices=("3.1", "3.2", "3.3", "3.4", "3.5"),
        default="3.3",
    )
    parser.add_argument("--switch-dps", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--poll-interval", type=float, default=5.0)
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
        raise ValueError("A scoped adapter credential is required via CIT_FABRIC_ADAPTER_TOKEN")
    simulated = arguments.mode == "simulation"
    backend: SmartPlugBackend
    if simulated:
        backend = SimulatedSmartPlug()
    else:
        if not arguments.device_address:
            raise ValueError("LAN mode requires --device-address")
        device_id = os.environ.get("CIT_TUYA_DEVICE_ID")
        local_key = os.environ.get("CIT_TUYA_LOCAL_KEY")
        if device_id is None or local_key is None:
            raise ValueError("LAN mode requires CIT_TUYA_DEVICE_ID and CIT_TUYA_LOCAL_KEY")
        backend = TinyTuyaLanPlug(
            TinyTuyaConfiguration(
                device_id=device_id,
                local_key=local_key,
                device_address=arguments.device_address,
                protocol_version=arguments.protocol_version,
                switch_dps=arguments.switch_dps,
                timeout_seconds=arguments.timeout,
            )
        )
    configuration = BridgeConfiguration(
        adapter_url=arguments.adapter_url,
        adapter_token=arguments.adapter_token,
        fabric_origin=arguments.fabric_origin or _origin(arguments.adapter_url),
        session_id=arguments.session_id,
        site_id=arguments.site_id,
        room_id=arguments.room_id,
        host_id=arguments.host_id,
        node_id=arguments.node_id,
        activation_file=arguments.activation_file.resolve(),
        simulated=simulated,
        vendor_brand=arguments.vendor,
        model=arguments.model,
        protocol_version=arguments.protocol_version,
        switch_dps=arguments.switch_dps,
        device_address=None if simulated else arguments.device_address,
        poll_interval_seconds=arguments.poll_interval,
    )
    print(
        f"Registering {arguments.node_id}; mode={arguments.mode}, "
        f"vendor={arguments.vendor}, safe-state=off",
        flush=True,
    )
    await FabricSmartPlugBridge(configuration, backend=backend).run()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    arguments = _parser().parse_args()
    try:
        asyncio.run(_run(arguments))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
