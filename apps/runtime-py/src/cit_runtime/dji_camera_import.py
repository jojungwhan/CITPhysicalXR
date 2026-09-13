"""Conservative DJI Osmo Nano imports through DJI Mimo on Android.

DJI documents Bluetooth/Wi-Fi transfer from Osmo Nano to DJI Mimo, but does
not publish a Nano desktop-transfer API.  This adapter drives only the visible
Mimo controls, selects media identities that are not already on the phone or
PC, and then performs append-only, SHA-256 verified ADB copies.  It never sends
a delete, format, record, or camera-settings action.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath

from .sony_camera_import import (
    AIR_COMMAND_PACKAGE,
    BatteryReading,
    ProcessRunner,
    SonyCameraImportError,
    SonyCameraSetupRequired,
    SonyImportProgress,
    SonyImportResult,
    SonyPhoneProbe,
    bounds_center,
    is_android_keyguard,
    parse_adb_devices,
    parse_android_battery,
    parse_camera_battery_ui,
    require_battery_for_sync,
    run_process,
    visible_text,
)

DJI_PACKAGE = "dji.mimo"
DJI_UI_DUMP_PATH = "/sdcard/cit-dji-mimo-ui.xml"
DJI_CAMERA_CACHE_DIRECTORY = "/sdcard/Android/data/dji.mimo/cache/ImageCaches"
DJI_PHONE_MEDIA_DIRECTORIES = (
    "/sdcard/DCIM/DJI Album",
    "/sdcard/DCIM/DJI Export",
    "/sdcard/Android/data/dji.mimo/files/DCIM/OriginalFiles/Video",
    "/sdcard/Android/data/dji.mimo/files/DCIM/OriginalFiles/Photo",
    "/sdcard/Android/data/dji.mimo/files/DCIM/OriginalFiles/PanoPhoto",
)
DJI_MEDIA_SUFFIXES = frozenset({".dng", ".heic", ".jpeg", ".jpg", ".mov", ".mp4", ".wav"})
DJI_MULTIPLE_SELECT_RESOURCE = "dji.mimo:id/image_multiple_select"
DJI_PLAYBACK_RECYCLER_RESOURCE = "dji.mimo:id/playback_main_recycler"
DJI_PLAYBACK_DATE_RESOURCE = "dji.mimo:id/text_title"
DJI_PLAYBACK_IMAGE_RESOURCE = "dji.mimo:id/v2_hg_childitem_img"
DJI_PLAYBACK_DURATION_RESOURCE = "dji.mimo:id/v2_hg_childitem_time"
DJI_TESTED_MIMO_VERSION = "2.11.9"

_DJI_CAMERA_CACHE_PATTERN = re.compile(
    r"^(?:Video|Photo)_\d+_"
    r"(?P<stem>DJI_(?P<timestamp>\d{14})_(?P<sequence>\d{4})_[A-Za-z0-9_-]+)_"
    r"(?P<extension>DNG|HEIC|JPEG|JPG|MOV|MP4|WAV)_"
    r"(?P<size>\d+)_(?P<duration_ms>\d+)_[A-Za-z0-9_-]+_photo_preview\.jpe?g$",
    re.IGNORECASE,
)
_DJI_EXPORTED_MEDIA_PATTERN = re.compile(
    r"^dji_mimo_(?P<date>\d{8})_(?P<time>\d{6})_(?P<sequence>\d{4})_"
    r"\d+_[A-Za-z0-9_-]+(?P<extension>\.[A-Za-z0-9]+)$",
    re.IGNORECASE,
)


class DjiCameraImportError(SonyCameraImportError):
    """A stable, user-actionable DJI import failure."""


class DjiCameraSetupRequired(SonyCameraSetupRequired, DjiCameraImportError):
    """DJI Mimo or Osmo Nano requires a one-time user-confirmed setup step."""


@dataclass(frozen=True)
class DjiRemoteFile:
    path: str
    name: str
    size: int


@dataclass(frozen=True)
class DjiCameraMediaIdentity:
    name: str
    sequence: str
    size: int
    duration_seconds: int
    captured_at: datetime


@dataclass(frozen=True)
class DjiPlaybackItem:
    capture_date: date
    duration_seconds: int
    node: ET.Element


def parse_dji_camera_cache_listing(output: str) -> list[DjiCameraMediaIdentity]:
    """Recover stable Nano identities from Mimo's externally readable preview cache."""

    media: dict[str, DjiCameraMediaIdentity] = {}
    for raw_line in output.splitlines():
        cache_name = PurePosixPath(raw_line.strip()).name
        match = _DJI_CAMERA_CACHE_PATTERN.fullmatch(cache_name)
        if match is None:
            continue
        try:
            captured_at = datetime.strptime(match.group("timestamp"), "%Y%m%d%H%M%S")
        except ValueError:
            continue
        extension = match.group("extension").upper()
        name = f"{match.group('stem')}.{extension}"
        media[name.casefold()] = DjiCameraMediaIdentity(
            name=name,
            sequence=match.group("sequence"),
            size=int(match.group("size")),
            duration_seconds=int(match.group("duration_ms")) // 1_000,
            captured_at=captured_at,
        )
    return sorted(media.values(), key=lambda item: (item.captured_at, item.name.casefold()))


