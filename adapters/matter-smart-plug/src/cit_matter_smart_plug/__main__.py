"""CLI for one cloud-free Matter smart-plug Fabric adapter."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from cit_integration_sdk import FabricConnectionConfiguration

from .backend import MatterSmartPlug, MatterSmartPlugConfiguration
from .bridge import BridgeConfiguration, FabricMatterBridge


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cit-matter-smart-plug",
        description="Expose one standard Matter OnOff plug through bounded CIT capabilities.",
    )
    parser.add_argument("--adapter-url", default=os.environ.get("CIT_MATTER_ADAPTER_URL"))
    parser.add_argument(
        "--adapter-token",
        default=os.environ.get("CIT_FABRIC_ADAPTER_TOKEN"),
        help="Scoped Fabric credential (prefer CIT_FABRIC_ADAPTER_TOKEN)",
    )
    parser.add_argument("--fabric-origin")
    parser.add_argument("--session-id", default=os.environ.get("CIT_MATTER_SESSION_ID"))
    parser.add_argument("--site-id", default=os.environ.get("CIT_MATTER_SITE_ID"))
    parser.add_argument("--room-id", default=os.environ.get("CIT_MATTER_ROOM_ID"))
    parser.add_argument("--host-id", default=os.environ.get("CIT_MATTER_HOST_ID"))
    parser.add_argument("--node-id", default=os.environ.get("CIT_MATTER_CIT_NODE_ID"))
    parser.add_argument(
        "--activation-file",
        type=Path,
        default=os.environ.get("CIT_MATTER_ACTIVATION_FILE"),
    )
    parser.add_argument(
        "--matter-server-url",
        default=os.environ.get("CIT_MATTER_SERVER_URL", "ws://127.0.0.1:5580/ws"),
    )
    parser.add_argument("--matter-node-id", type=int, default=os.environ.get("CIT_MATTER_NODE_ID"))
    parser.add_argument("--endpoint-id", type=int, default=os.environ.get("CIT_MATTER_ENDPOINT_ID"))
    parser.add_argument("--display-name", default=os.environ.get("CIT_MATTER_DISPLAY_NAME"))
    parser.add_argument("--vendor-name", default=os.environ.get("CIT_MATTER_VENDOR_NAME", "Matter"))
    parser.add_argument(
        "--product-name",
        default=os.environ.get("CIT_MATTER_PRODUCT_NAME", "On/Off Plug-in Unit"),
    )
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
    required = {
        "adapter URL": arguments.adapter_url,
        "session ID": arguments.session_id,
        "site ID": arguments.site_id,
        "room ID": arguments.room_id,
        "host ID": arguments.host_id,
        "CIT node ID": arguments.node_id,
        "activation file": arguments.activation_file,
        "Matter node ID": arguments.matter_node_id,
        "Matter endpoint ID": arguments.endpoint_id,
        "display name": arguments.display_name,
    }
    missing = [label for label, value in required.items() if value is None or value == ""]
    if missing:
        raise ValueError(f"Missing Matter adapter configuration: {', '.join(missing)}")
    backend = MatterSmartPlug(
        MatterSmartPlugConfiguration(
            server_url=arguments.matter_server_url,
            matter_node_id=arguments.matter_node_id,
            endpoint_id=arguments.endpoint_id,
        )
    )
    configuration = BridgeConfiguration(
        connection=FabricConnectionConfiguration(
            adapter_url=arguments.adapter_url,
            adapter_token=arguments.adapter_token,
            fabric_origin=arguments.fabric_origin or _origin(arguments.adapter_url),
            session_id=arguments.session_id,
            site_id=arguments.site_id,
            room_id=arguments.room_id,
        ),
        host_id=arguments.host_id,
        node_id=arguments.node_id,
        activation_file=arguments.activation_file.resolve(),
        matter_node_id=arguments.matter_node_id,
        endpoint_id=arguments.endpoint_id,
        display_name=arguments.display_name,
        vendor_name=arguments.vendor_name,
        product_name=arguments.product_name,
        poll_interval_seconds=arguments.poll_interval,
    )
    print(
        f"Registering {arguments.node_id}; transport=matter-local; safe-state=off",
        flush=True,
    )
    await FabricMatterBridge(configuration, backend=backend).run()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        asyncio.run(_run(_parser().parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
