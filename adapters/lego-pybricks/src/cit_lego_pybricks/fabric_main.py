"""CLI for the out-of-process LEGO Fabric adapter."""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from cit_integration_sdk import FabricConnectionConfiguration

from .adapter import build_adapter
from .ble import PybricksdevTransport
from .fabric_bridge import FabricLegoBridge, FabricLegoConfiguration
from .fakes import FakeHubTransport
from .hubs import PortKind, hub_model


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cit-lego-pybricks")
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
    parser.add_argument("--mode", choices=("simulation", "pybricks-ble"), default="simulation")
    parser.add_argument("--hub-name", required=True)
    parser.add_argument("--hub-model", required=True)
    ports = parser.add_mutually_exclusive_group(required=True)
    ports.add_argument("--ports-json")
    ports.add_argument("--ports-base64")
    return parser


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.hostname is None:
        raise ValueError("Adapter URL must include a hostname")
    scheme = "https" if parsed.scheme == "wss" else "http"
    authority = parsed.hostname if parsed.port is None else f"{parsed.hostname}:{parsed.port}"
    return f"{scheme}://{authority}"


def _ports(raw: str) -> dict[str, PortKind]:
    value: object = json.loads(raw)
    if not isinstance(value, dict) or not value:
        raise ValueError("ports-json must be a non-empty object")
    result: dict[str, PortKind] = {}
    for port, kind in value.items():
        if not isinstance(port, str) or not isinstance(kind, str):
            raise ValueError("Every LEGO port and kind must be a string")
        result[port.upper()] = PortKind(kind)
    return result


def _ports_argument(arguments: argparse.Namespace) -> str:
    if arguments.ports_json is not None:
        return str(arguments.ports_json)
    try:
        decoded = base64.b64decode(str(arguments.ports_base64), validate=True)
        return decoded.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as error:
        raise ValueError("ports-base64 must contain UTF-8 JSON") from error


async def _run(arguments: argparse.Namespace) -> None:
    if not arguments.adapter_token:
        raise ValueError("A scoped Fabric adapter credential is required")
    ports = _ports(_ports_argument(arguments))
    model = hub_model(arguments.hub_model)
    transport = (
        FakeHubTransport(hub_name=arguments.hub_name, model=model, ports=ports)
        if arguments.mode == "simulation"
        else PybricksdevTransport(hub_name=arguments.hub_name)
    )
    adapter = build_adapter(
        device_id=arguments.node_id,
        display_name=arguments.display_name,
        transport=transport,
        model_id=arguments.hub_model,
        ports=ports,
    )
    connection = FabricConnectionConfiguration(
        adapter_url=arguments.adapter_url,
        adapter_token=arguments.adapter_token,
        fabric_origin=arguments.fabric_origin or _origin(arguments.adapter_url),
        session_id=arguments.session_id,
        site_id=arguments.site_id,
        room_id=arguments.room_id,
    )
    await FabricLegoBridge(
        FabricLegoConfiguration(
            connection=connection,
            host_id=arguments.host_id,
            activation_file=arguments.activation_file.resolve(),
            simulated=arguments.mode == "simulation",
        ),
        adapter=adapter,
    ).run()


def main() -> None:
    try:
        asyncio.run(_run(_parser().parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
