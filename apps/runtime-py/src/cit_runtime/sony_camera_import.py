"""Zero-touch Sony ZV-E10 imports through a dedicated Android companion.

The first-generation ZV-E10 is not supported by Sony's Camera Remote SDK and
does not provide FTP.  Imaging Edge Mobile can, however, wake a previously
paired camera and expose its media.  This module drives that supported app via
ADB, then copies and verifies the phone-side originals without ever issuing a
camera or phone delete operation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

SONY_PACKAGE = "com.sony.playmemories.mobile"
AIR_COMMAND_PACKAGE = "com.samsung.android.service.aircommand"
PHONE_MEDIA_DIRECTORY = "/sdcard/DCIM/Imaging Edge Mobile"
UI_DUMP_PATH = "/sdcard/cit-sony-camera-ui.xml"
MEDIA_SUFFIXES = frozenset({".arw", ".heic", ".hif", ".jpeg", ".jpg", ".mov", ".mp4"})
BATTERY_WARNING_PERCENT = 30
BATTERY_MIN_SYNC_PERCENT = 20
SONY_WIFI_ACTIVITY = ".devicelist.WiFiActivity"
SONY_REMOTE_POWER_ACTIVITY = ".bluetooth.poweronoff.PowerOnOffActivity"
ANDROID_WIFI_REQUEST_ACTIVITY = "com.android.settings/.wifi.NetworkRequestDialogActivity"
BatteryCondition = Literal["unknown", "ok", "warning", "blocked"]


@dataclass(frozen=True)
class BatteryReading:
    """A point-in-time battery reading from Android or a companion-app screen."""

    level_percent: int | None = None
    charging: bool | None = None


class SonyCameraImportError(RuntimeError):
    """A stable, user-actionable import failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SonyCameraSetupRequired(SonyCameraImportError):
    """The one-time, camera-confirmed Bluetooth pairing is absent."""


