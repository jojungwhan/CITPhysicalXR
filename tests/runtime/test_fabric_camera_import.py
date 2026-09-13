from __future__ import annotations

import asyncio
import hashlib
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from cit_runtime.dji_camera_import import (
    AdbDjiCameraImporter,
    DjiCameraImportError,
    DjiCameraSetupRequired,
    DjiRemoteFile,
    camera_media_matches_download,
    dji_download_action_center,
    match_dji_playback_media,
    parse_dji_camera_cache_listing,
    parse_dji_remote_listing,
)
from cit_runtime.fabric_auth import FABRIC_PERMISSIONS, FabricBootstrapIdentity
from cit_runtime.fabric_camera import CameraImportState, SonyCameraImportService
from cit_runtime.fabric_service import create_fabric_app
from cit_runtime.sony_camera_import import (
    AdbSonyCameraImporter,
    BatteryReading,
    SonyCameraBatteryLow,
    SonyCameraImportError,
    SonyCameraSetupRequired,
    SonyImportProgress,
    SonyImportResult,
    SonyPhoneProbe,
    _GridItem,
    battery_condition,
    bounds_center,
    parse_adb_devices,
    parse_android_battery,
    parse_camera_battery_ui,
    parse_display_size,
    parse_remote_listing,
    parse_sha256_lines,
)
from fastapi.testclient import TestClient

NOW = datetime(2026, 9, 9, 10, 30, tzinfo=UTC)
ADMIN_TOKEN = "cit-camera-admin-" + "a" * 40
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


class FakeImporter:
    def __init__(
        self,
        destination: Path,
        *,
        result: SonyImportResult | None = None,
        error: Exception | None = None,
        phone_battery: BatteryReading | None = None,
    ) -> None:
        self.destination = destination
        self.result = result or SonyImportResult(2, 22, 24, 3_000, 2_260_951_681)
        self.error = error
        self.phone_battery = phone_battery or BatteryReading(70, True)
        self.import_calls = 0

    def probe(self) -> SonyPhoneProbe:
        return SonyPhoneProbe(
            phone_connected=True,
            phone_model="SM-N971N",
            app_installed=True,
            bluetooth_enabled=True,
            phone_battery=self.phone_battery,
            files_on_phone=24,
            bytes_on_phone=2_260_951_681,
        )

    def import_all(
        self,
        progress: Callable[[SonyImportProgress], None],
    ) -> SonyImportResult:
        self.import_calls += 1
        progress(SonyImportProgress("inventory", "Checking camera media"))
        progress(SonyImportProgress("copying", "Copying originals", 1, 2))
        if self.error is not None:
            raise self.error
        progress(SonyImportProgress("verifying", "Verifying originals", 2, 2))
        return self.result


class LockedPhoneRunner:
    def __call__(
        self,
        command: Sequence[str],
        *,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        arguments = tuple(command)
        output = ""
        if arguments[-1:] == ("devices",):
            output = "List of devices attached\nPHONE-1\tdevice\n"
        elif "pm" in arguments and "path" in arguments:
            output = "package:/data/app/com.sony.playmemories.mobile/base.apk\n"
        elif "stay_on_while_plugged_in" in arguments:
            output = "2\n"
        elif "packages" in arguments and "-e" in arguments:
            output = "package:com.samsung.android.service.aircommand\n"
        elif arguments[-1:] == ("cat '/sdcard/cit-sony-camera-ui.xml'",):
            output = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<hierarchy rotation="0">'
                '<node package="com.android.systemui" text="잠금해제 패턴을 그리세요" '
                'content-desc="기기 잠김" bounds="[0,0][1080,2280]" />'
                "</hierarchy>"
            )
        return subprocess.CompletedProcess(arguments, 0, output, "")


