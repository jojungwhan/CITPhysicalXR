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
from typing import Any, Literal

from .matter_client import MatterServerClient, discover_plug_endpoints, validate_setup_code

STDIN_LIMIT = 4_096
BluetoothStatus = Literal[
    "ready",
    "adapter_missing",
    "radio_off",
    "unsupported",
    "transport_missing",
    "unavailable",
    "unsupported_host",
]


class MatterAdminError(RuntimeError):
    """One secret-free, stable failure from the local Matter administration boundary."""

    def __init__(self, code: str, message: str) -> None:
        if (
            not code.startswith("MATTER_")
            or len(code) > 64
            or not code.replace("_", "").isalnum()
            or code != code.upper()
        ):
            raise ValueError("Matter administration error code is invalid")
        if (
            not 1 <= len(message) <= 500
            or "|" in message
            or any(ord(character) < 32 for character in message)
        ):
            raise ValueError("Matter administration error message is invalid")
        super().__init__(message)
        self.code = code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cit-matter-admin")
    parser.add_argument(
        "operation",
        choices=("inventory", "discover", "configure-wifi", "commission"),
    )
    parser.add_argument("--server-url", default="ws://127.0.0.1:5580/ws")
    return parser


async def _run(arguments: argparse.Namespace) -> dict[str, object]:
    client = MatterServerClient(arguments.server_url, timeout_seconds=30)
    await client.connect()
    try:
        if arguments.operation == "inventory":
            return _inventory(client, await _local_bluetooth_status())
        if arguments.operation == "discover":
            devices = await client.discover_commissionable_devices()
            return {
                "schemaVersion": "1.0",
                "devices": [
                    {
                        "candidateId": device.candidate_id,
                        "displayName": device.display_name,
                        "vendorId": device.vendor_id,
                        "productId": device.product_id,
                        "longDiscriminator": device.long_discriminator,
                    }
                    for device in devices
                ],
            }
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
        try:
            normalized_code = validate_setup_code(setup_code)
        except ValueError as error:
            raise MatterAdminError(
                "MATTER_SETUP_CODE_INVALID",
                "The entered Matter setup code is not a valid manual or QR setup code.",
            ) from error
        bluetooth_status = await _local_bluetooth_status()
        if bluetooth_status != "ready":
            on_network_devices = await client.discover_commissionable_devices()
            if not on_network_devices:
                raise _bluetooth_error(bluetooth_status)
        try:
            node = await client.commission(normalized_code)
        except Exception as error:
            raise _commissioning_error(error) from error
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


def _inventory(
    client: MatterServerClient,
    bluetooth_status: BluetoothStatus,
) -> dict[str, object]:
    endpoints = discover_plug_endpoints(client.nodes.values())
    bluetooth_enabled = client.server_info.get("bluetooth_enabled") is True
    return {
        "schemaVersion": "1.0",
        "controller": {
            "connected": True,
            "bluetoothEnabled": bluetooth_enabled,
            "bluetoothReady": bluetooth_enabled and bluetooth_status == "ready",
            "bluetoothStatus": bluetooth_status if bluetooth_enabled else "disabled",
            "wifiCredentialsSet": client.server_info.get("wifi_credentials_set") is True,
        },
        "plugs": [_endpoint_json(endpoint) for endpoint in endpoints],
    }


async def _local_bluetooth_status() -> BluetoothStatus:
    """Return the usable Windows BLE-radio state without starting a scan."""

    if sys.platform != "win32":
        return "unsupported_host"
    try:
        from winrt.windows.devices.bluetooth import BluetoothAdapter
        from winrt.windows.devices.radios import RadioState
    except ImportError:
        return "transport_missing"
    try:
        adapter = await BluetoothAdapter.get_default_async()
        if adapter is None:
            return "adapter_missing"
        if not adapter.is_central_role_supported:
            return "unsupported"
        radio = await adapter.get_radio_async()
        if radio.state != RadioState.ON:
            return "radio_off"
    except (OSError, RuntimeError):
        return "unavailable"
    return "ready"


