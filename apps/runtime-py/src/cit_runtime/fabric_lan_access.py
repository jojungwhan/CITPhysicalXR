"""Application-layer MAC allowlisting for local Control Tower clients.

The allowlist is deliberately a second gate.  Fabric bearer/session
authentication remains authoritative after a LAN client passes this check.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_MAC_HEX = re.compile(r"^[0-9a-fA-F]{12}$")
_ARP_MAC = re.compile(r"(?i)(?<![0-9a-f])([0-9a-f]{2}(?:[:-][0-9a-f]{2}){5})(?![0-9a-f])")


class LanMacAccessError(RuntimeError):
    """Raised for invalid or unavailable LAN access-management operations."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class LanAccessDevice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    displayName: str = Field(min_length=1, max_length=80)
    macAddress: str
    addedAt: datetime

    @field_validator("displayName")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalize_device_name(value)

    @field_validator("macAddress")
    @classmethod
    def validate_mac_address(cls, value: str) -> str:
        return normalize_mac_address(value)


class LanAccessOperations(BaseModel):
    manage: bool
    enrollUsbAndroid: bool


class LanAccessSnapshot(BaseModel):
    schemaVersion: Literal["1.0"] = "1.0"
    enabled: bool
    lanOrigin: str | None = None
    devices: list[LanAccessDevice]
    operations: LanAccessOperations


class LanAccessActionResult(BaseModel):
    accepted: bool
    message: str
    snapshot: LanAccessSnapshot


class _StoredLanAccess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["1.0"] = "1.0"
    devices: list[LanAccessDevice]


class MacAddressResolver(Protocol):
    def resolve(self, address: str) -> str | None: ...


ArpRunner = Callable[[tuple[str, ...], float], subprocess.CompletedProcess[str]]


def run_arp_process(
    arguments: tuple[str, ...],
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        shell=False,
    )