class SonyCameraBatteryLow(SonyCameraImportError):
    """A safe, retryable sync delay caused by a low non-charging battery."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        device: Literal["phone", "camera"],
        battery: BatteryReading,
    ) -> None:
        super().__init__(code, message)
        self.device = device
        self.battery = battery


@dataclass(frozen=True)
class SonyPhoneProbe:
    phone_connected: bool
    phone_model: str | None = None
    app_installed: bool = False
    bluetooth_enabled: bool = False
    camera_wifi_connected: bool = False
    phone_battery: BatteryReading | None = None
    files_on_phone: int = 0
    bytes_on_phone: int = 0
    message: str | None = None


@dataclass(frozen=True)
class SonyImportProgress:
    stage: str
    message: str
    completed_items: int = 0
    total_items: int | None = None
    bytes_on_phone: int = 0
    phone_battery: BatteryReading | None = None
    camera_battery: BatteryReading | None = None


@dataclass(frozen=True)
class SonyImportResult:
    copied_files: int
    skipped_files: int
    verified_files: int
    copied_bytes: int
    total_bytes: int


class ProcessRunner(Protocol):
    def __call__(
        self,
        command: Sequence[str],
        *,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]: ...


def run_process(
    command: Sequence[str],
    *,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


@dataclass(frozen=True)
class _RemoteFile:
    name: str
    size: int


@dataclass(frozen=True)
class _GridItem:
    key: str
    stem: str
    content_type: str
    checkbox: ET.Element


def parse_adb_devices(output: str, preferred_serial: str | None = None) -> str:
    devices: list[tuple[str, str]] = []
    for line in output.splitlines()[1:]:
        if "\t" not in line:
            continue
        serial, state = line.split("\t", maxsplit=1)
        devices.append((serial.strip(), state.strip()))
    if preferred_serial is not None:
        matching = [state for serial, state in devices if serial == preferred_serial]
        if not matching:
            raise SonyCameraImportError(
                "SONY_PHONE_NOT_CONNECTED",
                f"The configured Android phone {preferred_serial} is not connected by USB.",
            )
        if matching[0] != "device":
            raise SonyCameraImportError(
                "SONY_PHONE_NOT_AUTHORIZED",
                "Unlock the dedicated phone and authorize this computer for USB debugging once.",
            )
        return preferred_serial
    authorized = [serial for serial, state in devices if state == "device"]
    unauthorized = [serial for serial, state in devices if state != "device"]
    if not authorized and unauthorized:
        raise SonyCameraImportError(
            "SONY_PHONE_NOT_AUTHORIZED",
            "Unlock the dedicated phone and authorize this computer for USB debugging once.",
        )
    if not authorized:
        raise SonyCameraImportError(
            "SONY_PHONE_NOT_CONNECTED",
            "Connect the dedicated Android phone to this computer by USB.",
        )
    if len(authorized) != 1:
        raise SonyCameraImportError(
            "SONY_PHONE_AMBIGUOUS",
            "More than one Android device is connected; configure CITXR_SONY_PHONE_SERIAL.",
        )
    return authorized[0]


def parse_remote_listing(output: str) -> list[_RemoteFile]:
    files: list[_RemoteFile] = []
    pattern = re.compile(
        r"^-\S+\s+\d+\s+\d+\s+\d+\s+(\d+)\s+"
        r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+(.+?)\s*$"
    )
    for line in output.splitlines():
        match = pattern.match(line)
        if match is None:
            continue
        name = match.group(2)
        if name.startswith(".pending-") or Path(name).suffix.casefold() not in MEDIA_SUFFIXES:
            continue
        files.append(_RemoteFile(name=name, size=int(match.group(1))))
    return sorted(files, key=lambda item: item.name.casefold())


def parse_sha256_lines(output: str) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for line in output.splitlines():
        match = re.match(r"^([0-9a-fA-F]{64})\s+(.+?)\s*$", line)
        if match is not None:
            hashes[match.group(2)] = match.group(1).casefold()
    return hashes


def battery_condition(reading: BatteryReading | None) -> BatteryCondition:
    """Classify a reading using the import warning and delay thresholds."""

    if reading is None or reading.level_percent is None:
        return "unknown"
    if reading.level_percent < BATTERY_MIN_SYNC_PERCENT and reading.charging is not True:
        return "blocked"
    if reading.level_percent < BATTERY_WARNING_PERCENT:
        return "warning"
    return "ok"


def parse_android_battery(output: str) -> BatteryReading:
    """Parse the stable fields exposed by ``adb shell dumpsys battery``."""

    fields: dict[str, str] = {}
    for raw_line in output.splitlines():
        key, separator, value = raw_line.partition(":")
        if separator:
            fields[key.strip().casefold()] = value.strip().casefold()

    level_percent: int | None = None
    try:
        level = int(fields["level"])
        scale = int(fields.get("scale", "100"))
        if scale > 0 and 0 <= level <= scale:
            level_percent = round(level * 100 / scale)
    except (KeyError, ValueError):
        pass

    status = fields.get("status")
    if status in {"2", "5"}:  # Android BATTERY_STATUS_CHARGING / FULL
        charging: bool | None = True
    elif status in {"3", "4"}:  # DISCHARGING / NOT_CHARGING
        charging = False
    else:
        power_fields = [
            fields[key]
            for key in ("ac powered", "usb powered", "wireless powered")
            if key in fields
        ]
        charging = any(value == "true" for value in power_fields) if power_fields else None
    return BatteryReading(level_percent=level_percent, charging=charging)


def parse_camera_battery_ui(root: ET.Element, *, package: str) -> BatteryReading:
    """Read a best-effort camera battery value from its companion app's visible UI."""

    levels: list[int] = []
    charging_seen = False
    not_charging_seen = False
    for node in root.iter("node"):
        if node.attrib.get("package") != package:
            continue
        resource_id = node.attrib.get("resource-id", "").casefold()
        text = node.attrib.get("text", "")
        description = node.attrib.get("content-desc", "")
        searchable = " ".join((resource_id, text.casefold(), description.casefold()))
        if not any(marker in searchable for marker in ("battery", "batt", "배터리")):
            continue

        values = (text, description)
        found_level = False
        for value in values:
            for match in re.finditer(r"(?<!\d)(100|[1-9]?\d)\s*%", value):
                levels.append(int(match.group(1)))
                found_level = True
        if not found_level and any(marker in resource_id for marker in ("battery", "batt")):
            for value in values:
                if re.fullmatch(r"\s*(100|[1-9]?\d)\s*", value):
                    levels.append(int(value.strip()))

        if any(
            marker in searchable
            for marker in ("not charging", "not_charging", "충전 안 함", "충전안함")
        ):
            not_charging_seen = True
        elif any(
            marker in searchable
            for marker in ("charging", "is_charging", "charge_active", "충전 중", "충전중")
        ):
            charging_seen = True

    if not levels:
        return BatteryReading(charging=True if charging_seen and not not_charging_seen else None)
    charging = charging_seen and not not_charging_seen
    return BatteryReading(level_percent=min(levels), charging=charging)


def require_battery_for_sync(
    reading: BatteryReading,
    *,
    code: str,
    device: Literal["phone", "camera"],
    display_name: str,
) -> None:
    """Defer before media selection when a known battery is critically low."""

    if battery_condition(reading) != "blocked":
        return
    assert reading.level_percent is not None
    raise SonyCameraBatteryLow(
        code,
        f"{display_name} battery is {reading.level_percent}% and is not charging; "
        f"sync is deferred until it reaches {BATTERY_MIN_SYNC_PERCENT}% or starts charging.",
        device=device,
        battery=reading,
    )