def _normalized_media_extension(value: str) -> str:
    normalized = value.casefold()
    return ".jpg" if normalized == ".jpeg" else normalized


def camera_media_matches_download(
    media: DjiCameraMediaIdentity,
    downloaded_name: str,
    downloaded_size: int,
) -> bool:
    """Match a Mimo-renamed export back to its stable Nano media identity."""

    if downloaded_size != media.size:
        return False
    if downloaded_name.casefold() == media.name.casefold():
        return True
    match = _DJI_EXPORTED_MEDIA_PATTERN.fullmatch(PurePosixPath(downloaded_name).name)
    if match is None or match.group("sequence") != media.sequence:
        return False
    if _normalized_media_extension(match.group("extension")) != _normalized_media_extension(
        Path(media.name).suffix
    ):
        return False
    try:
        exported_at = datetime.strptime(
            f"{match.group('date')}{match.group('time')}",
            "%Y%m%d%H%M%S",
        )
    except ValueError:
        return False
    return abs((exported_at - media.captured_at).total_seconds()) <= 5


def dji_download_action_center(width: int, height: int) -> tuple[int, int]:
    """Return Mimo 2.11.9's middle (download) action, never its delete column."""

    if width <= 0 or height <= width:
        raise ValueError("DJI Mimo download automation requires a portrait display")
    return width // 2, height * 37 // 40


def match_dji_playback_media(
    media: Sequence[DjiCameraMediaIdentity],
    playback_items: Sequence[DjiPlaybackItem],
) -> list[tuple[DjiCameraMediaIdentity, DjiPlaybackItem]]:
    """Match only unambiguous date/duration pairs exposed by Mimo's device grid."""

    matches: list[tuple[DjiCameraMediaIdentity, DjiPlaybackItem]] = []
    used: set[str] = set()
    for item in playback_items:
        candidates = [
            candidate
            for candidate in media
            if candidate.name.casefold() not in used
            and candidate.captured_at.date() == item.capture_date
            and candidate.duration_seconds == item.duration_seconds
        ]
        if len(candidates) != 1:
            continue
        candidate = candidates[0]
        used.add(candidate.name.casefold())
        matches.append((candidate, item))
    return matches


def parse_dji_remote_listing(output: str) -> list[DjiRemoteFile]:
    files: dict[str, DjiRemoteFile] = {}
    roots = tuple(f"{root}/" for root in DJI_PHONE_MEDIA_DIRECTORIES)
    for raw_line in output.splitlines():
        size_text, separator, remote_path = raw_line.strip().partition("|")
        if not separator or not size_text.isdigit():
            continue
        normalized_path = remote_path.strip()
        if not normalized_path.startswith(roots):
            continue
        parsed_path = PurePosixPath(normalized_path)
        if ".." in parsed_path.parts:
            continue
        name = parsed_path.name
        if (
            not name
            or name.startswith(".pending-")
            or Path(name).suffix.casefold() not in DJI_MEDIA_SUFFIXES
        ):
            continue
        files[normalized_path] = DjiRemoteFile(
            path=normalized_path,
            name=name,
            size=int(size_text),
        )
    return sorted(files.values(), key=lambda item: (item.name.casefold(), item.path))