class WindowsArpMacResolver:
    """Resolve same-link IPv4 neighbors using the Windows ARP table."""

    def __init__(
        self,
        *,
        arp_path: str = "arp.exe",
        run_process: ArpRunner = run_arp_process,
        positive_ttl: float = 30.0,
        negative_ttl: float = 2.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if positive_ttl <= 0 or negative_ttl <= 0:
            raise ValueError("ARP cache TTLs must be positive")
        self._arp_path = arp_path
        self._run_process = run_process
        self._positive_ttl = positive_ttl
        self._negative_ttl = negative_ttl
        self._monotonic = monotonic
        self._cache: dict[str, tuple[str | None, float]] = {}
        self._lock = threading.Lock()

    def resolve(self, address: str) -> str | None:
        parsed = _parse_remote_ipv4(address)
        if parsed is None:
            return None
        normalized_address = str(parsed)
        now = self._monotonic()
        with self._lock:
            cached = self._cache.get(normalized_address)
            if cached is not None and cached[1] > now:
                return cached[0]
            resolved = self._resolve_uncached(normalized_address)
            ttl = self._positive_ttl if resolved is not None else self._negative_ttl
            self._cache[normalized_address] = (resolved, now + ttl)
            return resolved

    def _resolve_uncached(self, address: str) -> str | None:
        try:
            result = self._run_process((self._arp_path, "-a", address), 2.0)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None
        if result.returncode != 0:
            return None
        for raw_line in result.stdout.splitlines():
            fields = raw_line.split()
            if not fields or fields[0] != address:
                continue
            match = _ARP_MAC.search(raw_line)
            if match is None:
                continue
            try:
                return normalize_mac_address(match.group(1))
            except ValueError:
                return None
        return None


class LanMacAccessPolicy:
    """Persist and enforce the MAC allowlist for non-loopback HTTP clients."""

    def __init__(
        self,
        *,
        state_path: str | Path,
        enabled: bool,
        resolver: MacAddressResolver | None = None,
        lan_origin: str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._state_path = Path(state_path).resolve()
        self._enabled = enabled
        self._resolver = resolver or WindowsArpMacResolver()
        self._lan_origin = lan_origin
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._devices = self._load()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def lan_origin(self) -> str | None:
        return self._lan_origin

    def allows(self, client_host: str | None) -> bool:
        if client_host is None:
            return False
        parsed = _parse_client_address(client_host)
        if parsed is None:
            return False
        if parsed.is_loopback:
            return True
        if not self._enabled:
            return True
        if not isinstance(parsed, ipaddress.IPv4Address):
            return False
        resolved = self._resolver.resolve(str(parsed))
        if resolved is None:
            return False
        try:
            normalized = normalize_mac_address(resolved)
        except ValueError:
            return False
        with self._lock:
            return normalized in self._devices

    def snapshot(
        self,
        *,
        can_manage: bool,
        can_enroll_usb_android: bool,
    ) -> LanAccessSnapshot:
        with self._lock:
            devices = sorted(
                (device.model_copy(deep=True) for device in self._devices.values()),
                key=lambda device: (device.displayName.casefold(), device.macAddress),
            )
        return LanAccessSnapshot(
            enabled=self._enabled,
            lanOrigin=self._lan_origin,
            devices=devices,
            operations=LanAccessOperations(
                manage=can_manage,
                enrollUsbAndroid=can_manage and can_enroll_usb_android,
            ),
        )

    def add_device(self, display_name: str, mac_address: str) -> LanAccessDevice:
        normalized_name = normalize_device_name(display_name)
        normalized_mac = normalize_mac_address(mac_address)
        with self._lock:
            existing = self._devices.get(normalized_mac)
            device = LanAccessDevice(
                displayName=normalized_name,
                macAddress=normalized_mac,
                addedAt=existing.addedAt if existing is not None else self._clock(),
            )
            self._devices[normalized_mac] = device
            self._save()
            return device.model_copy(deep=True)

    def remove_device(self, mac_address: str) -> bool:
        normalized_mac = normalize_mac_address(mac_address)
        with self._lock:
            removed = self._devices.pop(normalized_mac, None)
            if removed is None:
                return False
            self._save()
            return True

    def contains_device(self, mac_address: str) -> bool:
        normalized_mac = normalize_mac_address(mac_address)
        with self._lock:
            return normalized_mac in self._devices

    def _load(self) -> dict[str, LanAccessDevice]:
        if not self._state_path.exists():
            return {}
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            stored = _StoredLanAccess.model_validate(raw)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise LanMacAccessError(
                "LAN_ACCESS_STATE_INVALID",
                "The Control Tower LAN allowlist is invalid and was not loaded.",
            ) from error
        devices: dict[str, LanAccessDevice] = {}
        for device in stored.devices:
            if device.macAddress in devices:
                raise LanMacAccessError(
                    "LAN_ACCESS_STATE_INVALID",
                    "The Control Tower LAN allowlist contains duplicate devices.",
                )
            devices[device.macAddress] = device
        return devices

    def _save(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = _StoredLanAccess(devices=list(self._devices.values())).model_dump_json(indent=2)
        temporary_path = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        try:
            temporary_path.write_text(payload + "\n", encoding="utf-8")
            temporary_path.replace(self._state_path)
        except OSError as error:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise LanMacAccessError(
                "LAN_ACCESS_SAVE_FAILED",
                "The Control Tower LAN allowlist could not be saved.",
            ) from error


class LanMacAccessMiddleware:
    """Reject non-allowlisted HTTP and WebSocket peers before route handling."""

    def __init__(self, app: ASGIApp, *, policy: LanMacAccessPolicy) -> None:
        self._app = app
        self._policy = policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self._app(scope, receive, send)
            return
        raw_client = scope.get("client")
        client_host = raw_client[0] if raw_client is not None else None
        if is_loopback_client(client_host):
            allowed = True
        else:
            allowed = await asyncio.to_thread(self._policy.allows, client_host)
        if allowed:
            await self._app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008, "reason": "LAN access denied"})
            return
        response = JSONResponse(
            status_code=403,
            content={
                "code": "LAN_ACCESS_DENIED",
                "message": "This device is not allowed to access Control Tower.",
            },
            headers={"Cache-Control": "no-store"},
        )
        await response(scope, receive, send)


def normalize_device_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Device name must be text")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("Device name contains an unsupported character")
    normalized = " ".join(value.split())
    if not 1 <= len(normalized) <= 80:
        raise ValueError("Device name must contain between 1 and 80 characters")
    return normalized


def normalize_mac_address(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("MAC address must be text")
    compact = value.strip().replace(":", "").replace("-", "").replace(".", "")
    if _MAC_HEX.fullmatch(compact) is None:
        raise ValueError("MAC address must contain exactly 12 hexadecimal digits")
    octets = [int(compact[index : index + 2], 16) for index in range(0, 12, 2)]
    if not any(octets) or all(octet == 0xFF for octet in octets) or octets[0] & 1:
        raise ValueError("MAC address must identify one unicast device")
    return ":".join(f"{octet:02x}" for octet in octets)


def is_loopback_client(client_host: str | None) -> bool:
    parsed = _parse_client_address(client_host) if client_host is not None else None
    return parsed is not None and parsed.is_loopback


def _parse_client_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    normalized = value.partition("%")[0]
    try:
        return ipaddress.ip_address(normalized)
    except ValueError:
        return None


def _parse_remote_ipv4(value: str) -> ipaddress.IPv4Address | None:
    parsed = _parse_client_address(value)
    if not isinstance(parsed, ipaddress.IPv4Address) or parsed.is_loopback:
        return None
    return parsed