def _bluetooth_error(status: BluetoothStatus) -> MatterAdminError:
    if status == "adapter_missing":
        return MatterAdminError(
            "MATTER_BLUETOOTH_ADAPTER_MISSING",
            "No Bluetooth LE adapter is connected to this computer.",
        )
    if status == "radio_off":
        return MatterAdminError(
            "MATTER_BLUETOOTH_RADIO_OFF",
            "A Bluetooth adapter is present, but the Windows Bluetooth radio is off.",
        )
    if status == "unsupported":
        return MatterAdminError(
            "MATTER_BLUETOOTH_UNSUPPORTED",
            "The connected Bluetooth adapter does not support Bluetooth Low Energy commissioning.",
        )
    return MatterAdminError(
        "MATTER_BLUETOOTH_UNAVAILABLE",
        "This computer has no usable Bluetooth Low Energy commissioning transport.",
    )


def _commissioning_error(error: Exception) -> MatterAdminError:
    """Classify controller prose into fixed messages that cannot reflect setup secrets."""

    diagnostic = str(error).casefold()
    if any(
        marker in diagnostic
        for marker in (
            "no bluetooth adapter",
            "bluetooth radio",
            "bluetooth unavailable",
            "ble adapter",
            "ble transport",
        )
    ):
        return MatterAdminError(
            "MATTER_BLUETOOTH_UNAVAILABLE",
            "Bluetooth commissioning could not start on this computer.",
        )
    if any(
        marker in diagnostic
        for marker in ("wifi", "wi-fi", "network credentials", "network commissioning")
    ):
        return MatterAdminError(
            "MATTER_WIFI_JOIN_FAILED",
            "The plug was reached, but it could not join the saved Wi-Fi.",
        )
    if "attestation" in diagnostic or "device certificate" in diagnostic:
        return MatterAdminError(
            "MATTER_ATTESTATION_FAILED",
            "The plug answered, but its Matter device identity could not be verified.",
        )
    if any(marker in diagnostic for marker in ("pase", "passcode", "password-authenticated")):
        return MatterAdminError(
            "MATTER_SETUP_CODE_REJECTED",
            "The plug answered, but it did not accept the printed Matter setup code.",
        )
    if any(
        marker in diagnostic
        for marker in ("manual pairing code", "qr pairing code", "verhoeff", "setup code")
    ):
        return MatterAdminError(
            "MATTER_SETUP_CODE_INVALID",
            "The entered Matter setup code is not valid.",
        )
    if any(
        marker in diagnostic
        for marker in ("controller connection", "controller is not connected", "connection closed")
    ):
        return MatterAdminError(
            "MATTER_CONTROLLER_UNAVAILABLE",
            "The local Matter controller connection was lost during commissioning.",
        )
    if any(
        marker in diagnostic
        for marker in ("commissionable", "not found", "discovery", "timed out", "timeout")
    ):
        return MatterAdminError(
            "MATTER_DEVICE_NOT_FOUND",
            "No Matter plug in setup mode answered before the discovery timeout.",
        )
    return MatterAdminError(
        "MATTER_COMMISSIONING_FAILED",
        "Matter commissioning failed at an unknown controller stage.",
    )


def _endpoint_json(endpoint: Any) -> dict[str, object]:
    return {
        "matterNodeId": str(endpoint.matter_node_id),
        "endpointId": endpoint.endpoint_id,
        "nodeId": endpoint.cit_node_id,
        "displayName": endpoint.display_name,
        "vendorName": endpoint.vendor_name,
        "productName": endpoint.product_name,
        "available": endpoint.available,
        "electricalTelemetry": endpoint.electrical_telemetry,
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
        # Low-level controller errors can contain request context. Emit only a
        # fixed classification so setup codes and Wi-Fi credentials stay secret.
        if arguments.operation == "commission":
            classified = (
                error if isinstance(error, MatterAdminError) else _commissioning_error(error)
            )
            message = f"CIT_MATTER_ERROR|{classified.code}|{classified}"
        elif arguments.operation == "configure-wifi":
            message = (
                "CIT_MATTER_ERROR|MATTER_WIFI_CONFIGURATION_FAILED|"
                "The local Matter controller could not save the Wi-Fi configuration."
            )
        else:
            message = "Matter discovery failed; confirm the loopback controller is running"
        print(message, file=sys.stderr)
        raise SystemExit(1) from None
    sys.stdout.write(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