def bounds_center(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\[(\d+),(\d+)]\[(\d+),(\d+)]", value)
    if match is None:
        raise SonyCameraImportError("SONY_PHONE_UI_INVALID", "Android UI bounds are invalid.")
    left, top, right, bottom = (int(part) for part in match.groups())
    return ((left + right) // 2, (top + bottom) // 2)


def parse_display_size(output: str) -> tuple[int, int]:
    """Return Android's effective display size from ``wm size`` output."""

    matches = re.findall(r"(?:Physical|Override) size:\s*(\d+)x(\d+)", output)
    if not matches:
        raise SonyCameraImportError(
            "SONY_PHONE_DISPLAY_UNAVAILABLE",
            "The Android phone display size could not be read safely.",
        )
    width, height = (int(value) for value in matches[-1])
    if width < 480 or height < 800 or width >= height:
        raise SonyCameraImportError(
            "SONY_PHONE_DISPLAY_UNSUPPORTED",
            "The Sony camera workflow requires the dedicated phone in portrait orientation.",
        )
    return width, height


def visible_text(root: ET.Element) -> set[str]:
    return {
        value
        for node in root.iter("node")
        for value in (node.attrib.get("text", ""), node.attrib.get("content-desc", ""))
        if value
    }


def is_android_keyguard(root: ET.Element) -> bool:
    locked_text = {
        "기기 잠김",
        "잠금해제 패턴을 그리세요",
        "Device locked",
        "Draw unlock pattern",
    }
    if visible_text(root) & locked_text:
        return True
    return any(
        marker in node.attrib.get("resource-id", "")
        for node in root.iter("node")
        for marker in (":id/keyguard_", ":id/bouncer_")
    )


class AdbSonyCameraImporter:
    """Drive Imaging Edge Mobile and perform verified, append-only PC copies."""

    def __init__(
        self,
        destination: Path,
        *,
        adb_path: str = "adb",
        preferred_serial: str | None = None,
        process_runner: ProcessRunner = run_process,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        transfer_timeout: float = 7_200,
    ) -> None:
        self.destination = destination.resolve()
        self.adb_path = adb_path
        self.preferred_serial = preferred_serial
        self._run_process = process_runner
        self._clock = clock
        self._sleep = sleeper
        self._transfer_timeout = transfer_timeout
        self._serial: str | None = None

    def probe(self) -> SonyPhoneProbe:
        try:
            serial = self._resolve_serial()
            model = self._adb(serial, "shell", "getprop", "ro.product.model").strip() or None
            installed = self._adb(
                serial, "shell", "pm", "path", SONY_PACKAGE, check=False
            ).startswith("package:")
            bluetooth = (
                self._adb(
                    serial,
                    "shell",
                    "settings",
                    "get",
                    "global",
                    "bluetooth_on",
                    check=False,
                ).strip()
                == "1"
            )
            wifi = self._wifi_ssid(serial)
            phone_battery = self._read_phone_battery(serial)
            remote = self._list_phone_media(serial) if installed else []
            return SonyPhoneProbe(
                phone_connected=True,
                phone_model=model,
                app_installed=installed,
                bluetooth_enabled=bluetooth,
                camera_wifi_connected="ZV-E10" in wifi,
                phone_battery=phone_battery,
                files_on_phone=len(remote),
                bytes_on_phone=sum(item.size for item in remote),
            )
        except SonyCameraImportError as error:
            return SonyPhoneProbe(phone_connected=False, message=str(error))
        except (OSError, subprocess.SubprocessError) as error:
            return SonyPhoneProbe(
                phone_connected=False,
                message=f"ADB is unavailable: {type(error).__name__}",
            )

    def import_all(
        self,
        progress: Callable[[SonyImportProgress], None],
    ) -> SonyImportResult:
        serial = self._resolve_serial()
        self._serial = serial
        if not self._adb(serial, "shell", "pm", "path", SONY_PACKAGE, check=False).startswith(
            "package:"
        ):
            raise SonyCameraImportError(
                "SONY_APP_NOT_INSTALLED",
                "Sony Imaging Edge Mobile is not installed on the dedicated phone.",
            )

        phone_battery = self._read_phone_battery(serial)
        progress(
            SonyImportProgress(
                "connecting",
                "Checking Android phone battery",
                phone_battery=phone_battery,
            )
        )
        require_battery_for_sync(
            phone_battery,
            code="SONY_PHONE_BATTERY_LOW",
            device="phone",
            display_name="Dedicated Android phone",
        )

        old_stay_awake = self._adb(
            serial,
            "shell",
            "settings",
            "get",
            "global",
            "stay_on_while_plugged_in",
            check=False,
        ).strip()
        air_command_enabled = AIR_COMMAND_PACKAGE in self._adb(
            serial,
            "shell",
            "pm",
            "list",
            "packages",
            "-e",
            AIR_COMMAND_PACKAGE,
            check=False,
        )
        try:
            progress(SonyImportProgress("connecting", "Preparing the Android companion"))
            if air_command_enabled:
                self._adb(
                    serial,
                    "shell",
                    "pm",
                    "disable-user",
                    "--user",
                    "0",
                    AIR_COMMAND_PACKAGE,
                    check=False,
                )
            self._adb(serial, "shell", "am", "force-stop", AIR_COMMAND_PACKAGE, check=False)
            self._adb(serial, "shell", "svc", "power", "stayon", "usb", check=False)
            self._adb(serial, "shell", "svc", "bluetooth", "enable", check=False)
            self._adb(serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP", check=False)
            self._adb(serial, "shell", "wm", "dismiss-keyguard", check=False)

            root = self._open_sony_app(serial)
            root = self._ensure_camera_connection(serial, root, progress)
            camera_battery = parse_camera_battery_ui(root, package=SONY_PACKAGE)
            progress(
                SonyImportProgress(
                    "connecting",
                    "Checking Sony ZV-E10 battery",
                    phone_battery=phone_battery,
                    camera_battery=camera_battery,
                )
            )
            require_battery_for_sync(
                camera_battery,
                code="SONY_CAMERA_BATTERY_LOW",
                device="camera",
                display_name="Sony ZV-E10",
            )
            date_list = self._open_camera_import(serial, root)
            self._import_missing_camera_items(serial, date_list, progress)
            progress(SonyImportProgress("copying", "Copying new originals to this PC"))
            return self._copy_and_verify(serial, progress)
        finally:
            if old_stay_awake.isdigit():
                self._adb(
                    serial,
                    "shell",
                    "settings",
                    "put",
                    "global",
                    "stay_on_while_plugged_in",
                    old_stay_awake,
                    check=False,
                )
            else:
                self._adb(serial, "shell", "svc", "power", "stayon", "false", check=False)
            if air_command_enabled:
                self._adb(
                    serial,
                    "shell",
                    "pm",
                    "enable",
                    "--user",
                    "0",
                    AIR_COMMAND_PACKAGE,
                    check=False,
                )

    def _resolve_serial(self) -> str:
        output = self._host_adb("devices", timeout=15)
        return parse_adb_devices(output, self.preferred_serial)

    def _host_adb(self, *args: str, timeout: float = 30, check: bool = True) -> str:
        try:
            result = self._run_process((self.adb_path, *args), timeout=timeout)
        except FileNotFoundError as error:
            raise SonyCameraImportError(
                "ADB_NOT_INSTALLED", "Android platform-tools (adb) are not installed."
            ) from error
        except subprocess.TimeoutExpired as error:
            raise SonyCameraImportError(
                "ADB_TIMEOUT", "Android did not respond in time."
            ) from error
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise SonyCameraImportError(
                "ADB_COMMAND_FAILED",
                detail[:400] or "Android command failed.",
            )
        return result.stdout

    def _adb(
        self,
        serial: str,
        *args: str,
        timeout: float = 30,
        check: bool = True,
    ) -> str:
        return self._host_adb("-s", serial, *args, timeout=timeout, check=check)

    def _shell(self, serial: str, command: str, *, timeout: float = 30) -> str:
        return self._adb(serial, "shell", command, timeout=timeout)

    def _wifi_ssid(self, serial: str) -> str:
        output = self._adb(serial, "shell", "dumpsys", "wifi", timeout=45, check=False)
        match = re.search(r'mWifiInfo SSID: (?:"([^"]+)"|([^,\r\n]+))', output)
        return (match.group(1) or match.group(2)).strip() if match is not None else ""

    def _activity_state(self, serial: str) -> str:
        output = self._adb(
            serial,
            "shell",
            "dumpsys",
            "activity",
            "activities",
            timeout=20,
            check=False,
        )
        return next(
            (line.strip() for line in output.splitlines() if "mResumedActivity:" in line),
            "",
        )

    def _read_phone_battery(self, serial: str) -> BatteryReading:
        return parse_android_battery(self._adb(serial, "shell", "dumpsys", "battery", check=False))

    def _list_phone_media(self, serial: str) -> list[_RemoteFile]:
        listing = self._shell(
            serial,
            f"if [ -d '{PHONE_MEDIA_DIRECTORY}' ]; then ls -lanA '{PHONE_MEDIA_DIRECTORY}'; fi",
            timeout=45,
        )
        return parse_remote_listing(listing)

    def _dump_ui(self, serial: str, *, attempts: int = 4) -> ET.Element:
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                self._adb(
                    serial,
                    "shell",
                    "uiautomator",
                    "dump",
                    UI_DUMP_PATH,
                    timeout=20,
                )
                body = self._shell(serial, f"cat '{UI_DUMP_PATH}'", timeout=10)
                return ET.fromstring(body)
            except (ET.ParseError, SonyCameraImportError) as error:
                last_error = error
                self._sleep(1)
        raise SonyCameraImportError(
            "SONY_PHONE_UI_UNAVAILABLE",
            "The Sony app screen could not be read. Keep the dedicated phone unlocked.",
        ) from last_error

    @staticmethod
    def _parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
        return {child: parent for parent in root.iter() for child in parent}

    @staticmethod
    def _find(
        root: ET.Element,
        *,
        texts: Sequence[str] = (),
        resource_suffix: str | None = None,
    ) -> ET.Element | None:
        for node in root.iter("node"):
            if texts and (
                node.attrib.get("text") in texts or node.attrib.get("content-desc") in texts
            ):
                return node
            if resource_suffix is not None and node.attrib.get("resource-id", "").endswith(
                resource_suffix
            ):
                return node
        return None

    def _tap(self, serial: str, root: ET.Element, node: ET.Element) -> None:
        parents = self._parent_map(root)
        target = node
        while target.attrib.get("clickable") != "true" and target in parents:
            target = parents[target]
        x, y = bounds_center(target.attrib.get("bounds", node.attrib.get("bounds", "")))
        self._adb(
            serial,
            "shell",
            "input",
            "touchscreen",
            "tap",
            str(x),
            str(y),
        )

    def _click_if_present(
        self,
        serial: str,
        root: ET.Element,
        *,
        texts: Sequence[str] = (),
        resource_suffix: str | None = None,
    ) -> bool:
        node = self._find(root, texts=texts, resource_suffix=resource_suffix)
        if node is None:
            return False
        self._tap(serial, root, node)
        return True

    @staticmethod
    def _is_connected_ui(root: ET.Element) -> bool:
        texts = visible_text(root)
        return (
            bool({"카메라 내 이미지 가져오기", "Import Images from Camera"} & texts)
            or AdbSonyCameraImporter._find(root, resource_suffix="/datelistview") is not None
            or AdbSonyCameraImporter._find(root, resource_suffix="/btn_content_copy") is not None
        )

    def _open_sony_app(self, serial: str) -> ET.Element:
        def launch() -> None:
            self._adb(
                serial,
                "shell",
                "monkey",
                "-p",
                SONY_PACKAGE,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
                timeout=20,
            )
            self._sleep(3)

        launch()
        try:
            root = self._dump_ui(serial)
        except SonyCameraImportError as error:
            if error.code != "SONY_PHONE_UI_UNAVAILABLE":
                raise
            # Imaging Edge's Bluetooth Remote Power activity can leave Android's
            # accessibility hierarchy in a state where uiautomator is killed.
            # Restarting only the Sony app returns it to its inspectable camera
            # list without changing the persisted pairing or Wi-Fi approval.
            self._adb(serial, "shell", "am", "force-stop", SONY_PACKAGE)
            launch()
            root = self._dump_ui(serial)
        if is_android_keyguard(root):
            raise SonyCameraSetupRequired(
                "SONY_PHONE_UNLOCK_REQUIRED",
                "Unlock the dedicated Android phone once. To remain unattended after "
                "USB disconnects or restarts, set its screen lock to Swipe or None.",
            )
        if self._find(root, resource_suffix="/processing_screen") is not None:
            deadline = self._clock() + 15
            while self._clock() < deadline:
                if "ZV-E10" in self._wifi_ssid(serial):
                    break
                self._sleep(2)
            else:
                self._adb(serial, "shell", "am", "force-stop", SONY_PACKAGE)
                self._adb(
                    serial,
                    "shell",
                    "monkey",
                    "-p",
                    SONY_PACKAGE,
                    "-c",
                    "android.intent.category.LAUNCHER",
                    "1",
                )
                self._sleep(3)
                root = self._dump_ui(serial)
        return root

    def _ensure_camera_connection(
        self,
        serial: str,
        root: ET.Element,
        progress: Callable[[SonyImportProgress], None],
    ) -> ET.Element:
        if self._is_connected_ui(root):
            return root

        progress(SonyImportProgress("connecting", "Connecting to Sony ZV-E10"))
        start = self._find(root, texts=("시작", "Start"))
        if start is not None and "ZV-E10" in visible_text(root):
            self._tap(serial, root, start)
            connected = self._wait_for_connection(serial, 35)
            if connected is not None:
                return connected
            self._adb(serial, "shell", "am", "force-stop", SONY_PACKAGE)
            root = self._open_sony_app(serial)

        for attempt in range(2):
            self._open_remote_power(serial, root)
            self._tap_remote_power_camera(serial)
            connected = self._wait_for_connection(serial, 60)
            if connected is not None:
                return connected
            if attempt == 0:
                self._adb(serial, "shell", "am", "force-stop", SONY_PACKAGE)
                root = self._open_sony_app(serial)
        raise SonyCameraImportError(
            "SONY_CAMERA_CONNECTION_FAILED",
            "The paired ZV-E10 did not enter media-transfer mode.",
        )

    def _open_remote_power(self, serial: str, root: ET.Element) -> None:
        target_text = ("카메라 원격 전원 켬/끔", "Camera Remote Power ON/OFF")
        for _ in range(5):
            target = self._find(root, texts=target_text)
            if target is not None:
                self._tap(serial, root, target)
                break
            self._adb(
                serial,
                "shell",
                "input",
                "touchscreen",
                "swipe",
                "1000",
                "950",
                "1000",
                "380",
                "550",
            )
            self._sleep(1)
            root = self._dump_ui(serial)
        else:
            raise SonyCameraImportError(
                "SONY_REMOTE_POWER_UNAVAILABLE",
                "Imaging Edge Mobile does not expose Camera Remote Power ON/OFF.",
            )
        self._sleep(2)
        try:
            root = self._dump_ui(serial, attempts=1)
        except SonyCameraImportError as error:
            if error.code == "SONY_PHONE_UI_UNAVAILABLE":
                # Bluetooth discovery animates continuously on this screen. On
                # Samsung Android builds, uiautomator is killed while waiting for
                # the activity to become idle, so the guarded coordinate path
                # below takes over.
                return
            raise
        texts = visible_text(root)
        if (
            "Bluetooth를 이용한 전원 켬/끔이 호환되는 카메라에서 사용할 수 있는 기능입니다."
            in texts
            or "Remote power control is available for compatible cameras using Bluetooth." in texts
        ):
            self._click_if_present(serial, root, resource_suffix="android:id/button1")
            self._sleep(2)
            try:
                root = self._dump_ui(serial, attempts=1)
            except SonyCameraImportError as error:
                if error.code != "SONY_PHONE_UI_UNAVAILABLE":
                    raise
        if root.find(".//node[@package='com.android.settings']") is not None:
            self._accept_camera_wifi_request(serial, root)
            self._sleep(4)

    def _tap_remote_power_camera(self, serial: str) -> None:
        deadline = self._clock() + 10
        while self._clock() < deadline:
            if SONY_REMOTE_POWER_ACTIVITY in self._activity_state(serial):
                break
            self._sleep(1)
        else:
            raise SonyCameraSetupRequired(
                "SONY_REMOTE_POWER_SETUP_REQUIRED",
                "One-time setup required: pair ZV-E10 in Imaging Edge Mobile and enable "
                "Bluetooth plus Send to Smartphone Func. > Cnct. during Power OFF on the camera.",
            )

        # Imaging Edge needs time to discover its bonded BLE camera. The target
        # is the per-camera power control at the right of the first camera row.
        # Validate the exact activity and portrait display before using the
        # dedicated-phone coordinate so another app can never receive the tap.
        self._sleep(20)
        if SONY_REMOTE_POWER_ACTIVITY not in self._activity_state(serial):
            raise SonyCameraImportError(
                "SONY_REMOTE_POWER_UNAVAILABLE",
                "Imaging Edge Mobile left its Remote Power screen unexpectedly.",
            )
        width, height = parse_display_size(self._adb(serial, "shell", "wm", "size", timeout=15))
        self._adb(
            serial,
            "shell",
            "input",
            "touchscreen",
            "tap",
            str(round(width * 0.911)),
            str(round(height * 0.1395)),
        )

    def _accept_camera_wifi_request(self, serial: str, root: ET.Element) -> bool:
        if root.find(".//node[@package='com.android.settings']") is None:
            return False
        texts = visible_text(root)
        expected_title = {"기기에 연결할까요?", "Connect to device?"}
        has_camera_ssid = any("DIRECT-" in value and "ZV-E10" in value for value in texts)
        if not expected_title & texts or not has_camera_ssid:
            return False
        connect = self._find(root, texts=("연결", "Connect"))
        if connect is None:
            return False
        self._tap(serial, root, connect)
        return True

    def _wait_for_connection(self, serial: str, timeout: float) -> ET.Element | None:
        deadline = self._clock() + timeout
        while self._clock() < deadline:
            activity = self._activity_state(serial)
            if ANDROID_WIFI_REQUEST_ACTIVITY in activity:
                try:
                    request = self._dump_ui(serial, attempts=1)
                    if self._accept_camera_wifi_request(serial, request):
                        self._sleep(2)
                        continue
                except SonyCameraImportError:
                    pass
            elif (
                "ZV-E10" in self._wifi_ssid(serial)
                and SONY_WIFI_ACTIVITY not in activity
                and SONY_REMOTE_POWER_ACTIVITY not in activity
            ):
                try:
                    root = self._dump_ui(serial, attempts=1)
                    if self._is_connected_ui(root):
                        return root
                except SonyCameraImportError:
                    pass
            self._sleep(2)
        return None

    def _open_camera_import(self, serial: str, root: ET.Element) -> ET.Element:
        if self._find(root, resource_suffix="/btn_content_copy") is not None:
            self._adb(serial, "shell", "input", "keyevent", "4")
            self._sleep(2)
            root = self._dump_ui(serial)
        if self._find(root, resource_suffix="/datelistview") is not None:
            return root
        target = self._find(
            root,
            texts=("카메라 내 이미지 가져오기", "Import Images from Camera"),
        )
        if target is None:
            raise SonyCameraImportError(
                "SONY_IMPORT_VIEW_UNAVAILABLE",
                "The camera connected, but its image-import action is unavailable.",
            )
        self._tap(serial, root, target)
        self._sleep(3)
        root = self._dump_ui(serial)
        texts = visible_text(root)
        if any("HEIF" in value or "movie" in value.casefold() for value in texts):
            self._click_if_present(serial, root, resource_suffix="android:id/button1")
            self._sleep(4)
            root = self._dump_ui(serial)
        if self._find(root, resource_suffix="/datelistview") is None:
            raise SonyCameraImportError(
                "SONY_CAMERA_INVENTORY_FAILED",
                "The camera media list did not become available.",
            )
        return root

    def _import_missing_camera_items(
        self,
        serial: str,
        root: ET.Element,
        progress: Callable[[SonyImportProgress], None],
    ) -> None:
        known_names = {item.name.casefold() for item in self._list_phone_media(serial)} | {
            path.name.casefold()
            for path in self.destination.glob("*")
            if path.is_file() and path.suffix.casefold() in MEDIA_SUFFIXES
        }
        completed_dates: set[str] = set()
        unchanged_scrolls = 0
        while unchanged_scrolls < 2 and len(completed_dates) < 500:
            root = self._dump_ui(serial)
            date_nodes = [
                node
                for node in root.iter("node")
                if node.attrib.get("resource-id", "").endswith("/date") and node.attrib.get("text")
            ]
            next_date = next(
                (node for node in date_nodes if node.attrib["text"] not in completed_dates),
                None,
            )
            if next_date is None:
                before = tuple(node.attrib["text"] for node in date_nodes)
                list_view = self._find(root, resource_suffix="/datelistview")
                if list_view is None or list_view.attrib.get("scrollable") != "true":
                    break
                left, top, right, bottom = self._bounds(list_view)
                self._adb(
                    serial,
                    "shell",
                    "input",
                    "touchscreen",
                    "swipe",
                    str((left + right) // 2),
                    str(bottom - 80),
                    str((left + right) // 2),
                    str(top + 80),
                    "600",
                )
                self._sleep(2)
                after_root = self._dump_ui(serial)
                after = tuple(
                    node.attrib["text"]
                    for node in after_root.iter("node")
                    if node.attrib.get("resource-id", "").endswith("/date")
                    and node.attrib.get("text")
                )
                unchanged_scrolls = unchanged_scrolls + 1 if after == before else 0
                continue

            unchanged_scrolls = 0
            date = next_date.attrib["text"]
            completed_dates.add(date)
            progress(
                SonyImportProgress(
                    "inventory",
                    f"Checking camera media from {date}",
                    completed_items=len(completed_dates),
                )
            )
            self._tap(serial, root, next_date)
            self._sleep(3)
            grid = self._dump_ui(serial)
            selected = self._select_missing_grid_items(serial, grid, date, known_names)
            if selected:
                self._start_and_wait_for_transfer(serial, date, selected, progress)
                known_names.update(item.name.casefold() for item in self._list_phone_media(serial))
            self._adb(serial, "shell", "input", "keyevent", "4")
            self._sleep(2)

    @staticmethod
    def _bounds(node: ET.Element) -> tuple[int, int, int, int]:
        match = re.fullmatch(r"\[(\d+),(\d+)]\[(\d+),(\d+)]", node.attrib.get("bounds", ""))
        if match is None:
            raise SonyCameraImportError("SONY_PHONE_UI_INVALID", "Android UI bounds are invalid.")
        return tuple(int(value) for value in match.groups())  # type: ignore[return-value]

    def _grid_items(self, root: ET.Element, date: str) -> list[_GridItem]:
        parents = self._parent_map(root)
        result: list[_GridItem] = []
        for name_node in root.iter("node"):
            if not name_node.attrib.get("resource-id", "").endswith("/file_name"):
                continue
            stem = name_node.attrib.get("text", "").strip()
            if not stem:
                continue
            card = name_node
            checkbox: ET.Element | None = None
            for _ in range(7):
                checkbox = self._find(card, resource_suffix="/checkbox_tap_area")
                if checkbox is not None:
                    break
                if card not in parents:
                    break
                card = parents[card]
            if checkbox is None:
                continue
            type_node = self._find(card, resource_suffix="/content_type")
            content_type = type_node.attrib.get("text", "") if type_node is not None else ""
            result.append(
                _GridItem(
                    key=f"{date}|{stem}|{content_type}",
                    stem=stem,
                    content_type=content_type,
                    checkbox=checkbox,
                )
            )
        return result

    @staticmethod
    def _expected_name_groups(item: _GridItem) -> tuple[frozenset[str], ...]:
        """Return required filename groups, with alternatives within each group."""

        kind = item.content_type.casefold()
        stem = item.stem.casefold()
        if "xavc" in kind or "movie" in kind or "mp4" in kind:
            return (frozenset({f"{stem}.mp4"}),)
        if "raw" in kind and "jpeg" in kind:
            return (
                frozenset({f"{stem}.arw"}),
                frozenset({f"{stem}.jpg", f"{stem}.jpeg"}),
            )
        if "raw" in kind:
            return (frozenset({f"{stem}.arw"}),)
        if "heif" in kind:
            return (frozenset({f"{stem}.hif", f"{stem}.heic"}),)
        if "jpeg" in kind or "jpg" in kind:
            return (frozenset({f"{stem}.jpg", f"{stem}.jpeg"}),)
        return ()

    @classmethod
    def _grid_item_is_known(cls, item: _GridItem, known_names: set[str]) -> bool:
        groups = cls._expected_name_groups(item)
        return bool(groups) and all(group & known_names for group in groups)

    def _select_missing_grid_items(
        self,
        serial: str,
        root: ET.Element,
        date: str,
        known_names: set[str],
    ) -> list[str]:
        selected: list[str] = []
        seen: set[str] = set()
        unchanged_scrolls = 0
        while unchanged_scrolls < 2:
            items = self._grid_items(root, date)
            new_keys = {item.key for item in items} - seen
            unchanged_scrolls = unchanged_scrolls + 1 if not new_keys else 0
            for item in items:
                if item.key in seen:
                    continue
                seen.add(item.key)
                if not self._grid_item_is_known(item, known_names):
                    self._tap(serial, root, item.checkbox)
                    selected.append(item.key)
                    self._sleep(0.15)
            count_node = self._find(root, resource_suffix="/item_count")
            count_match = (
                re.search(r"\d+", count_node.attrib.get("text", ""))
                if count_node is not None
                else None
            )
            if count_match is not None and len(seen) >= int(count_match.group()):
                break
            grid = self._find(root, resource_suffix="/thumbnails")
            if grid is None or grid.attrib.get("scrollable") != "true":
                break
            left, top, right, bottom = self._bounds(grid)
            self._adb(
                serial,
                "shell",
                "input",
                "touchscreen",
                "swipe",
                str((left + right) // 2),
                str(bottom - 70),
                str((left + right) // 2),
                str(top + 70),
                "550",
            )
            self._sleep(2)
            root = self._dump_ui(serial)
        return selected

    def _start_and_wait_for_transfer(
        self,
        serial: str,
        date: str,
        selected: list[str],
        progress: Callable[[SonyImportProgress], None],
    ) -> None:
        root = self._dump_ui(serial)
        copy_button = self._find(root, resource_suffix="/btn_content_copy")
        if copy_button is None or copy_button.attrib.get("enabled") != "true":
            raise SonyCameraImportError(
                "SONY_CAMERA_SELECTION_FAILED", "New camera items could not be selected."
            )
        self._tap(serial, root, copy_button)
        self._sleep(2)
        root = self._dump_ui(serial)
        texts = visible_text(root)
        if not ({"원본", "Original"} & texts):
            self._click_if_present(serial, root, resource_suffix="android:id/button2")
            raise SonyCameraSetupRequired(
                "SONY_ORIGINAL_SIZE_SETUP_REQUIRED",
                "Set Imaging Edge Mobile > Import Settings > Import Image Size to Original once.",
            )
        ok = self._find(root, resource_suffix="android:id/button1")
        if ok is None:
            raise SonyCameraImportError(
                "SONY_TRANSFER_CONFIRMATION_MISSING",
                "The original-size transfer confirmation did not appear.",
            )
        self._tap(serial, root, ok)
        started = self._clock()
        while self._clock() - started < self._transfer_timeout:
            remote = self._list_phone_media(serial)
            progress(
                SonyImportProgress(
                    "transferring",
                    f"Importing {len(selected)} original item(s) from {date}",
                    bytes_on_phone=sum(item.size for item in remote),
                )
            )
            try:
                root = self._dump_ui(serial, attempts=1)
            except SonyCameraImportError:
                self._sleep(4)
                continue
            texts = visible_text(root)
            if {"항목 복사 완료.", "Items copied."} & texts:
                self._click_if_present(serial, root, resource_suffix="android:id/button1")
                self._sleep(2)
                return
            if any("실패" in value or "failed" in value.casefold() for value in texts):
                raise SonyCameraImportError(
                    "SONY_TRANSFER_FAILED", "Imaging Edge Mobile reported a transfer failure."
                )
            self._sleep(4)
        raise SonyCameraImportError(
            "SONY_TRANSFER_TIMEOUT",
            "The camera transfer did not finish within two hours.",
        )

    def _copy_and_verify(
        self,
        serial: str,
        progress: Callable[[SonyImportProgress], None],
    ) -> SonyImportResult:
        self.destination.mkdir(parents=True, exist_ok=True)
        remote_files = self._list_phone_media(serial)
        if remote_files:
            sha_output = self._shell(
                serial,
                f"cd '{PHONE_MEDIA_DIRECTORY}' && sha256sum -- *",
                timeout=max(120, len(remote_files) * 30),
            )
            remote_hashes = parse_sha256_lines(sha_output)
        else:
            remote_hashes = {}
        if len(remote_hashes) < len(remote_files):
            raise SonyCameraImportError(
                "SONY_PHONE_HASH_FAILED",
                "The phone could not hash every completed media file.",
            )

        copied = 0
        skipped = 0
        copied_bytes = 0
        manifest_files: list[dict[str, object]] = []
        total_bytes = sum(item.size for item in remote_files)
        for index, remote in enumerate(remote_files, start=1):
            expected_hash = remote_hashes[remote.name]
            target = self.destination / remote.name
            if self._matches_remote(target, remote, expected_hash):
                skipped += 1
                manifest_files.append(
                    {"name": target.name, "sizeBytes": remote.size, "sha256": expected_hash}
                )
                progress(
                    SonyImportProgress(
                        "verifying",
                        f"Verified {target.name}",
                        completed_items=index,
                        total_items=len(remote_files),
                        bytes_on_phone=total_bytes,
                    )
                )
                continue
            if target.exists():
                target = self._collision_target(
                    target,
                    remote,
                    expected_hash,
                )
                if self._matches_remote(target, remote, expected_hash):
                    skipped += 1
                    manifest_files.append(
                        {"name": target.name, "sizeBytes": remote.size, "sha256": expected_hash}
                    )
                    progress(
                        SonyImportProgress(
                            "verifying",
                            f"Verified {target.name}",
                            completed_items=index,
                            total_items=len(remote_files),
                            bytes_on_phone=total_bytes,
                        )
                    )
                    continue
            part = target.with_name(f".{target.name}.cit-part")
            part.unlink(missing_ok=True)
            remote_path = f"{PHONE_MEDIA_DIRECTORY}/{remote.name}"
            try:
                self._adb(
                    serial,
                    "pull",
                    "-a",
                    remote_path,
                    str(part),
                    timeout=max(120, remote.size / 2_000_000),
                )
                if part.stat().st_size != remote.size or self._hash_file(part) != expected_hash:
                    raise SonyCameraImportError(
                        "SONY_PC_VERIFICATION_FAILED",
                        f"Checksum verification failed for {remote.name}.",
                    )
                os.replace(part, target)
            finally:
                part.unlink(missing_ok=True)
            copied += 1
            copied_bytes += remote.size
            manifest_files.append(
                {"name": target.name, "sizeBytes": remote.size, "sha256": expected_hash}
            )
            progress(
                SonyImportProgress(
                    "verifying",
                    f"Copied and verified {target.name}",
                    completed_items=index,
                    total_items=len(remote_files),
                    bytes_on_phone=total_bytes,
                )
            )

        summary = {
            "schemaVersion": "1.0",
            "camera": "Sony ZV-E10",
            "source": "Imaging Edge Mobile over USB/ADB",
            "verified": True,
            "cameraFilesDeleted": False,
            "phoneFilesDeleted": False,
            "fileCount": len(remote_files),
            "totalBytes": total_bytes,
            "files": manifest_files,
        }
        summary_path = self.destination / "sony-camera-import-summary.json"
        temporary = summary_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, summary_path)
        return SonyImportResult(
            copied_files=copied,
            skipped_files=skipped,
            verified_files=len(remote_files),
            copied_bytes=copied_bytes,
            total_bytes=total_bytes,
        )

    def _collision_target(
        self,
        original: Path,
        remote: _RemoteFile,
        expected_hash: str,
    ) -> Path:
        """Choose a collision-safe target without overwriting unrelated content."""

        suffix = expected_hash[:8]
        candidate = original.with_name(f"{original.stem}__{suffix}{original.suffix}")
        index = 2
        while candidate.exists() and not self._matches_remote(candidate, remote, expected_hash):
            candidate = original.with_name(f"{original.stem}__{suffix}_{index}{original.suffix}")
            index += 1
        return candidate

    def _matches_remote(
        self,
        path: Path,
        remote: _RemoteFile,
        expected_hash: str,
    ) -> bool:
        return (
            path.is_file()
            and path.stat().st_size == remote.size
            and self._hash_file(path) == expected_hash
        )

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
