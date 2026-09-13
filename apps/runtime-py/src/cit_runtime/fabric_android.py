"""USB-tethered Android access to the local Control Tower PWA."""

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import subprocess
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode, urlsplit

from pydantic import BaseModel

_RFC1918_NETWORKS = tuple(
    ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


class AndroidControllerState(StrEnum):
    CHECKING = "checking"
    UNAVAILABLE = "unavailable"
    UNAUTHORIZED = "unauthorized"
    AMBIGUOUS = "ambiguous"
    READY = "ready"
    FAILED = "failed"


class AndroidControllerOperations(BaseModel):
    openController: bool


class AndroidControllerSnapshot(BaseModel):
    schemaVersion: Literal["1.0"] = "1.0"
    state: AndroidControllerState
    phoneConnected: bool
    phoneModel: str | None = None
    usbReverseReady: bool
    operations: AndroidControllerOperations
    lastCheckedAt: datetime | None = None
    errorCode: str | None = None
    message: str


class AndroidControllerActionResult(BaseModel):
    accepted: bool
    message: str
    snapshot: AndroidControllerSnapshot


class AndroidControllerError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class AndroidWifiIdentity:
    display_name: str
    mac_address: str


ProcessRunner = Callable[
    [tuple[str, ...], float],
    subprocess.CompletedProcess[str],
]


def run_android_process(
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
    )


class AndroidControllerService:
    """Keep one authorized USB phone bridged to the loopback-only web app."""

    def __init__(
        self,
        *,
        port: int,
        adb_path: str = "adb",
        preferred_serial: str | None = None,
        run_process: ProcessRunner = run_android_process,
        monitor_interval: float | None = 10.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not 1024 <= port <= 65535:
            raise ValueError("Android controller port must be between 1024 and 65535")
        if monitor_interval is not None and monitor_interval <= 0:
            raise ValueError("Android controller monitor interval must be positive or None")
        self._port = port
        self._adb_path = adb_path
        self._preferred_serial = preferred_serial
        self._run_process = run_process
        self._monitor_interval = monitor_interval
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = asyncio.Lock()
        self._monitor_task: asyncio.Task[None] | None = None
        self._serial: str | None = None
        self._controller_opened = False
        self._snapshot = AndroidControllerSnapshot(
            state=AndroidControllerState.CHECKING,
            phoneConnected=False,
            usbReverseReady=False,
            operations=AndroidControllerOperations(openController=False),
            message="Checking for an authorized Android phone connected by USB.",
        )

    async def start(self) -> None:
        await self.refresh()
        if self._monitor_interval is not None and self._monitor_task is None:
            self._monitor_task = asyncio.create_task(self._monitor())

    async def stop(self) -> None:
        if self._monitor_task is None:
            return
        self._monitor_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._monitor_task
        self._monitor_task = None

    async def snapshot(self) -> AndroidControllerSnapshot:
        async with self._lock:
            return self._snapshot.model_copy(deep=True)

    async def refresh(self) -> AndroidControllerSnapshot:
        async with self._lock:
            try:
                snapshot, serial = await asyncio.to_thread(self._refresh_sync)
            except AndroidControllerError as error:
                self._serial = None
                self._snapshot = self._error_snapshot(error)
            else:
                self._serial = serial
                self._snapshot = snapshot
            return self._snapshot.model_copy(deep=True)

    async def open_controller(self, ticket: str) -> AndroidControllerActionResult:
        return await self._open_controller_at_origin(
            ticket,
            f"http://127.0.0.1:{self._port}",
            "Control Tower opened on the USB-connected Android phone.",
        )

    async def open_lan_controller(
        self,
        ticket: str,
        lan_origin: str,
    ) -> AndroidControllerActionResult:
        origin = _validated_lan_origin(lan_origin, self._port)
        return await self._open_controller_at_origin(
            ticket,
            origin,
            "Control Tower opened on the allowed Android phone over local Wi-Fi.",
        )

    async def _open_controller_at_origin(
        self,
        ticket: str,
        origin: str,
        message: str,
    ) -> AndroidControllerActionResult:
        if (
            not isinstance(ticket, str)
            or not 32 <= len(ticket) <= 128
            or ticket != ticket.strip()
            or any(character.isspace() for character in ticket)
        ):
            raise AndroidControllerError(
                "ANDROID_CONTROLLER_TICKET_INVALID",
                "The Android Control Tower access link is invalid.",
            )
        async with self._lock:
            try:
                snapshot, serial = await asyncio.to_thread(self._refresh_sync)
                await asyncio.to_thread(self._open_sync, serial, ticket, origin)
            except AndroidControllerError as error:
                self._serial = None
                self._snapshot = self._error_snapshot(error)
                raise
            self._serial = serial
            self._snapshot = snapshot
            self._controller_opened = True
            return AndroidControllerActionResult(
                accepted=True,
                message=message,
                snapshot=snapshot.model_copy(deep=True),
            )

    async def wifi_identity(self) -> AndroidWifiIdentity:
        """Read the connected phone's current per-network Wi-Fi MAC over USB."""

        async with self._lock:
            try:
                snapshot, serial = await asyncio.to_thread(self._refresh_sync)
                identity = await asyncio.to_thread(
                    self._wifi_identity_sync,
                    serial,
                    snapshot.phoneModel,
                )
            except AndroidControllerError as error:
                self._serial = None
                self._snapshot = self._error_snapshot(error)
                raise
            self._serial = serial
            self._snapshot = snapshot
            return identity

    async def install_unlock_companion(
        self,
        apk_path: str | Path,
        provisioning_uri: str,
    ) -> None:
        """Install and provision once; unlock events use local Wi-Fi afterward."""

        exact_apk = await asyncio.to_thread(_validated_companion_apk, apk_path)
        parsed = urlsplit(provisioning_uri)
        if (
            parsed.scheme != "cit-control-tower"
            or parsed.netloc != "pair"
            or re.fullmatch(r"/[A-Za-z0-9_-]{80,1800}", parsed.path) is None
            or parsed.query
            or parsed.fragment
            or len(provisioning_uri) > 2_048
            or any(character.isspace() for character in provisioning_uri)
        ):
            raise AndroidControllerError(
                "ANDROID_COMPANION_PAIRING_INVALID",
                "The Control Tower Companion pairing request is invalid.",
            )
        async with self._lock:
            try:
                snapshot, serial = await asyncio.to_thread(self._refresh_sync)
                await asyncio.to_thread(
                    self._install_unlock_companion_sync,
                    serial,
                    exact_apk,
                    provisioning_uri,
                )
            except AndroidControllerError as error:
                self._serial = None
                self._snapshot = self._error_snapshot(error)
                raise
            self._serial = serial
            self._snapshot = snapshot

    async def restore_controller_foreground(self) -> bool:
        """Bring back the existing Chrome task without opening another tab or ticket."""

        async with self._lock:
            if not self._controller_opened:
                return False
            try:
                snapshot, serial = await asyncio.to_thread(self._refresh_sync)
                await asyncio.to_thread(self._restore_foreground_sync, serial)
            except AndroidControllerError as error:
                self._serial = None
                self._snapshot = self._error_snapshot(error)
                return False
            self._serial = serial
            self._snapshot = snapshot
            return True

    async def _monitor(self) -> None:
        assert self._monitor_interval is not None
        while True:
            await asyncio.sleep(self._monitor_interval)
            await self.refresh()

    def _refresh_sync(self) -> tuple[AndroidControllerSnapshot, str]:
        devices = self._invoke("devices", "-l", timeout=5.0)
        serial = _select_usb_device(devices.stdout, self._preferred_serial)
        reverse = self._invoke(
            "-s",
            serial,
            "reverse",
            f"tcp:{self._port}",
            f"tcp:{self._port}",
            timeout=5.0,
        )
        if reverse.returncode != 0:
            raise AndroidControllerError(
                "ANDROID_CONTROLLER_REVERSE_FAILED",
                "The USB phone is connected, but its secure local bridge could not be restored.",
            )
        model_result = self._invoke(
            "-s",
            serial,
            "shell",
            "getprop",
            "ro.product.model",
            timeout=5.0,
        )
        model = _safe_model(model_result.stdout) if model_result.returncode == 0 else None
        snapshot = AndroidControllerSnapshot(
            state=AndroidControllerState.READY,
            phoneConnected=True,
            phoneModel=model,
            usbReverseReady=True,
            operations=AndroidControllerOperations(openController=True),
            lastCheckedAt=self._clock(),
            message=(
                "The USB bridge is ready. The phone can stay connected while its Wi-Fi "
                "switches to a camera."
            ),
        )
        return snapshot, serial

    def _open_sync(self, serial: str, ticket: str, origin: str) -> None:
        fragment = urlencode(
            {
                "android-console-ticket": ticket,
            }
        )
        url = f"{origin}/fabric#{fragment}"
        launched = self._invoke(
            "-s",
            serial,
            "shell",
            "am",
            "start",
            "-a",
            "android.intent.action.VIEW",
            "-c",
            "android.intent.category.BROWSABLE",
            "-d",
            url,
            timeout=10.0,
        )
        if launched.returncode != 0:
            raise AndroidControllerError(
                "ANDROID_CONTROLLER_OPEN_FAILED",
                "Android is connected, but its browser could not open Control Tower.",
            )

    def _restore_foreground_sync(self, serial: str) -> None:
        restored = self._invoke(
            "-s",
            serial,
            "shell",
            "am",
            "start",
            "-n",
            "com.android.chrome/com.google.android.apps.chrome.Main",
            timeout=10.0,
        )
        if restored.returncode != 0:
            raise AndroidControllerError(
                "ANDROID_CONTROLLER_RESTORE_FAILED",
                "Android is connected, but Control Tower could not return to the foreground.",
            )

    def _install_unlock_companion_sync(
        self,
        serial: str,
        apk_path: Path,
        provisioning_uri: str,
    ) -> None:
        installed = self._invoke(
            "-s",
            serial,
            "install",
            "-r",
            str(apk_path),
            timeout=120.0,
        )
        if installed.returncode != 0 or "success" not in installed.stdout.casefold():
            raise AndroidControllerError(
                "ANDROID_COMPANION_INSTALL_FAILED",
                "Android rejected the Control Tower Companion installation.",
            )
        cleared = self._invoke(
            "-s",
            serial,
            "shell",
            "pm",
            "clear",
            "com.cit.controltower.companion",
            timeout=15.0,
        )
        if cleared.returncode != 0 or "success" not in cleared.stdout.casefold():
            raise AndroidControllerError(
                "ANDROID_COMPANION_RESET_FAILED",
                "The companion was installed, but its previous pairing could not be cleared.",
            )
        launched = self._invoke(
            "-s",
            serial,
            "shell",
            "am",
            "start",
            "-W",
            "-n",
            "com.cit.controltower.companion/.MainActivity",
            "-a",
            "android.intent.action.VIEW",
            "-d",
            provisioning_uri,
            timeout=15.0,
        )
        if launched.returncode != 0:
            raise AndroidControllerError(
                "ANDROID_COMPANION_PAIRING_FAILED",
                "The companion was installed but could not accept its one-time pairing.",
            )

    def _wifi_identity_sync(
        self,
        serial: str,
        model: str | None,
    ) -> AndroidWifiIdentity:
        result = self._invoke(
            "-s",
            serial,
            "shell",
            "cmd",
            "wifi",
            "status",
            timeout=5.0,
        )
        if result.returncode != 0:
            raise AndroidControllerError(
                "ANDROID_CONTROLLER_WIFI_UNAVAILABLE",
                "The USB phone's Wi-Fi identity could not be read.",
            )
        match = re.search(
            r"(?i)\bMAC:\s*([0-9a-f]{2}(?::[0-9a-f]{2}){5})(?![0-9a-f:])",
            result.stdout,
        )
        if match is None or "wifi is connected" not in result.stdout.casefold():
            raise AndroidControllerError(
                "ANDROID_CONTROLLER_WIFI_DISCONNECTED",
                "Connect the USB phone to the same Wi-Fi network as this computer first.",
            )
        if match.group(1).casefold() == "02:00:00:00:00:00":
            raise AndroidControllerError(
                "ANDROID_CONTROLLER_WIFI_UNAVAILABLE",
                "Android returned a hidden placeholder instead of its current Wi-Fi identity.",
            )
        return AndroidWifiIdentity(
            display_name=f"{model or 'Android phone'} (Wi-Fi)",
            mac_address=match.group(1).casefold(),
        )

    def _invoke(self, *arguments: str, timeout: float) -> subprocess.CompletedProcess[str]:
        command = (self._adb_path, *arguments)
        try:
            result = self._run_process(command, timeout)
        except FileNotFoundError as error:
            raise AndroidControllerError(
                "ANDROID_CONTROLLER_ADB_UNAVAILABLE",
                "Android platform-tools (adb) are not installed on this computer.",
            ) from error
        except subprocess.TimeoutExpired as error:
            raise AndroidControllerError(
                "ANDROID_CONTROLLER_TIMEOUT",
                "The USB-connected Android phone did not respond in time.",
            ) from error
        if arguments == ("devices", "-l") and result.returncode != 0:
            raise AndroidControllerError(
                "ANDROID_CONTROLLER_ADB_UNAVAILABLE",
                "Android platform-tools could not inspect connected phones.",
            )
        return result

    def _error_snapshot(self, error: AndroidControllerError) -> AndroidControllerSnapshot:
        state = {
            "ANDROID_CONTROLLER_NOT_CONNECTED": AndroidControllerState.UNAVAILABLE,
            "ANDROID_CONTROLLER_NOT_AUTHORIZED": AndroidControllerState.UNAUTHORIZED,
            "ANDROID_CONTROLLER_AMBIGUOUS": AndroidControllerState.AMBIGUOUS,
        }.get(error.code, AndroidControllerState.FAILED)
        return AndroidControllerSnapshot(
            state=state,
            phoneConnected=state
            in {AndroidControllerState.UNAUTHORIZED, AndroidControllerState.AMBIGUOUS},
            usbReverseReady=False,
            operations=AndroidControllerOperations(openController=False),
            lastCheckedAt=self._clock(),
            errorCode=error.code,
            message=str(error),
        )


def configured_android_controller(port: int) -> AndroidControllerService:
    preferred_serial = os.environ.get("CITXR_ANDROID_CONTROLLER_SERIAL")
    if preferred_serial is None:
        preferred_serial = os.environ.get("CITXR_SONY_PHONE_SERIAL")
    return AndroidControllerService(
        port=port,
        adb_path=os.environ.get("CITXR_ADB_PATH", "adb"),
        preferred_serial=preferred_serial,
    )


def _select_usb_device(output: str, preferred_serial: str | None) -> str:
    devices: list[tuple[str, str]] = []
    for raw_line in output.splitlines():
        fields = raw_line.split()
        if len(fields) < 2 or fields[0].casefold() == "list":
            continue
        serial, state = fields[0], fields[1]
        if serial.startswith("emulator-") or ":" in serial:
            continue
        devices.append((serial, state))

    if preferred_serial is not None:
        matching = [state for serial, state in devices if serial == preferred_serial]
        if not matching:
            raise AndroidControllerError(
                "ANDROID_CONTROLLER_NOT_CONNECTED",
                "Connect the configured Android phone to this computer by USB.",
            )
        if matching[0] != "device":
            raise AndroidControllerError(
                "ANDROID_CONTROLLER_NOT_AUTHORIZED",
                "Unlock the phone and authorize USB debugging for this computer once.",
            )
        return preferred_serial

    if not devices:
        raise AndroidControllerError(
            "ANDROID_CONTROLLER_NOT_CONNECTED",
            "Connect the dedicated Android phone to this computer by USB.",
        )
    if len(devices) != 1:
        raise AndroidControllerError(
            "ANDROID_CONTROLLER_AMBIGUOUS",
            "More than one USB phone is attached; configure the dedicated Android phone.",
        )
    serial, state = devices[0]
    if state != "device":
        raise AndroidControllerError(
            "ANDROID_CONTROLLER_NOT_AUTHORIZED",
            "Unlock the phone and authorize USB debugging for this computer once.",
        )
    return serial


def _safe_model(output: str) -> str | None:
    model = output.strip()
    if not model or len(model) > 80:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in model):
        return None
    return model


def _validated_companion_apk(apk_path: str | Path) -> Path:
    exact_apk = Path(apk_path).resolve()
    if (
        not exact_apk.is_file()
        or exact_apk.suffix.casefold() != ".apk"
        or exact_apk.stat().st_size <= 0
        or exact_apk.stat().st_size > 64 * 1024 * 1024
    ):
        raise AndroidControllerError(
            "ANDROID_COMPANION_APK_INVALID",
            "The Control Tower Companion APK is missing or invalid.",
        )
    return exact_apk


def _validated_lan_origin(value: str, expected_port: int) -> str:
    parsed = urlsplit(value)
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
        port = parsed.port
    except ValueError as error:
        raise AndroidControllerError(
            "ANDROID_CONTROLLER_LAN_ORIGIN_INVALID",
            "The configured Control Tower local-network address is invalid.",
        ) from error
    if (
        parsed.scheme != "http"
        or not isinstance(address, ipaddress.IPv4Address)
        or not any(address in network for network in _RFC1918_NETWORKS)
        or port != expected_port
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise AndroidControllerError(
            "ANDROID_CONTROLLER_LAN_ORIGIN_INVALID",
            "The configured Control Tower local-network address is invalid.",
        )
    return f"http://{address}:{port}"
