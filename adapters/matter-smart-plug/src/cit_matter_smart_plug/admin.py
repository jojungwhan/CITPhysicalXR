"""Local-only Matter controller administration CLI.

Commissioning and Wi-Fi credentials are accepted exclusively as bounded JSON
on stdin.  They are never accepted as command-line arguments or emitted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Mapping
from typing import Any

from .matter_client import MatterServerClient, discover_plug_endpoints

STDIN_LIMIT = 4_096


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cit-matter-admin")
    parser.add_argument(
        "operation",
        choices=("inventory", "configure-wifi", "commission"),
    )
    parser.add_argument("--server-url", default="ws://127.0.0.1:5580/ws")
    return parser


async def _run(arguments: argparse.Namespace) -> dict[str, object]:
    client = MatterServerClient(arguments.server_url, timeout_seconds=30)
    await client.connect()
    try:
        if arguments.operation == "inventory":
            return _inventory(client)
        document = _stdin_object()
        if arguments.operation == "configure-wifi":
            if set(document) != {"ssid", "password"}:
                raise ValueError("Wi-Fi setup requires exactly ssid and password")
            ssid = document.get("ssid")
            password = document.get("password")
            if not isinstance(ssid, str) or not isinstance(password, str):
                raise ValueError("Wi-Fi setup values must be strings")
            await client.set_wifi_credentials(ssid, password)
            return {"schemaVersion": "1.0", "configured": True}
        if set(document) != {"setupCode"}:
            raise ValueError("Matter commissioning requires exactly setupCode")
        setup_code = document.get("setupCode")
        if not isinstance(setup_code, str):
            raise ValueError("Matter setup code must be a string")
        node = await client.commission(setup_code)
        endpoints = discover_plug_endpoints((node,))
        if not endpoints:
            raise ValueError(
                "The commissioned Matter device does not expose an On/Off Plug-in Unit endpoint"
            )
        return {
            "schemaVersion": "1.0",
            "commissioned": True,
            "plugs": [_endpoint_json(endpoint) for endpoint in endpoints],
        }
    finally:
        await client.close()


def _inventory(client: MatterServerClient) -> dict[str, object]:
    endpoints = discover_plug_endpoints(client.nodes.values())
    return {
        "schemaVersion": "1.0",
        "controller": {
            "connected": True,
            "bluetoothEnabled": client.server_info.get("bluetooth_enabled") is True,
            "wifiCredentialsSet": client.server_info.get("wifi_credentials_set") is True,
        },
        "plugs": [_endpoint_json(endpoint) for endpoint in endpoints],
    }


def _endpoint_json(endpoint: Any) -> dict[str, object]:
    return {
        "matterNodeId": str(endpoint.matter_node_id),
        "endpointId": endpoint.endpoint_id,
        "nodeId": endpoint.cit_node_id,
        "displayName": endpoint.display_name,
        "vendorName": endpoint.vendor_name,
        "productName": endpoint.product_name,
        "available": endpoint.available,
    }


def _stdin_object() -> dict[str, object]:
    raw = sys.stdin.read(STDIN_LIMIT + 1)
    if len(raw) > STDIN_LIMIT:
        raise ValueError("Matter setup input exceeded its size limit")

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Matter setup input contains a repeated field")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, Mapping):
        raise ValueError("Matter setup input must be a JSON object")
    return {str(key): item for key, item in value.items()}


def main() -> None:
    arguments = _parser().parse_args()
    try:
        result = asyncio.run(_run(arguments))
    except KeyboardInterrupt:
        return
    except Exception as error:
        # The child controller may include request context in low-level errors.
        # Keep technician output useful without reflecting any supplied secret.
        del error
        message = (
            "Matter commission failed; confirm the printed code, pairing mode, "
            "Windows Bluetooth, and configured classroom Wi-Fi"
            if arguments.operation == "commission"
            else "Matter Wi-Fi setup failed; confirm the loopback controller is running"
        )
        print(message, file=sys.stderr)
        raise SystemExit(1) from None
    sys.stdout.write(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