class DjiCopyRunner:
    remote_path = "/sdcard/DCIM/DJI Album/DJI_20260909_001.MP4"

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.commands: list[tuple[str, ...]] = []

    def __call__(
        self,
        command: Sequence[str],
        *,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        arguments = tuple(command)
        self.commands.append(arguments)
        output = ""
        if "pull" in arguments:
            Path(arguments[-1]).write_bytes(self.payload)
        elif arguments[-1].startswith("for root in "):
            output = f"{len(self.payload)}|{self.remote_path}\n"
        elif arguments[-1].startswith("sha256sum -- "):
            output = f"{hashlib.sha256(self.payload).hexdigest()}  {self.remote_path}\n"
        return subprocess.CompletedProcess(arguments, 0, output, "")


def test_adb_and_media_output_parsers() -> None:
    devices = "List of devices attached\nR3CMB0ANZYT\tdevice\n"
    listing = "\n".join(
        (
            "-rw-rw---- 1 1023 1023 150 2026-09-09 10:01 DSC00001.JPG",
            "-rw-rw---- 1 1023 1023 900 2026-09-09 10:02 C0001.MP4",
            "-rw-rw---- 1 1023 1023 20 2026-09-09 10:03 .pending-C0002.MP4",
            "-rw-rw---- 1 1023 1023 10 2026-09-09 10:04 notes.txt",
        )
    )
    digest = "a" * 64

    assert parse_adb_devices(devices) == "R3CMB0ANZYT"
    assert [(item.name, item.size) for item in parse_remote_listing(listing)] == [
        ("C0001.MP4", 900),
        ("DSC00001.JPG", 150),
    ]
    assert parse_sha256_lines(f"{digest}  DSC00001.JPG\n") == {"DSC00001.JPG": digest}
    assert bounds_center("[10,20][30,60]") == (20, 40)
    assert parse_display_size("Physical size: 1440x3040\nOverride size: 1080x2280") == (
        1080,
        2280,
    )


def test_battery_parsers_classify_phone_and_camera_preflight() -> None:
    phone = parse_android_battery(
        """
        AC powered: false
        USB powered: true
        Wireless powered: false
        status: 2
        level: 70
        scale: 100
        """
    )
    low_phone = parse_android_battery(
        """
        AC powered: false
        USB powered: false
        Wireless powered: false
        status: 3
        level: 19
        scale: 100
        """
    )
    camera_ui = ET.fromstring(
        """
        <hierarchy>
          <node package="com.android.systemui" resource-id="battery" text="4%" />
          <node package="dji.mimo" resource-id="dji.mimo:id/camera_battery"
                content-desc="Camera battery 18%" />
        </hierarchy>
        """
    )

    assert phone == BatteryReading(70, True)
    assert battery_condition(phone) == "ok"
    assert low_phone == BatteryReading(19, False)
    assert battery_condition(low_phone) == "blocked"
    assert battery_condition(BatteryReading(19, True)) == "warning"
    assert battery_condition(BatteryReading(29, False)) == "warning"
    assert parse_camera_battery_ui(camera_ui, package="dji.mimo") == BatteryReading(18, False)


@pytest.mark.asyncio
async def test_low_phone_battery_defers_before_import_task(tmp_path: Path) -> None:
    importer = FakeImporter(
        tmp_path / "imports",
        phone_battery=BatteryReading(19, False),
    )
    service = SonyCameraImportService(importer)

    with pytest.raises(SonyCameraBatteryLow) as raised:
        await service.start_import()
    snapshot = await service.snapshot(refresh=False)

    assert raised.value.code == "SONY_PHONE_BATTERY_LOW"
    assert importer.import_calls == 0
    assert snapshot.state is CameraImportState.DEFERRED
    assert snapshot.phoneBattery.levelPercent == 19
    assert snapshot.phoneBattery.condition == "blocked"
    assert snapshot.operations.startImport is False


@pytest.mark.asyncio
async def test_low_camera_battery_is_retryable_and_exposed(tmp_path: Path) -> None:
    importer = FakeImporter(
        tmp_path / "imports",
        error=SonyCameraBatteryLow(
            "SONY_CAMERA_BATTERY_LOW",
            "Sony camera battery is low.",
            device="camera",
            battery=BatteryReading(12, False),
        ),
    )
    service = SonyCameraImportService(importer)

    await service.start_import()
    snapshot = await service.wait_until_idle()

    assert snapshot.state is CameraImportState.DEFERRED
    assert snapshot.cameraBattery.levelPercent == 12
    assert snapshot.cameraBattery.condition == "blocked"
    assert snapshot.operations.startImport is True


def test_dji_phone_listing_keeps_originals_inside_mimo_directories() -> None:
    listing = "\n".join(
        (
            "900|/sdcard/DCIM/DJI Album/DJI_20260909_001.MP4",
            "150|/sdcard/DCIM/DJI Export/DJI_20260909_002.JPG",
            (
                "250|/sdcard/Android/data/dji.mimo/files/DCIM/"
                "OriginalFiles/Video/DJI_20260909_003.MP4"
            ),
            "20|/sdcard/DCIM/DJI Album/DJI_20260909_001.LRF",
            "10|/sdcard/DCIM/DJI Album/../private.JPG",
            "40|/sdcard/Download/DJI_20260909_003.MP4",
        )
    )

    assert [(item.name, item.size) for item in parse_dji_remote_listing(listing)] == [
        ("DJI_20260909_001.MP4", 900),
        ("DJI_20260909_002.JPG", 150),
        ("DJI_20260909_003.MP4", 250),
    ]


def test_dji_camera_cache_recovers_stable_media_identity() -> None:
    listing = "\n".join(
        (
            ".nomedia",
            (
                "Video_1074793728_DJI_20260902211733_0052_D_MP4_"
                "111852870_15000_202692211732_photo_preview.jpg"
            ),
            (
                "Video_1074794048_DJI_20260909074045_0057_D_MP4_"
                "10406985745_2634000_20269974044_photo_preview.jpg"
            ),
            "unrelated_preview.jpg",
        )
    )

    media = parse_dji_camera_cache_listing(listing)

    assert [item.name for item in media] == [
        "DJI_20260902211733_0052_D.MP4",
        "DJI_20260909074045_0057_D.MP4",
    ]
    assert media[0].sequence == "0052"
    assert media[0].size == 111_852_870
    assert media[0].duration_seconds == 15
    assert media[0].captured_at == datetime(2026, 9, 2, 21, 17, 33)
    assert media[1].duration_seconds == 2_634


def test_dji_export_name_is_matched_to_its_camera_identity() -> None:
    media = parse_dji_camera_cache_listing(
        "Video_1074793728_DJI_20260902211733_0052_D_MP4_"
        "111852870_15000_202692211732_photo_preview.jpg"
    )[0]

    assert camera_media_matches_download(
        media,
        "dji_mimo_20260902_211732_0052_1788933004308_timelapse.mp4",
        111_852_870,
    )
    assert not camera_media_matches_download(
        media,
        "dji_mimo_20260902_211732_0053_1788933004308_timelapse.mp4",
        111_852_870,
    )
    assert not camera_media_matches_download(
        media,
        "dji_mimo_20260902_211732_0052_1788933004308_timelapse.mp4",
        111_852_871,
    )


def test_dji_live_playback_grid_maps_korean_dates_and_durations(tmp_path: Path) -> None:
    root = ET.fromstring(
        """
        <hierarchy rotation="0">
          <node resource-id="dji.mimo:id/playback_main_recycler" bounds="[0,0][1080,2064]">
            <node clickable="true" bounds="[3,396][1077,506]">
              <node resource-id="dji.mimo:id/text_title" text="오늘" />
            </node>
            <node clickable="true" bounds="[3,512][357,866]">
              <node resource-id="dji.mimo:id/v2_hg_childitem_img" />
              <node resource-id="dji.mimo:id/v2_hg_childitem_time" text="43:54" />
            </node>
            <node clickable="true" bounds="[3,872][1077,982]">
              <node resource-id="dji.mimo:id/text_title" text="어제" />
            </node>
            <node clickable="true" bounds="[3,988][357,1342]">
              <node resource-id="dji.mimo:id/v2_hg_childitem_img" />
              <node resource-id="dji.mimo:id/v2_hg_childitem_time" text="37:09" />
            </node>
            <node clickable="true" bounds="[3,1348][1077,1458]">
              <node resource-id="dji.mimo:id/text_title" text="09-07" />
            </node>
            <node clickable="true" bounds="[3,1464][357,1818]">
              <node resource-id="dji.mimo:id/v2_hg_childitem_img" />
              <node resource-id="dji.mimo:id/v2_hg_childitem_time" text="00:44" />
            </node>
          </node>
        </hierarchy>
        """
    )
    importer = AdbDjiCameraImporter(tmp_path / "imports")

    items = importer._playback_items(root, date(2026, 9, 9))

    assert [
        (item.capture_date.isoformat(), item.duration_seconds, item.node.attrib["bounds"])
        for item in items
    ] == [
        ("2026-09-09", 2_634, "[3,512][357,866]"),
        ("2026-09-08", 2_229, "[3,988][357,1342]"),
        ("2026-09-07", 44, "[3,1464][357,1818]"),
    ]

    camera_media = parse_dji_camera_cache_listing(
        "\n".join(
            (
                "Video_1_DJI_20260907144154_0054_D_MP4_194709137_"
                "44000_202697144154_photo_preview.jpg",
                "Video_2_DJI_20260908075433_0056_D_MP4_9272689274_"
                "2229000_20269875432_photo_preview.jpg",
                "Video_3_DJI_20260909074045_0057_D_MP4_10406985745_"
                "2634000_20269974044_photo_preview.jpg",
            )
        )
    )
    matches = match_dji_playback_media(camera_media, items)
    assert [(media.sequence, item.duration_seconds) for media, item in matches] == [
        ("0057", 2_634),
        ("0056", 2_229),
        ("0054", 44),
    ]


def test_dji_playback_accepts_icon_only_multiple_select(tmp_path: Path) -> None:
    root = ET.fromstring(
        '<hierarchy rotation="0"><node resource-id="dji.mimo:id/image_multiple_select" '
        'clickable="true" bounds="[943,150][1027,234]" /></hierarchy>'
    )
    importer = AdbDjiCameraImporter(tmp_path / "imports")

    assert importer._open_playback("PHONE-1", root) is root


def test_dji_playback_closes_completed_zero_file_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_root = ET.fromstring(
        """
        <hierarchy rotation="0">
          <node resource-id="dji.mimo:id/tv_select_message" text="0파일선택" />
          <node resource-id="dji.mimo:id/image_cancel_multiple_select" text="취소"
                clickable="true" bounds="[869,157][1027,231]" />
        </hierarchy>
        """
    )
    playback_root = ET.fromstring(
        '<hierarchy rotation="0"><node resource-id="dji.mimo:id/image_multiple_select" '
        'clickable="true" bounds="[943,150][1027,234]" /></hierarchy>'
    )
    importer = AdbDjiCameraImporter(tmp_path / "imports", sleeper=lambda _seconds: None)
    tapped: list[str] = []
    monkeypatch.setattr(
        importer,
        "_tap",
        lambda _serial, _root, node: tapped.append(node.attrib["resource-id"]),
    )
    monkeypatch.setattr(importer, "_dump_ui", lambda _serial: playback_root)

    assert importer._open_playback("PHONE-1", selected_root) is playback_root
    assert tapped == ["dji.mimo:id/image_cancel_multiple_select"]


def test_dji_resource_only_album_is_recognized_as_connected() -> None:
    root = ET.fromstring(
        """
        <hierarchy rotation="0">
          <node resource-id="dji.mimo:id/playback_main_recycler" />
          <node resource-id="dji.mimo:id/tv_title_playback" text="장치" selected="true" />
          <node resource-id="dji.mimo:id/tv_title_gallery" text="로컬" />
        </hierarchy>
        """
    )

    assert AdbDjiCameraImporter._connected_ui(root, "OsmoNano-5A76")


def test_dji_download_action_uses_guarded_middle_action() -> None:
    assert dji_download_action_center(1080, 2280) == (540, 2109)


def test_dji_download_tap_requires_exact_guard_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    importer = AdbDjiCameraImporter(tmp_path / "imports")
    root = ET.fromstring(
        """
        <hierarchy rotation="0">
          <node resource-id="dji.mimo:id/tv_select_message" text="1파일선택" />
        </hierarchy>
        """
    )
    commands: list[tuple[str, ...]] = []

    def fake_adb(_serial: str, *arguments: str, **_kwargs: object) -> str:
        commands.append(arguments)
        if arguments[:3] == ("shell", "dumpsys", "package"):
            return "versionCode=241754\nversionName=2.11.9\n"
        if arguments[:3] == ("shell", "dumpsys", "window"):
            return "mCurrentFocus=Window{1 u0 dji.mimo/dji.lomo.main.activity.MainActivity}\n"
        if arguments[:3] == ("shell", "wm", "size"):
            return "Physical size: 1080x2280\n"
        return ""

    monkeypatch.setattr(importer, "_adb", fake_adb)

    importer._tap_download_action("PHONE-1", root, expected_count=1)

    assert commands[-1] == (
        "shell",
        "input",
        "touchscreen",
        "tap",
        "540",
        "2109",
    )


def test_dji_download_tap_refuses_selection_count_mismatch(tmp_path: Path) -> None:
    importer = AdbDjiCameraImporter(tmp_path / "imports")
    root = ET.fromstring(
        '<hierarchy rotation="0"><node resource-id="dji.mimo:id/tv_select_message" '
        'text="2 files selected" /></hierarchy>'
    )

    with pytest.raises(DjiCameraImportError, match="selection changed"):
        importer._tap_download_action("PHONE-1", root, expected_count=1)


def test_dji_download_selects_missing_identity_and_waits_for_renamed_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    importer = AdbDjiCameraImporter(
        tmp_path / "imports",
        sleeper=lambda _seconds: None,
    )
    media = parse_dji_camera_cache_listing(
        "Video_1074793728_DJI_20260902211733_0052_D_MP4_"
        "111852870_15000_202692211732_photo_preview.jpg"
    )[0]

    def screen(*, selection_count: int | None) -> ET.Element:
        selection = (
            ""
            if selection_count is None
            else (
                '<node resource-id="dji.mimo:id/tv_select_message" '
                f'text="{selection_count}파일선택" />'
            )
        )
        return ET.fromstring(
            f"""
            <hierarchy rotation="0">
              <node resource-id="dji.mimo:id/image_multiple_select" clickable="true"
                    bounds="[943,150][1027,234]" />
              {selection}
              <node resource-id="dji.mimo:id/playback_main_recycler"
                    bounds="[0,0][1080,2064]">
                <node clickable="true" bounds="[3,1824][1077,1934]">
                  <node resource-id="dji.mimo:id/text_title" text="09-02" />
                </node>
                <node clickable="true" bounds="[3,1940][357,2064]">
                  <node resource-id="dji.mimo:id/v2_hg_childitem_img" />
                  <node resource-id="dji.mimo:id/v2_hg_childitem_time" text="00:15" />
                </node>
              </node>
            </hierarchy>
            """
        )

    # Mimo's animated transfer banner prevents uiautomator from reaching an idle
    # state. A successful importer must not require another UI dump after the
    # guarded download tap; the exported file is the acceptance signal.
    screens = iter((screen(selection_count=0), screen(selection_count=1)))
    downloaded = False
    taps: list[str] = []

    def list_phone_media(_serial: str) -> list[DjiRemoteFile]:
        if not downloaded:
            return []
        return [
            DjiRemoteFile(
                path=(
                    "/sdcard/DCIM/DJI Album/"
                    "dji_mimo_20260902_211732_0052_1788933004308_timelapse.mp4"
                ),
                name="dji_mimo_20260902_211732_0052_1788933004308_timelapse.mp4",
                size=111_852_870,
            )
        ]

    def tap(_serial: str, _root: ET.Element, node: ET.Element) -> None:
        taps.append(node.attrib.get("resource-id", node.attrib.get("bounds", "")))

    def tap_download(
        _serial: str,
        _root: ET.Element,
        *,
        expected_count: int,
    ) -> None:
        nonlocal downloaded
        assert expected_count == 1
        downloaded = True

    monkeypatch.setattr(importer, "_list_camera_media", lambda _serial: [media])
    monkeypatch.setattr(importer, "_list_phone_media", list_phone_media)
    monkeypatch.setattr(importer, "_phone_today", lambda _serial: date(2026, 9, 9))
    monkeypatch.setattr(importer, "_dump_ui", lambda _serial, **_kwargs: next(screens))
    monkeypatch.setattr(importer, "_tap", tap)
    monkeypatch.setattr(importer, "_tap_download_action", tap_download)

    importer._download_missing_camera_items("PHONE-1", screen(selection_count=None), lambda _: None)

    assert taps == ["dji.mimo:id/image_multiple_select", "[3,1940][357,2064]"]


@pytest.mark.parametrize(
    "screen",
    (
        (
            '<node package="dji.mimo" text="Agree and Continue" bounds="[0,0][1,1]" />'
            '<node package="dji.mimo" text="Read the User Agreement and Privacy Policy" '
            'bounds="[0,0][1,1]" />'
        ),
        (
            '<node package="dji.mimo" text="AGREE" bounds="[0,0][1,1]" />'
            '<node package="dji.mimo" text="Terms of Use" bounds="[0,0][1,1]" />'
        ),
        (
            '<node package="com.android.permissioncontroller" text="Allow DJI Mimo" '
            'bounds="[0,0][1,1]" />'
        ),
        (
            '<node package="dji.mimo" text="DJI Mimo would like to access mobile '
            'device storage" bounds="[0,0][1,1]" />'
        ),
    ),
)
def test_dji_import_never_accepts_consent_or_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    screen: str,
) -> None:
    importer = AdbDjiCameraImporter(tmp_path / "imports", sleeper=lambda _seconds: None)
    root = ET.fromstring(f'<hierarchy rotation="0">{screen}</hierarchy>')
    monkeypatch.setattr(importer, "_adb", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(importer, "_dump_ui", lambda *_args, **_kwargs: root)

    with pytest.raises(DjiCameraSetupRequired):
        importer._open_mimo("PHONE-1")


def test_dji_low_camera_battery_defers_before_media_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    importer = AdbDjiCameraImporter(tmp_path / "imports", sleeper=lambda _seconds: None)
    connected = ET.fromstring(
        """
        <hierarchy rotation="0">
          <node package="dji.mimo" resource-id="dji.mimo:id/camera_battery"
                content-desc="Camera battery 12%" />
        </hierarchy>
        """
    )
    opened_playback = False

    def fake_adb(_serial: str, *args: str, **_kwargs: object) -> str:
        if args == ("shell", "dumpsys", "battery"):
            return "status: 2\nlevel: 70\nscale: 100\nUSB powered: true\n"
        if "stay_on_while_plugged_in" in args:
            return "2"
        return ""

    def open_playback(_serial: str, _root: ET.Element) -> ET.Element:
        nonlocal opened_playback
        opened_playback = True
        return connected

    monkeypatch.setattr(importer, "_resolve_serial", lambda: "PHONE-1")
    monkeypatch.setattr(importer, "_package_installed", lambda _serial: True)
    monkeypatch.setattr(importer, "_adb", fake_adb)
    monkeypatch.setattr(importer, "_open_mimo", lambda _serial: connected)
    monkeypatch.setattr(
        importer,
        "_ensure_camera_connection",
        lambda _serial, _root, _progress: connected,
    )
    monkeypatch.setattr(importer, "_open_playback", open_playback)

    with pytest.raises(SonyCameraBatteryLow) as raised:
        importer.import_all(lambda _progress: None)

    assert raised.value.code == "DJI_CAMERA_BATTERY_LOW"
    assert raised.value.device == "camera"
    assert opened_playback is False


def test_dji_pc_copy_is_verified_append_only_and_collision_safe(tmp_path: Path) -> None:
    runner = DjiCopyRunner(b"first original")
    destination = tmp_path / "imports"
    importer = AdbDjiCameraImporter(destination, process_runner=runner)

    first = importer._copy_and_verify("PHONE-1", lambda _progress: None)
    runner.payload = b"other original"
    second = importer._copy_and_verify("PHONE-1", lambda _progress: None)

    first_path = destination / "DJI_20260909_001.MP4"
    collision_hash = hashlib.sha256(runner.payload).hexdigest()[:8]
    collision_path = destination / f"DJI_20260909_001__{collision_hash}.MP4"
    assert first.copied_files == 1
    assert second.copied_files == 1
    assert first_path.read_bytes() == b"first original"
    assert collision_path.read_bytes() == b"other original"
    assert not any(
        token in {"rm", "delete", "unlink"} for command in runner.commands for token in command
    )


def test_locked_companion_reports_one_time_setup_instead_of_navigation_failure(
    tmp_path: Path,
) -> None:
    importer = AdbSonyCameraImporter(
        tmp_path / "imports",
        process_runner=LockedPhoneRunner(),
        sleeper=lambda _seconds: None,
    )

    with pytest.raises(SonyCameraSetupRequired) as raised:
        importer.import_all(lambda _progress: None)

    assert raised.value.code == "SONY_PHONE_UNLOCK_REQUIRED"


def test_sony_app_restarts_when_resumed_remote_power_ui_cannot_be_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    importer = AdbSonyCameraImporter(
        tmp_path / "imports",
        sleeper=lambda _seconds: None,
    )
    camera_list = ET.fromstring(
        '<hierarchy><node package="com.sony.playmemories.mobile" text="ZV-E10" /></hierarchy>'
    )
    screens: list[ET.Element | SonyCameraImportError] = [
        SonyCameraImportError(
            "SONY_PHONE_UI_UNAVAILABLE",
            "The resumed Remote Power screen cannot be inspected.",
        ),
        camera_list,
    ]
    commands: list[tuple[str, ...]] = []

    def dump_ui(_serial: str) -> ET.Element:
        screen = screens.pop(0)
        if isinstance(screen, SonyCameraImportError):
            raise screen
        return screen

    def adb(_serial: str, *arguments: str, **_kwargs: object) -> str:
        commands.append(arguments)
        return ""

    monkeypatch.setattr(importer, "_dump_ui", dump_ui)
    monkeypatch.setattr(importer, "_adb", adb)

    assert importer._open_sony_app("PHONE-1") is camera_list
    assert (
        commands.count(
            (
                "shell",
                "monkey",
                "-p",
                "com.sony.playmemories.mobile",
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            )
        )
        == 2
    )
    assert ("shell", "am", "force-stop", "com.sony.playmemories.mobile") in commands


def test_sony_wait_accepts_only_the_exact_camera_wifi_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    importer = AdbSonyCameraImporter(
        tmp_path / "imports",
        sleeper=lambda _seconds: None,
    )
    request = ET.fromstring(
        """
        <hierarchy>
          <node package="com.android.settings" text="기기에 연결할까요?" />
          <node package="com.android.settings" text="DIRECT-omE1:ZV-E10" />
          <node package="com.android.settings" text="연결" clickable="true"
                bounds="[541,1954][990,2049]" />
        </hierarchy>
        """
    )
    connected = ET.fromstring(
        """
        <hierarchy>
          <node package="com.sony.playmemories.mobile"
                text="카메라 내 이미지 가져오기" />
        </hierarchy>
        """
    )
    activities = iter(
        (
            "com.android.settings/.wifi.NetworkRequestDialogActivity",
            "com.sony.playmemories.mobile/.selectfunction.SelectFunctionActivity",
        )
    )
    screens = iter((request, connected))
    tapped: list[str] = []

    monkeypatch.setattr(importer, "_activity_state", lambda _serial: next(activities))
    monkeypatch.setattr(importer, "_wifi_ssid", lambda _serial: "DIRECT-omE1:ZV-E10")
    monkeypatch.setattr(importer, "_dump_ui", lambda _serial, **_kwargs: next(screens))
    monkeypatch.setattr(
        importer,
        "_tap",
        lambda _serial, _root, node: tapped.append(node.attrib["text"]),
    )

    assert importer._wait_for_connection("PHONE-1", 1) is connected
    assert tapped == ["연결"]

    unrelated = ET.fromstring(
        """
        <hierarchy>
          <node package="other.app" text="기기에 연결할까요?" />
          <node package="other.app" text="DIRECT-omE1:ZV-E10" />
          <node package="other.app" text="연결" />
        </hierarchy>
        """
    )
    assert importer._accept_camera_wifi_request("PHONE-1", unrelated) is False


def test_sony_activity_state_uses_only_the_resumed_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    importer = AdbSonyCameraImporter(tmp_path / "imports")
    activities = (
        "Hist #1: com.sony.playmemories.mobile/.bluetooth.poweronoff.PowerOnOffActivity\n"
        "Hist #0: com.sony.playmemories.mobile/.devicelist.WiFiActivity\n"
        "mResumedActivity: ActivityRecord{abc u0 "
        "com.sony.playmemories.mobile/.selectfunction.SelectFunctionActivity t12}\n"
    )
    monkeypatch.setattr(importer, "_adb", lambda *_args, **_kwargs: activities)

    resumed = importer._activity_state("PHONE-1")

    assert "mResumedActivity:" in resumed
    assert "SelectFunctionActivity" in resumed
    assert "PowerOnOffActivity" not in resumed
    assert "WiFiActivity" not in resumed


def test_sony_remote_power_tap_is_activity_and_display_guarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    importer = AdbSonyCameraImporter(
        tmp_path / "imports",
        sleeper=lambda _seconds: None,
    )
    commands: list[tuple[str, ...]] = []

    def adb(_serial: str, *arguments: str, **_kwargs: object) -> str:
        commands.append(arguments)
        if arguments == ("shell", "wm", "size"):
            return "Physical size: 1080x2280\n"
        return ""

    monkeypatch.setattr(
        importer,
        "_activity_state",
        lambda _serial: "com.sony.playmemories.mobile/.bluetooth.poweronoff.PowerOnOffActivity",
    )
    monkeypatch.setattr(importer, "_adb", adb)

    importer._tap_remote_power_camera("PHONE-1")

    assert commands[-1] == (
        "shell",
        "input",
        "touchscreen",
        "tap",
        "984",
        "318",
    )


@pytest.mark.parametrize(
    ("content_type", "known_names", "expected"),
    (
        ("JPEG", {"dsc00001.jpg"}, True),
        ("JPEG", {"dsc00001.jpeg"}, True),
        ("HEIF", {"dsc00001.heic"}, True),
        ("RAW", {"dsc00001.arw"}, True),
        ("RAW+JPEG", {"dsc00001.arw", "dsc00001.jpeg"}, True),
        ("RAW+JPEG", {"dsc00001.arw"}, False),
        ("XAVC S", {"c0001.mp4"}, True),
        ("XAVC S", {"c0002.mp4"}, False),
        ("unknown", {"dsc00001.jpg"}, False),
    ),
)
def test_grid_item_deduplication_accepts_extension_alternatives(
    content_type: str,
    known_names: set[str],
    expected: bool,
) -> None:
    stem = "C0001" if "xavc" in content_type.casefold() else "DSC00001"
    item = _GridItem(
        key="2026-09-09|item",
        stem=stem,
        content_type=content_type,
        checkbox=ET.Element("node"),
    )

    assert AdbSonyCameraImporter._grid_item_is_known(item, known_names) is expected


@pytest.mark.asyncio
async def test_background_import_completes_with_verified_result(tmp_path: Path) -> None:
    importer = FakeImporter(tmp_path / "imports")
    service = SonyCameraImportService(importer, clock=lambda: NOW)

    ready = await service.snapshot()
    started = await service.start_import()
    completed = await service.wait_until_idle()

    assert ready.state is CameraImportState.READY
    assert started.accepted is True
    assert completed.state is CameraImportState.COMPLETED
    assert completed.lastResult is not None
    assert completed.lastResult.verifiedFiles == 24
    assert completed.lastResult.completedAt == NOW
    assert completed.operations.startImport is True
    assert importer.import_calls == 1


@pytest.mark.asyncio
async def test_destination_opener_receives_only_configured_directory(tmp_path: Path) -> None:
    importer = FakeImporter(tmp_path / "imports")
    opened: list[Path] = []
    service = SonyCameraImportService(importer, directory_opener=opened.append)

    result = await service.open_destination()

    assert result.opened is True
    assert result.destination == str(importer.destination)
    assert opened == [importer.destination]


@pytest.mark.asyncio
async def test_pairing_requirement_is_exposed_as_setup_state(tmp_path: Path) -> None:
    importer = FakeImporter(
        tmp_path / "imports",
        error=SonyCameraSetupRequired("PAIR_ONCE", "Pair the camera once."),
    )
    service = SonyCameraImportService(importer)

    await service.start_import()
    snapshot = await service.wait_until_idle()

    assert snapshot.state is CameraImportState.SETUP_REQUIRED
    assert snapshot.setupRequired is True
    assert snapshot.errorCode == "PAIR_ONCE"
    assert snapshot.operations.startImport is True


@pytest.mark.asyncio
async def test_camera_work_restores_an_open_android_controller_on_completion(
    tmp_path: Path,
) -> None:
    importer = FakeImporter(
        tmp_path / "imports",
        error=SonyCameraSetupRequired("PAIR_ONCE", "Pair the camera once."),
    )
    restored = 0

    async def restore_controller() -> None:
        nonlocal restored
        restored += 1

    service = SonyCameraImportService(importer, after_import=restore_controller)

    await service.start_import()
    snapshot = await service.wait_until_idle()

    assert snapshot.state is CameraImportState.SETUP_REQUIRED
    assert restored == 1


@pytest.mark.asyncio
async def test_periodic_import_runs_without_a_button_press(tmp_path: Path) -> None:
    importer = FakeImporter(tmp_path / "imports")
    service = SonyCameraImportService(
        importer,
        automatic_interval=3_600,
        automatic_initial_delay=0.01,
    )

    await service.start_automatic_imports()
    try:
        for _ in range(100):
            if importer.import_calls:
                break
            await asyncio.sleep(0.01)
        completed = await service.wait_until_idle()
    finally:
        await service.stop_automatic_imports()

    assert importer.import_calls == 1
    assert completed.state is CameraImportState.COMPLETED
    assert completed.automaticEnabled is True
    assert completed.automaticIntervalSeconds == 3_600
    assert completed.lastAutomaticAttemptAt is not None


def test_camera_import_api_starts_and_audits(tmp_path: Path) -> None:
    importer = FakeImporter(tmp_path / "imports")
    opened: list[Path] = []
    camera = SonyCameraImportService(
        importer,
        clock=lambda: NOW,
        directory_opener=opened.append,
    )
    identity = FabricBootstrapIdentity(
        identity_id="admin-camera",
        token=ADMIN_TOKEN,
        actor_type="administrator",
        roles=("administrator",),
        permissions=tuple(sorted(FABRIC_PERMISSIONS)),
    )

    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=(identity,),
            camera_import_service=camera,
            maintenance_interval=None,
        )
    ) as client:
        unauthenticated = client.get("/api/v1/fabric/camera-import")
        status = client.get("/api/v1/fabric/camera-import", headers=ADMIN_HEADERS)
        started = client.post("/api/v1/fabric/camera-import/start", headers=ADMIN_HEADERS)
        opened_response = client.post(
            "/api/v1/fabric/camera-import/open-destination",
            headers=ADMIN_HEADERS,
        )
        audit = client.get("/api/v1/fabric/audit?limit=50", headers=ADMIN_HEADERS)

    assert unauthenticated.status_code == 401
    assert status.status_code == 200
    assert status.json()["phoneModel"] == "SM-N971N"
    assert status.json()["phoneBattery"] == {
        "levelPercent": 70,
        "charging": True,
        "condition": "ok",
    }
    assert started.status_code == 200
    assert started.json()["accepted"] is True
    assert opened_response.status_code == 200
    assert opened_response.json()["opened"] is True
    assert opened == [importer.destination]
    record = next(item for item in audit.json() if item["action"] == "fabric.camera_import.start")
    assert record["actorId"] == "admin-camera"
    assert record["details"]["cameraFilesDeleted"] is False
    assert record["details"]["phoneFilesDeleted"] is False
    assert any(item["action"] == "fabric.camera_import.destination.open" for item in audit.json())


