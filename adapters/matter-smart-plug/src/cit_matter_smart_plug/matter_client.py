"""Small loopback client for the Open Home Foundation Matter Server protocol.

Matter protocol details stay inside this adapter package.  The Interaction
Fabric runtime starts only a fixed launcher and never imports Matter SDK code.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlsplit

from websockets.asyncio.client import ClientConnection, connect

MAX_MESSAGE_BYTES = 4 * 1024 * 1024
ON_OFF_CLUSTER_ID = 6
ON_OFF_ATTRIBUTE_ID = 0
DESCRIPTOR_CLUSTER_ID = 29
DEVICE_TYPE_LIST_ATTRIBUTE_ID = 0
ON_OFF_PLUGIN_UNIT_DEVICE_TYPE = 0x010A
ELECTRICAL_POWER_MEASUREMENT_CLUSTER_ID = 0x0090
ELECTRICAL_ENERGY_MEASUREMENT_CLUSTER_ID = 0x0091
VOLTAGE_ATTRIBUTE_ID = 0x0004
ACTIVE_CURRENT_ATTRIBUTE_ID = 0x0005
ACTIVE_POWER_ATTRIBUTE_ID = 0x0008
FREQUENCY_ATTRIBUTE_ID = 0x000E
POWER_FACTOR_ATTRIBUTE_ID = 0x0011
CUMULATIVE_ENERGY_IMPORTED_ATTRIBUTE_ID = 0x0001
_ATTRIBUTE_PATH = re.compile(r"^(?P<endpoint>[0-9]+)/(?P<cluster>[0-9]+)/(?P<attribute>[0-9]+)$")


class MatterServerError(RuntimeError):
    """A local controller operation failed without disclosing credentials."""


@dataclass(frozen=True, slots=True)
class ElectricalMeasurements:
    """Normalized values from the standard Matter 1.3 energy clusters."""

    active_power_watts: float | None = None
    voltage_volts: float | None = None
    active_current_amperes: float | None = None
    cumulative_energy_kilowatt_hours: float | None = None
    frequency_hertz: float | None = None
    power_factor_ratio: float | None = None


@dataclass(frozen=True, slots=True)
class MatterEndpoint:
    matter_node_id: int
    endpoint_id: int
    available: bool
    vendor_name: str
    product_name: str
    node_label: str
    electrical_telemetry: bool

    @property
    def cit_node_id(self) -> str:
        return f"matter-{self.matter_node_id:x}-ep{self.endpoint_id}"

    @property
    def display_name(self) -> str:
        label = self.node_label or self.product_name
        if label:
            return label[:120]
        return f"Matter smart plug {self.matter_node_id:x}/{self.endpoint_id}"


@dataclass(frozen=True, slots=True)
class MatterCommissionableDevice:
    """Sanitized public view of one nearby setup-mode Matter advertisement."""

    candidate_id: str
    display_name: str
    vendor_id: int
    product_id: int
    long_discriminator: int


class MatterServerClient:
    """Concurrent request/event client for one loopback Matter controller."""

    def __init__(self, server_url: str, *, timeout_seconds: float = 30.0) -> None:
        self.server_url = _loopback_websocket_url(server_url)
        if not 1 <= timeout_seconds <= 300:
            raise ValueError("Matter controller timeout must be between 1 and 300 seconds")
        self.timeout_seconds = timeout_seconds
        self.server_info: dict[str, object] = {}
        self.nodes: dict[int, dict[str, object]] = {}
        self._socket: ClientConnection | None = None
        self._receiver: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future[object]] = {}
        self._next_message_id = 0

    async def connect(self) -> None:
        if self._socket is not None:
            return
        socket = await connect(
            self.server_url,
            max_size=MAX_MESSAGE_BYTES,
            open_timeout=10,
            close_timeout=3,
        )
        try:
            raw_info = await asyncio.wait_for(socket.recv(), timeout=10)
            info = _json_object(raw_info)
            schema_version = info.get("schema_version")
            if type(schema_version) is not int or schema_version < 12:
                raise MatterServerError("The local Matter controller protocol is too old for CIT")
            self.server_info = info
            self._socket = socket
            self._receiver = asyncio.create_task(
                self._receive_loop(), name="cit-matter-controller-receive"
            )
            nodes = await self.command("start_listening", {})
            self.nodes = _node_map(nodes)
        except BaseException:
            await socket.close()
            self._socket = None
            raise

    async def close(self) -> None:
        receiver = self._receiver
        self._receiver = None
        socket = self._socket
        self._socket = None
        if receiver is not None:
            receiver.cancel()
        if socket is not None:
            await socket.close()
        if receiver is not None:
            await asyncio.gather(receiver, return_exceptions=True)
        self._fail_pending(MatterServerError("Matter controller connection closed"))

    async def command(
        self,
        command: str,
        arguments: Mapping[str, object],
        *,
        timeout_seconds: float | None = None,
    ) -> object:
        socket = self._socket
        if socket is None:
            raise MatterServerError("Matter controller is not connected")
        self._next_message_id += 1
        message_id = str(self._next_message_id)
        future = asyncio.get_running_loop().create_future()
        self._pending[message_id] = future
        payload = json.dumps(
            {"message_id": message_id, "command": command, "args": dict(arguments)},
            separators=(",", ":"),
        )
        try:
            async with self._send_lock:
                await socket.send(payload)
            async with asyncio.timeout(timeout_seconds or self.timeout_seconds):
                return await future
        except TimeoutError as error:
            raise MatterServerError(f"Matter controller timed out during {command}") from error
        finally:
            self._pending.pop(message_id, None)

    async def refresh_node(self, node_id: int) -> dict[str, object]:
        raw = await self.command("get_node", {"node_id": node_id})
        node = _node_object(raw)
        self.nodes[node_id] = node
        return node

    async def read_on_off(self, node_id: int, endpoint_id: int) -> bool:
        path = f"{endpoint_id}/{ON_OFF_CLUSTER_ID}/{ON_OFF_ATTRIBUTE_ID}"
        raw = await self.command(
            "read_attribute",
            {
                "node_id": node_id,
                "attribute_path": path,
                "fabric_filtered": False,
            },
        )
        if isinstance(raw, Mapping):
            state = raw.get(path)
            if type(state) is bool:
                node = self.nodes.get(node_id)
                attributes = node.get("attributes") if node else None
                if isinstance(attributes, dict):
                    attributes[path] = state
                return state
        node = await self.refresh_node(node_id)
        attributes = node.get("attributes")
        state = attributes.get(path) if isinstance(attributes, Mapping) else None
        if type(state) is not bool:
            raise MatterServerError("Matter plug did not report a boolean OnOff state")
        return state

    async def read_electrical_measurements(
        self, node_id: int, endpoint_id: int
    ) -> ElectricalMeasurements | None:
        node = self.nodes.get(node_id)
        if node is None:
            node = await self.refresh_node(node_id)
        attributes = node.get("attributes")
        if not isinstance(attributes, Mapping):
            return None
        return extract_electrical_measurements(attributes, endpoint_id)

    async def set_on_off(self, node_id: int, endpoint_id: int, on: bool) -> None:
        if type(on) is not bool:
            raise TypeError("Matter OnOff state must be boolean")
        await self.command(
            "device_command",
            {
                "node_id": node_id,
                "endpoint_id": endpoint_id,
                "cluster_id": ON_OFF_CLUSTER_ID,
                "command_name": "on" if on else "off",
                "payload": {},
                "response_type": None,
            },
        )

    async def set_wifi_credentials(self, ssid: str, password: str) -> None:
        if not 1 <= len(ssid.encode("utf-8")) <= 32:
            raise ValueError("Wi-Fi SSID must contain 1 through 32 UTF-8 bytes")
        if len(password) > 63:
            raise ValueError("Wi-Fi password must contain at most 63 characters")
        await self.command(
            "set_wifi_credentials",
            {"ssid": ssid, "credentials": password},
        )

    async def commission(self, setup_code: str) -> dict[str, object]:
        normalized = validate_setup_code(setup_code)
        raw = await self.command(
            "commission_with_code",
            {
                "code": normalized,
                "network_only": False,
            },
            timeout_seconds=240,
        )
        node = _node_object(raw)
        node_id = _node_id(node)
        self.nodes[node_id] = node
        return node

    async def discover_commissionable_devices(self) -> list[MatterCommissionableDevice]:
        raw = await self.command("discover_commissionable_nodes", {})
        if not isinstance(raw, list):
            raise MatterServerError("Matter controller returned invalid discovery results")
        devices: list[MatterCommissionableDevice] = []
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            try:
                vendor_id = _bounded_integer(item.get("vendor_id"), 0, 0xFFFF)
                product_id = _bounded_integer(item.get("product_id"), 0, 0xFFFF)
                discriminator = _bounded_integer(item.get("long_discriminator"), 0, 0x0FFF)
                commissioning_mode = _bounded_integer(item.get("commissioning_mode"), 0, 2)
            except (TypeError, ValueError):
                continue
            if commissioning_mode == 0:
                continue
            instance_name = item.get("instance_name")
            rotating_id = item.get("rotating_id")
            identity_material = "\0".join(
                value for value in (instance_name, rotating_id) if isinstance(value, str) and value
            )
            if not identity_material:
                continue
            identity = hashlib.sha256(
                (f"{identity_material}\0{vendor_id}\0{product_id}\0{discriminator}").encode()
            ).hexdigest()[:12]
            device_name = item.get("device_name")
            display_name = (
                device_name.strip()[:120]
                if isinstance(device_name, str)
                and device_name.strip()
                and all(31 < ord(character) < 127 for character in device_name.strip())
                else f"Matter device VID {vendor_id:04x} PID {product_id:04x}"
            )
            devices.append(
                MatterCommissionableDevice(
                    candidate_id=f"matter-{identity}",
                    display_name=display_name,
                    vendor_id=vendor_id,
                    product_id=product_id,
                    long_discriminator=discriminator,
                )
            )
        return sorted(devices, key=lambda item: item.candidate_id)

    async def _receive_loop(self) -> None:
        socket = self._socket
        if socket is None:
            return
        try:
            async for raw in socket:
                message = _json_object(raw)
                if "event" in message:
                    self._handle_event(message)
                    continue
                message_id = message.get("message_id")
                if not isinstance(message_id, str):
                    continue
                future = self._pending.get(message_id)
                if future is None or future.done():
                    continue
                if "error_code" in message:
                    details = message.get("details")
                    diagnostic = (
                        str(details)[:500]
                        if details
                        else f"Matter controller error {message.get('error_code')}"
                    )
                    future.set_exception(MatterServerError(diagnostic))
                elif "result" in message:
                    future.set_result(message["result"])
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._fail_pending(MatterServerError(f"Matter controller connection failed: {error}"))
        finally:
            if self._socket is socket:
                self._socket = None

    def _handle_event(self, message: Mapping[str, object]) -> None:
        event = message.get("event")
        data = message.get("data")
        if event in {"node_added", "node_updated"}:
            try:
                node = _node_object(data)
                self.nodes[_node_id(node)] = node
            except (TypeError, ValueError):
                pass
            return
        if event == "node_removed":
            try:
                self.nodes.pop(_integer(data, "Matter node ID"), None)
            except (TypeError, ValueError):
                pass
            return
        if event != "attribute_updated" or not isinstance(data, list) or len(data) != 3:
            return
        try:
            node_id = _integer(data[0], "Matter node ID")
        except (TypeError, ValueError):
            return
        path = data[1]
        existing_node = self.nodes.get(node_id)
        attributes = existing_node.get("attributes") if existing_node else None
        if isinstance(path, str) and isinstance(attributes, dict):
            attributes[path] = data[2]

    def _fail_pending(self, error: Exception) -> None:
        for future in tuple(self._pending.values()):
            if not future.done():
                future.set_exception(error)
        self._pending.clear()


def discover_plug_endpoints(nodes: Iterable[Mapping[str, object]]) -> list[MatterEndpoint]:
    endpoints: list[MatterEndpoint] = []
    for raw_node in nodes:
        node = dict(raw_node)
        try:
            node_id = _node_id(node)
        except (TypeError, ValueError):
            continue
        attributes = node.get("attributes")
        if not isinstance(attributes, Mapping):
            continue
        available = node.get("available") is True
        for path, state in attributes.items():
            if not isinstance(path, str) or type(state) is not bool:
                continue
            matched = _ATTRIBUTE_PATH.fullmatch(path)
            if matched is None:
                continue
            endpoint_id = int(matched.group("endpoint"))
            if (
                endpoint_id == 0
                or int(matched.group("cluster")) != ON_OFF_CLUSTER_ID
                or int(matched.group("attribute")) != ON_OFF_ATTRIBUTE_ID
                or not _is_on_off_plug(attributes, endpoint_id)
            ):
                continue
            endpoints.append(
                MatterEndpoint(
                    matter_node_id=node_id,
                    endpoint_id=endpoint_id,
                    available=available,
                    vendor_name=_attribute_text(attributes, "0/40/1"),
                    product_name=_attribute_text(attributes, "0/40/3"),
                    node_label=_attribute_text(attributes, "0/40/5"),
                    electrical_telemetry=(
                        extract_electrical_measurements(attributes, endpoint_id) is not None
                    ),
                )
            )
    return sorted(endpoints, key=lambda item: (item.matter_node_id, item.endpoint_id))


def extract_electrical_measurements(
    attributes: Mapping[object, object], endpoint_id: int
) -> ElectricalMeasurements | None:
    """Read only standardized Matter electrical attributes from one endpoint.

    Matter 1.3 defines power values in milli-units, power factor in hundredths
    of a percent, and cumulative energy in mWh. Unsupported or null attributes
    remain absent instead of being confused with zero.
    """

    power_prefix = f"{endpoint_id}/{ELECTRICAL_POWER_MEASUREMENT_CLUSTER_ID}"
    energy_path = (
        f"{endpoint_id}/{ELECTRICAL_ENERGY_MEASUREMENT_CLUSTER_ID}/"
        f"{CUMULATIVE_ENERGY_IMPORTED_ATTRIBUTE_ID}"
    )
    active_power = _signed_integer_or_none(
        attributes.get(f"{power_prefix}/{ACTIVE_POWER_ATTRIBUTE_ID}")
    )
    voltage = _signed_integer_or_none(attributes.get(f"{power_prefix}/{VOLTAGE_ATTRIBUTE_ID}"))
    active_current = _signed_integer_or_none(
        attributes.get(f"{power_prefix}/{ACTIVE_CURRENT_ATTRIBUTE_ID}")
    )
    frequency = _signed_integer_or_none(attributes.get(f"{power_prefix}/{FREQUENCY_ATTRIBUTE_ID}"))
    power_factor = _signed_integer_or_none(
        attributes.get(f"{power_prefix}/{POWER_FACTOR_ATTRIBUTE_ID}")
    )
    energy = _energy_value_or_none(attributes.get(energy_path))
    if all(
        value is None
        for value in (active_power, voltage, active_current, energy, frequency, power_factor)
    ):
        return None
    return ElectricalMeasurements(
        active_power_watts=_scaled(active_power, 1_000),
        voltage_volts=_scaled(voltage, 1_000),
        active_current_amperes=_scaled(active_current, 1_000),
        cumulative_energy_kilowatt_hours=_scaled(energy, 1_000_000),
        frequency_hertz=_scaled(frequency, 1_000),
        power_factor_ratio=_scaled(power_factor, 10_000),
    )


def validate_setup_code(value: str) -> str:
    candidate = value.strip()
    if candidate.startswith("MT:"):
        if re.fullmatch(r"MT:[A-Z0-9.+\-]{10,100}", candidate) is None:
            raise ValueError("Matter QR setup code is invalid")
        return candidate
    if re.fullmatch(r"[0-9][0-9 -]{9,30}[0-9]", candidate) is None:
        raise ValueError("Matter manual setup code is invalid")
    digits = candidate.replace("-", "").replace(" ", "")
    if len(digits) not in {11, 21}:
        raise ValueError("Matter manual setup code must contain 11 or 21 digits")
    return candidate


def _is_on_off_plug(attributes: Mapping[object, object], endpoint_id: int) -> bool:
    device_types = attributes.get(
        f"{endpoint_id}/{DESCRIPTOR_CLUSTER_ID}/{DEVICE_TYPE_LIST_ATTRIBUTE_ID}"
    )
    if not isinstance(device_types, list):
        return False
    for entry in device_types:
        if not isinstance(entry, Mapping):
            continue
        raw_type = entry.get(
            "deviceType",
            entry.get("device_type", entry.get("0", entry.get(0))),
        )
        try:
            if _integer(raw_type, "Matter device type") == ON_OFF_PLUGIN_UNIT_DEVICE_TYPE:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _attribute_text(attributes: Mapping[object, object], path: str) -> str:
    value = attributes.get(path)
    if not isinstance(value, str) or "\x00\x00" in value:
        return ""
    return value.strip()[:120]


def _loopback_websocket_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "ws"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/ws"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Matter controller URL must be an exact loopback ws:// URL ending /ws")
    return value


def _json_object(raw: str | bytes) -> dict[str, object]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise MatterServerError("Matter controller returned a non-object message")
    return cast(dict[str, object], value)


def _node_object(raw: object) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise MatterServerError("Matter controller returned an invalid node")
    node = {str(key): value for key, value in raw.items()}
    _node_id(node)
    if not isinstance(node.get("attributes"), Mapping):
        raise MatterServerError("Matter controller node has no attribute map")
    node["attributes"] = dict(cast(Mapping[object, object], node["attributes"]))
    return node


def _node_map(raw: object) -> dict[int, dict[str, object]]:
    if not isinstance(raw, list):
        raise MatterServerError("Matter controller returned an invalid node inventory")
    result: dict[int, dict[str, object]] = {}
    for item in raw:
        node = _node_object(item)
        result[_node_id(node)] = node
    return result


def _node_id(node: Mapping[str, object]) -> int:
    return _integer(node.get("node_id"), "Matter node ID")


def _integer(value: object, label: str) -> int:
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    raise ValueError(f"{label} must be a non-negative integer")


def _bounded_integer(value: object, minimum: int, maximum: int) -> int:
    result = _integer(value, "Matter discovery value")
    if not minimum <= result <= maximum:
        raise ValueError("Matter discovery value is outside its allowed range")
    return result


def _signed_integer_or_none(value: object) -> int | None:
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    return None


def _energy_value_or_none(value: object) -> int | None:
    if not isinstance(value, Mapping):
        return None
    return _signed_integer_or_none(value.get("energy"))


def _scaled(value: int | None, divisor: int) -> float | None:
    return None if value is None else value / divisor