class AdbDjiCameraImporter:
    """Drive visible Mimo import UI, then verify append-only copies to the PC."""

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

    def probe(self) -> SonyPhoneProbe:
        try:
            serial = self._resolve_serial()
            model = self._adb(serial, "shell", "getprop", "ro.product.model").strip() or None
            installed = self._package_installed(serial)
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
            remote = self._list_phone_media(serial)
            return SonyPhoneProbe(
                phone_connected=True,
                phone_model=model,
                app_installed=installed,
                bluetooth_enabled=bluetooth,
                camera_wifi_connected=self._is_osmo_wifi(wifi),
                phone_battery=phone_battery,
                files_on_phone=len(remote),
                bytes_on_phone=sum(item.size for item in remote),
                message=(None if installed else "DJI Mimo is not installed."),
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
        if not self._package_installed(serial):
            raise DjiCameraSetupRequired(
                "DJI_APP_NOT_INSTALLED",
                "Install DJI Mimo on the dedicated Android phone once.",
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
            code="DJI_PHONE_BATTERY_LOW",
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
            progress(SonyImportProgress("connecting", "Preparing DJI Mimo"))
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
            self._adb(serial, "shell", "svc", "wifi", "enable", check=False)
            self._adb(serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP", check=False)
            self._adb(serial, "shell", "wm", "dismiss-keyguard", check=False)

            root = self._open_mimo(serial)
            root = self._ensure_camera_connection(serial, root, progress)
            camera_battery = parse_camera_battery_ui(root, package=DJI_PACKAGE)
            progress(
                SonyImportProgress(
                    "connecting",
                    "Checking DJI Osmo Nano battery",
                    phone_battery=phone_battery,
                    camera_battery=camera_battery,
                )
            )
            require_battery_for_sync(
                camera_battery,
                code="DJI_CAMERA_BATTERY_LOW",
                device="camera",
                display_name="DJI Osmo Nano",
            )
            playback = self._open_playback(serial, root)
            self._download_missing_camera_items(serial, playback, progress)
            progress(SonyImportProgress("copying", "Copying DJI originals to this PC"))
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
        return parse_adb_devices(
            self._host_adb("devices", timeout=15),
            self.preferred_serial,
        )

    def _host_adb(self, *args: str, timeout: float = 30, check: bool = True) -> str:
        try:
            result = self._run_process((self.adb_path, *args), timeout=timeout)
        except FileNotFoundError as error:
            raise DjiCameraImportError(
                "ADB_NOT_INSTALLED", "Android platform-tools (adb) are not installed."
            ) from error
        except subprocess.TimeoutExpired as error:
            raise DjiCameraImportError("ADB_TIMEOUT", "Android did not respond in time.") from error
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise DjiCameraImportError(
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

    def _package_installed(self, serial: str) -> bool:
        return self._adb(
            serial,
            "shell",
            "pm",
            "path",
            DJI_PACKAGE,
            check=False,
        ).startswith("package:")

    def _wifi_ssid(self, serial: str) -> str:
        output = self._adb(serial, "shell", "dumpsys", "wifi", timeout=45, check=False)
        match = re.search(r'mWifiInfo SSID: (?:(?:"([^"]+)")|([^,\r\n]+))', output)
        return (match.group(1) or match.group(2)).strip() if match is not None else ""

    def _read_phone_battery(self, serial: str) -> BatteryReading:
        return parse_android_battery(self._adb(serial, "shell", "dumpsys", "battery", check=False))

    @staticmethod
    def _is_osmo_wifi(ssid: str) -> bool:
        normalized = ssid.casefold().replace(" ", "")
        return "osmo" in normalized or "djiosmo" in normalized

    def _list_phone_media(self, serial: str) -> list[DjiRemoteFile]:
        roots = " ".join(shlex.quote(root) for root in DJI_PHONE_MEDIA_DIRECTORIES)
        listing = self._shell(
            serial,
            "for root in "
            f'{roots}; do if [ -d "$root" ]; then '
            "find \"$root\" -type f -exec stat -c '%s|%n' '{}' ';'; fi; done",
            timeout=90,
        )
        return parse_dji_remote_listing(listing)

    def _list_camera_media(self, serial: str) -> list[DjiCameraMediaIdentity]:
        cache_root = shlex.quote(DJI_CAMERA_CACHE_DIRECTORY)
        listing = self._shell(
            serial,
            f"if [ -d {cache_root} ]; then "
            f"find {cache_root} -maxdepth 1 -type f -printf '%f\\n'; fi",
            timeout=90,
        )
        return parse_dji_camera_cache_listing(listing)

    def _phone_today(self, serial: str) -> date:
        value = self._shell(serial, "date +%Y-%m-%d", timeout=15).strip()
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise DjiCameraImportError(
                "DJI_PHONE_CLOCK_INVALID",
                "The dedicated DJI phone date could not be read.",
            ) from error

    def _known_downloads(self, serial: str) -> list[tuple[str, int]]:
        known = [(item.name, item.size) for item in self._list_phone_media(serial)]
        for path in self.destination.glob("*"):
            if not path.is_file() or path.suffix.casefold() not in DJI_MEDIA_SUFFIXES:
                continue
            try:
                known.append((path.name, path.stat().st_size))
            except OSError:
                continue
        return known

    @staticmethod
    def _camera_media_is_known(
        media: DjiCameraMediaIdentity,
        downloads: Sequence[tuple[str, int]],
    ) -> bool:
        return any(camera_media_matches_download(media, name, size) for name, size in downloads)

    def _dump_ui(self, serial: str, *, attempts: int = 4) -> ET.Element:
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                dump_result = self._adb(
                    serial,
                    "shell",
                    "uiautomator",
                    "dump",
                    DJI_UI_DUMP_PATH,
                    timeout=20,
                )
                if "dumped to" not in dump_result.casefold():
                    raise DjiCameraImportError(
                        "DJI_PHONE_UI_BUSY",
                        "DJI Mimo's animated screen did not become idle.",
                    )
                body = self._shell(serial, f"cat {shlex.quote(DJI_UI_DUMP_PATH)}", timeout=10)
                return ET.fromstring(body)
            except (ET.ParseError, SonyCameraImportError) as error:
                last_error = error
                self._sleep(1)
        raise DjiCameraImportError(
            "DJI_PHONE_UI_UNAVAILABLE",
            "The DJI Mimo screen could not be read. Keep the dedicated phone unlocked.",
        ) from last_error

    @staticmethod
    def _values(node: ET.Element) -> tuple[str, str]:
        return (
            node.attrib.get("text", "").strip(),
            node.attrib.get("content-desc", "").strip(),
        )

    @classmethod
    def _find_text(cls, root: ET.Element, texts: Sequence[str]) -> ET.Element | None:
        wanted = {text.casefold() for text in texts}
        for node in root.iter("node"):
            if any(value.casefold() in wanted for value in cls._values(node) if value):
                return node
        return None

    @classmethod
    def _find_contains(cls, root: ET.Element, values: Sequence[str]) -> ET.Element | None:
        wanted = tuple(value.casefold() for value in values)
        for node in root.iter("node"):
            if any(
                marker in value.casefold()
                for value in cls._values(node)
                if value
                for marker in wanted
            ):
                return node
        return None

    @staticmethod
    def _find_resource(root: ET.Element, resource_id: str) -> ET.Element | None:
        return next(
            (node for node in root.iter("node") if node.attrib.get("resource-id") == resource_id),
            None,
        )

    @staticmethod
    def _parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
        return {child: parent for parent in root.iter() for child in parent}

    def _tap(self, serial: str, root: ET.Element, node: ET.Element) -> None:
        parents = self._parent_map(root)
        target = node
        while target.attrib.get("clickable") != "true" and target in parents:
            target = parents[target]
        x, y = bounds_center(target.attrib.get("bounds", node.attrib.get("bounds", "")))
        self._adb(serial, "shell", "input", "touchscreen", "tap", str(x), str(y))

    @classmethod
    def _selection_count(cls, root: ET.Element) -> int | None:
        selection = cls._find_resource(root, "dji.mimo:id/tv_select_message")
        selection_text = selection.attrib.get("text", "") if selection is not None else ""
        count_match = re.search(r"\d+", selection_text)
        return int(count_match.group()) if count_match is not None else None

    def _tap_download_action(
        self,
        serial: str,
        root: ET.Element,
        *,
        expected_count: int,
    ) -> None:
        actual_count = self._selection_count(root)
        if actual_count != expected_count:
            raise DjiCameraImportError(
                "DJI_MEDIA_SELECTION_CHANGED",
                "DJI Mimo's media selection changed; CIT refused to press an action.",
            )
        if root.attrib.get("rotation", "0") != "0":
            raise DjiCameraImportError(
                "DJI_PHONE_ORIENTATION_UNSAFE",
                "Keep the dedicated DJI phone in portrait orientation.",
            )

        package = self._adb(
            serial,
            "shell",
            "dumpsys",
            "package",
            DJI_PACKAGE,
            timeout=45,
        )
        version_match = re.search(r"^\s*versionName=([^\s]+)", package, re.MULTILINE)
        version = version_match.group(1) if version_match is not None else ""
        if version != DJI_TESTED_MIMO_VERSION:
            raise DjiCameraImportError(
                "DJI_MIMO_VERSION_UNVERIFIED",
                f"DJI Mimo {version or 'unknown'} has not been verified for safe automation.",
            )

        window = self._adb(serial, "shell", "dumpsys", "window", timeout=45)
        focus = next(
            (line for line in window.splitlines() if "mCurrentFocus=" in line),
            "",
        )
        if f"{DJI_PACKAGE}/" not in focus:
            raise DjiCameraImportError(
                "DJI_MIMO_NOT_FOREGROUND",
                "DJI Mimo left the foreground; CIT refused to press an action.",
            )

        size_output = self._adb(serial, "shell", "wm", "size")
        sizes = re.findall(r"(?:Physical|Override) size:\s*(\d+)x(\d+)", size_output)
        if not sizes:
            raise DjiCameraImportError(
                "DJI_PHONE_UI_INVALID",
                "The dedicated phone display size could not be verified.",
            )
        width, height = (int(value) for value in sizes[-1])
        try:
            x, y = dji_download_action_center(width, height)
        except ValueError as error:
            raise DjiCameraImportError(
                "DJI_PHONE_ORIENTATION_UNSAFE",
                str(error),
            ) from error
        self._adb(
            serial,
            "shell",
            "input",
            "touchscreen",
            "tap",
            str(x),
            str(y),
        )

    def _open_mimo(self, serial: str) -> ET.Element:
        self._adb(
            serial,
            "shell",
            "monkey",
            "-p",
            DJI_PACKAGE,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
            timeout=20,
        )
        self._sleep(4)
        root = self._dump_ui(serial)
        if is_android_keyguard(root):
            raise DjiCameraSetupRequired(
                "DJI_PHONE_UNLOCK_REQUIRED",
                "Unlock the dedicated Android phone once. For unattended recovery, "
                "set this spare phone's screen lock to Swipe or None.",
            )
        if any(
            "permissioncontroller" in node.attrib.get("package", "").casefold()
            for node in root.iter("node")
        ):
            raise DjiCameraSetupRequired(
                "DJI_MIMO_PERMISSION_REQUIRED",
                "Review DJI Mimo's Android permissions on the dedicated phone once.",
            )
        consent = self._find_contains(
            root,
            ("Agree and Continue", "Agree", "동의하고 계속", "동의"),
        )
        legal = self._find_contains(
            root,
            (
                "Terms of Use",
                "Privacy Policy",
                "Privacy Notice",
                "User Agreement",
                "이용약관",
                "이용 약관",
                "개인정보 처리방침",
                "사용자 계약",
            ),
        )
        if consent is not None and legal is not None:
            raise DjiCameraSetupRequired(
                "DJI_MIMO_CONSENT_REQUIRED",
                "Open DJI Mimo once and review its user agreement and privacy choices.",
            )
        mimo_permission = self._find_contains(
            root,
            (
                "DJI Mimo would like to access",
                "DJI Mimo requires access",
                "DJI Mimo에 모바일 기기",
                "Permission Request",
            ),
        )
        if mimo_permission is not None:
            raise DjiCameraSetupRequired(
                "DJI_MIMO_PERMISSION_REQUIRED",
                "Review DJI Mimo's requested permissions on the dedicated phone once.",
            )
        return root

    @classmethod
    def _connected_ui(cls, root: ET.Element, wifi_ssid: str) -> bool:
        has_camera_view = (
            cls._find_resource(root, DJI_PLAYBACK_RECYCLER_RESOURCE) is not None
            or cls._find_contains(
                root,
                ("album", "playback", "앨범", "재생", "osmo nano"),
            )
            is not None
        )
        return has_camera_view and (
            cls._is_osmo_wifi(wifi_ssid)
            or cls._find_text(root, ("Connected", "연결됨")) is not None
        )

    def _ensure_camera_connection(
        self,
        serial: str,
        root: ET.Element,
        progress: Callable[[SonyImportProgress], None],
    ) -> ET.Element:
        wifi = self._wifi_ssid(serial)
        if self._connected_ui(root, wifi):
            return root
        progress(SonyImportProgress("connecting", "Connecting to DJI Osmo Nano"))

        nano = self._find_contains(root, ("Osmo Nano",))
        if nano is not None:
            self._tap(serial, root, nano)
            self._sleep(2)
            root = self._dump_ui(serial)
        connect = self._find_text(root, ("Connect", "연결"))
        if connect is not None:
            self._tap(serial, root, connect)

        deadline = self._clock() + 90
        while self._clock() < deadline:
            self._sleep(2)
            root = self._dump_ui(serial, attempts=1)
            texts = visible_text(root)
            if self._connected_ui(root, self._wifi_ssid(serial)):
                return root
            if any(
                marker in value.casefold()
                for value in texts
                for marker in ("verification code", "인증 코드", "activate", "활성화")
            ):
                raise DjiCameraSetupRequired(
                    "DJI_NANO_ACTIVATION_REQUIRED",
                    "Complete Osmo Nano activation and approve its first connection "
                    "in DJI Mimo once.",
                )
        raise DjiCameraSetupRequired(
            "DJI_NANO_PAIRING_REQUIRED",
            "Power on Osmo Nano and pair it with DJI Mimo once. DJI documents Wi-Fi and "
            "Bluetooth transfer but does not guarantee remote wake from every power state.",
        )

    def _open_playback(self, serial: str, root: ET.Element) -> ET.Element:
        if self._find_resource(root, DJI_MULTIPLE_SELECT_RESOURCE) is not None:
            return root
        selection_count = self._selection_count(root)
        if selection_count is not None:
            if selection_count != 0:
                raise DjiCameraImportError(
                    "DJI_MEDIA_SELECTION_BUSY",
                    "DJI Mimo already has user-selected media; cancel it on the phone once.",
                )
            cancel = self._find_resource(root, "dji.mimo:id/image_cancel_multiple_select")
            if cancel is None:
                raise DjiCameraImportError(
                    "DJI_PLAYBACK_UNAVAILABLE",
                    "DJI Mimo did not expose its completed selection close action.",
                )
            self._tap(serial, root, cancel)
            self._sleep(1)
            root = self._dump_ui(serial)
            if self._find_resource(root, DJI_MULTIPLE_SELECT_RESOURCE) is not None:
                return root
        device_tab = self._find_resource(root, "dji.mimo:id/tv_title_playback")
        if device_tab is not None:
            self._tap(serial, root, device_tab)
            self._sleep(1)
            root = self._dump_ui(serial)
            if self._find_resource(root, DJI_MULTIPLE_SELECT_RESOURCE) is not None:
                return root
        album = self._find_contains(root, ("album", "playback", "앨범", "재생"))
        if album is None:
            raise DjiCameraImportError(
                "DJI_PLAYBACK_UNAVAILABLE",
                "DJI Mimo connected, but its camera album control was not exposed to Android.",
            )
        self._tap(serial, root, album)
        self._sleep(4)
        root = self._dump_ui(serial)
        if self._find_resource(root, DJI_MULTIPLE_SELECT_RESOURCE) is None:
            raise DjiCameraImportError(
                "DJI_PLAYBACK_UNAVAILABLE",
                "DJI Mimo did not open the Osmo Nano media list.",
            )
        return root

    @staticmethod
    def _duration_seconds(value: str) -> int | None:
        parts = value.strip().split(":")
        if len(parts) not in {2, 3} or any(not part.isdigit() for part in parts):
            return None
        numbers = [int(part) for part in parts]
        if len(numbers) == 2:
            minutes, seconds = numbers
            hours = 0
        else:
            hours, minutes, seconds = numbers
        if minutes >= 60 or seconds >= 60:
            return None
        return hours * 3_600 + minutes * 60 + seconds

    @staticmethod
    def _capture_date(label: str, today: date) -> date | None:
        normalized = label.strip().casefold()
        if normalized in {"today", "오늘"}:
            return today
        if normalized in {"yesterday", "어제"}:
            return today - timedelta(days=1)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
            try:
                return date.fromisoformat(normalized)
            except ValueError:
                return None
        partial = re.fullmatch(r"(?P<month>\d{2})-(?P<day>\d{2})", normalized)
        if partial is not None:
            try:
                candidate = date(
                    today.year,
                    int(partial.group("month")),
                    int(partial.group("day")),
                )
            except ValueError:
                return None
            if candidate <= today:
                return candidate
            try:
                return candidate.replace(year=today.year - 1)
            except ValueError:
                return None
        return None

    @classmethod
    def _playback_items(cls, root: ET.Element, today: date) -> list[DjiPlaybackItem]:
        recycler = cls._find_resource(root, DJI_PLAYBACK_RECYCLER_RESOURCE)
        if recycler is None:
            return []
        capture_date: date | None = None
        items: list[DjiPlaybackItem] = []
        for child in recycler:
            title = cls._find_resource(child, DJI_PLAYBACK_DATE_RESOURCE)
            if title is not None:
                capture_date = cls._capture_date(title.attrib.get("text", ""), today)
                continue
            if capture_date is None:
                continue
            image = cls._find_resource(child, DJI_PLAYBACK_IMAGE_RESOURCE)
            duration = cls._find_resource(child, DJI_PLAYBACK_DURATION_RESOURCE)
            if image is None or duration is None:
                continue
            duration_seconds = cls._duration_seconds(duration.attrib.get("text", ""))
            if duration_seconds is None:
                continue
            items.append(
                DjiPlaybackItem(
                    capture_date=capture_date,
                    duration_seconds=duration_seconds,
                    node=child,
                )
            )
        return items

    @staticmethod
    def _media_name(node: ET.Element) -> str | None:
        for value in (
            node.attrib.get("text", ""),
            node.attrib.get("content-desc", ""),
        ):
            for token in re.split(r"[\s,;]+", value):
                cleaned = token.strip("()[]{}")
                if Path(cleaned).suffix.casefold() in DJI_MEDIA_SUFFIXES:
                    return PurePosixPath(cleaned).name
        return None

    @classmethod
    def _media_nodes(cls, root: ET.Element) -> dict[str, ET.Element]:
        return {
            name: node for node in root.iter("node") if (name := cls._media_name(node)) is not None
        }

    @staticmethod
    def _largest_scrollable(root: ET.Element) -> ET.Element | None:
        candidates = [node for node in root.iter("node") if node.attrib.get("scrollable") == "true"]
        if not candidates:
            return None

        def area(node: ET.Element) -> int:
            try:
                left, top, right, bottom = AdbDjiCameraImporter._bounds(node)
            except DjiCameraImportError:
                return 0
            return (right - left) * (bottom - top)

        return max(candidates, key=area)

    @staticmethod
    def _bounds(node: ET.Element) -> tuple[int, int, int, int]:
        match = re.fullmatch(r"\[(\d+),(\d+)]\[(\d+),(\d+)]", node.attrib.get("bounds", ""))
        if match is None:
            raise DjiCameraImportError("DJI_PHONE_UI_INVALID", "Android UI bounds are invalid.")
        return tuple(int(value) for value in match.groups())  # type: ignore[return-value]

    def _download_missing_camera_items(
        self,
        serial: str,
        root: ET.Element,
        progress: Callable[[SonyImportProgress], None],
    ) -> None:
        camera_media = self._list_camera_media(serial)
        today = self._phone_today(serial)
        playback_items = self._playback_items(root, today)
        if not camera_media:
            if not playback_items:
                return
            raise DjiCameraImportError(
                "DJI_MEDIA_IDENTITIES_UNAVAILABLE",
                "DJI Mimo showed camera media without stable cache identities; CIT refused "
                "to select it blindly.",
            )

        known_downloads = self._known_downloads(serial)
        missing = [
            media
            for media in camera_media
            if not self._camera_media_is_known(media, known_downloads)
        ]
        if not missing:
            return

        initial_matches = match_dji_playback_media(missing, playback_items)
        if len(initial_matches) != len(missing):
            raise DjiCameraImportError(
                "DJI_MEDIA_IDENTITIES_UNAVAILABLE",
                "DJI Mimo's dates and durations did not uniquely identify every new original; "
                "CIT refused to select it blindly.",
            )

        select = self._find_resource(root, DJI_MULTIPLE_SELECT_RESOURCE)
        if select is None:
            raise DjiCameraImportError(
                "DJI_MEDIA_SELECTION_UNAVAILABLE",
                "DJI Mimo did not expose media selection.",
            )

        selection_active = False
        try:
            self._tap(serial, root, select)
            selection_active = True
            self._sleep(2)
            root = self._dump_ui(serial)
            selection_matches = match_dji_playback_media(
                missing,
                self._playback_items(root, today),
            )
            if len(selection_matches) != len(missing):
                raise DjiCameraImportError(
                    "DJI_MEDIA_SELECTION_CHANGED",
                    "DJI Mimo's visible media changed while entering selection mode.",
                )

            selected: list[DjiCameraMediaIdentity] = []
            for media, item in selection_matches:
                self._tap(serial, root, item.node)
                selected.append(media)
                self._sleep(0.1)
            progress(
                SonyImportProgress(
                    "inventory",
                    "Selected new Osmo Nano originals",
                    completed_items=len(selected),
                    total_items=len(camera_media),
                )
            )

            root = self._dump_ui(serial)
            self._tap_download_action(serial, root, expected_count=len(selected))
            # Mimo keeps selection mode open and animates a transfer banner for
            # multi-file downloads. During that animation uiautomator cannot reach
            # an idle state, so only the appearance of exact exported files below
            # is used as the acceptance/completion signal.
            selection_active = False
        finally:
            if selection_active:
                try:
                    current = self._dump_ui(serial, attempts=1)
                    cancel = self._find_resource(
                        current,
                        "dji.mimo:id/image_cancel_multiple_select",
                    )
                    if cancel is not None:
                        self._tap(serial, current, cancel)
                except SonyCameraImportError:
                    pass

        deadline = self._clock() + self._transfer_timeout
        while self._clock() < deadline:
            remote = self._list_phone_media(serial)
            downloaded = [
                media
                for media in selected
                if any(
                    camera_media_matches_download(media, item.name, item.size) for item in remote
                )
            ]
            progress(
                SonyImportProgress(
                    "transferring",
                    f"Downloading {len(selected)} Osmo Nano original(s)",
                    completed_items=len(downloaded),
                    total_items=len(selected),
                    bytes_on_phone=sum(item.size for item in remote),
                )
            )
            if len(downloaded) == len(selected):
                return
            self._sleep(4)
        raise DjiCameraImportError(
            "DJI_TRANSFER_TIMEOUT",
            "DJI Mimo did not finish the camera transfer within two hours.",
        )

    def _copy_and_verify(
        self,
        serial: str,
        progress: Callable[[SonyImportProgress], None],
    ) -> SonyImportResult:
        self.destination.mkdir(parents=True, exist_ok=True)
        remote_files = self._list_phone_media(serial)
        copied = 0
        skipped = 0
        copied_bytes = 0
        total_bytes = sum(item.size for item in remote_files)
        manifest_files: list[dict[str, object]] = []
        for index, remote in enumerate(remote_files, start=1):
            expected_hash = self._remote_hash(serial, remote.path)
            target = self.destination / remote.name
            if target.exists() and not self._matches_remote(target, remote, expected_hash):
                target = self._collision_target(target, remote, expected_hash)
            if self._matches_remote(target, remote, expected_hash):
                skipped += 1
            else:
                part = target.with_name(f".{target.name}.cit-part")
                part.unlink(missing_ok=True)
                try:
                    self._adb(
                        serial,
                        "pull",
                        "-a",
                        remote.path,
                        str(part),
                        timeout=max(120, remote.size / 2_000_000),
                    )
                    if part.stat().st_size != remote.size or self._hash_file(part) != expected_hash:
                        raise DjiCameraImportError(
                            "DJI_PC_VERIFICATION_FAILED",
                            f"Checksum verification failed for {remote.name}.",
                        )
                    os.replace(part, target)
                finally:
                    part.unlink(missing_ok=True)
                copied += 1
                copied_bytes += remote.size
            manifest_files.append(
                {
                    "name": target.name,
                    "sourcePath": remote.path,
                    "sizeBytes": remote.size,
                    "sha256": expected_hash,
                }
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

        summary = {
            "schemaVersion": "1.0",
            "camera": "DJI Osmo Nano",
            "source": "DJI Mimo over USB/ADB",
            "verified": True,
            "cameraFilesDeleted": False,
            "phoneFilesDeleted": False,
            "fileCount": len(remote_files),
            "totalBytes": total_bytes,
            "files": manifest_files,
        }
        summary_path = self.destination / "dji-osmo-nano-import-summary.json"
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

    def _remote_hash(self, serial: str, remote_path: str) -> str:
        output = self._shell(
            serial,
            f"sha256sum -- {shlex.quote(remote_path)}",
            timeout=7_200,
        )
        digest = output.strip().split(maxsplit=1)[0].casefold()
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise DjiCameraImportError(
                "DJI_PHONE_HASH_FAILED",
                f"The phone could not hash {PurePosixPath(remote_path).name}.",
            )
        return digest

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _matches_remote(
        cls,
        path: Path,
        remote: DjiRemoteFile,
        expected_hash: str,
    ) -> bool:
        return (
            path.is_file()
            and path.stat().st_size == remote.size
            and cls._hash_file(path) == expected_hash
        )

    def _collision_target(
        self,
        original: Path,
        remote: DjiRemoteFile,
        expected_hash: str,
    ) -> Path:
        suffix = expected_hash[:8]
        candidate = original.with_name(f"{original.stem}__{suffix}{original.suffix}")
        index = 2
        while candidate.exists() and not self._matches_remote(
            candidate,
            remote,
            expected_hash,
        ):
            candidate = original.with_name(f"{original.stem}__{suffix}_{index}{original.suffix}")
            index += 1
        return candidate