def test_camera_import_collection_targets_dji_without_changing_sony(tmp_path: Path) -> None:
    sony_importer = FakeImporter(tmp_path / "sony")
    dji_importer = FakeImporter(tmp_path / "dji")
    opened: list[Path] = []
    sony = SonyCameraImportService(sony_importer, clock=lambda: NOW)
    dji = SonyCameraImportService(
        dji_importer,
        camera_id="dji-osmo-nano-android",
        display_name="DJI Osmo Nano",
        app_display_name="DJI Mimo",
        error_prefix="DJI",
        clock=lambda: NOW,
        directory_opener=opened.append,
    )
    identity = FabricBootstrapIdentity(
        identity_id="admin-camera",
        token=ADMIN_TOKEN,
        actor_type="administrator",
        roles=("administrator",),
        permissions=tuple(sorted(FABRIC_PERMISSIONS)),
    )

    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "fabric.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=(identity,),
            camera_import_services={
                sony.camera_id: sony,
                dji.camera_id: dji,
            },
            maintenance_interval=None,
        )
    ) as client:
        statuses = client.get("/api/v1/fabric/camera-imports", headers=ADMIN_HEADERS)
        started = client.post(
            "/api/v1/fabric/camera-imports/dji-osmo-nano-android/start",
            headers=ADMIN_HEADERS,
        )
        opened_response = client.post(
            "/api/v1/fabric/camera-imports/dji-osmo-nano-android/open-destination",
            headers=ADMIN_HEADERS,
        )
        audit = client.get("/api/v1/fabric/audit?limit=50", headers=ADMIN_HEADERS)

    assert statuses.status_code == 200
    assert [item["cameraId"] for item in statuses.json()] == [
        "sony-zve10-android",
        "dji-osmo-nano-android",
    ]
    assert started.status_code == 200
    assert started.json()["snapshot"]["displayName"] == "DJI Osmo Nano"
    assert sony_importer.import_calls == 0
    assert dji_importer.import_calls == 1
    assert opened_response.status_code == 200
    assert opened == [dji_importer.destination]
    records = [item for item in audit.json() if item["resourceId"] == dji.camera_id]
    assert {item["action"] for item in records} == {
        "fabric.camera_import.start",
        "fabric.camera_import.destination.open",
    }
