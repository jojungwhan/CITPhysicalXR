"""Background services for append-only camera imports through Android."""

from __future__ import annotations

import asyncio
import os
import subprocess
import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from .sony_camera_import import (
    AdbSonyCameraImporter,
    BatteryCondition,
    BatteryReading,
    SonyCameraBatteryLow,
    SonyCameraImportError,
    SonyCameraSetupRequired,
    SonyImportProgress,
    SonyImportResult,
    SonyPhoneProbe,
    battery_condition,
    require_battery_for_sync,
)

SONY_CAMERA_ID = "sony-zve10-android"
DJI_CAMERA_ID = "dji-osmo-nano-android"


class CameraImportState(StrEnum):
    UNAVAILABLE = "unavailable"
    READY = "ready"
    DEFERRED = "deferred"
    SETUP_REQUIRED = "setup_required"
    CONNECTING = "connecting"
    INVENTORY = "inventory"
    TRANSFERRING = "transferring"
    COPYING = "copying"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


ACTIVE_CAMERA_STATES = frozenset(
    {
        CameraImportState.CONNECTING,
        CameraImportState.INVENTORY,
        CameraImportState.TRANSFERRING,
        CameraImportState.COPYING,
        CameraImportState.VERIFYING,
    }
)


class CameraImportOperations(BaseModel):
    startImport: bool
    openDestination: bool


class CameraImportProgress(BaseModel):
    stage: str
    message: str
    completedItems: int = 0
    totalItems: int | None = None
    bytesOnPhone: int = 0


class CameraImportBattery(BaseModel):
    levelPercent: int | None = None
    charging: bool | None = None
    condition: BatteryCondition = "unknown"


class CameraImportResult(BaseModel):
    copiedFiles: int
    skippedFiles: int
    verifiedFiles: int
    copiedBytes: int
    totalBytes: int
    completedAt: datetime


class CameraImportSnapshot(BaseModel):
    schemaVersion: Literal["1.0"] = "1.0"
    cameraId: str = SONY_CAMERA_ID
    displayName: str = "Sony ZV-E10"
    state: CameraImportState
    destination: str
    phoneConnected: bool
    phoneModel: str | None = None
    appInstalled: bool
    bluetoothEnabled: bool
    cameraWifiConnected: bool
    phoneBattery: CameraImportBattery = Field(default_factory=CameraImportBattery)
    cameraBattery: CameraImportBattery = Field(default_factory=CameraImportBattery)
    setupRequired: bool
    filesOnPhone: int
    bytesOnPhone: int
    automaticEnabled: bool
    automaticIntervalSeconds: int | None = None
    nextAutomaticRunAt: datetime | None = None
    lastAutomaticAttemptAt: datetime | None = None
    operations: CameraImportOperations
    progress: CameraImportProgress | None = None
    lastResult: CameraImportResult | None = None
    errorCode: str | None = None
    message: str | None = None


class CameraImportActionResult(BaseModel):
    accepted: bool
    message: str
    snapshot: CameraImportSnapshot


class CameraDestinationActionResult(BaseModel):
    opened: bool
    destination: str
    message: str


def camera_import_battery(reading: BatteryReading | None) -> CameraImportBattery:
    return CameraImportBattery(
        levelPercent=reading.level_percent if reading is not None else None,
        charging=reading.charging if reading is not None else None,
        condition=battery_condition(reading),
    )


class CameraImporter(Protocol):
    destination: Path

    def probe(self) -> SonyPhoneProbe: ...

    def import_all(
        self,
        progress: Callable[[SonyImportProgress], None],
    ) -> SonyImportResult: ...


DirectoryOpener = Callable[[Path], None]
AfterImport = Callable[[], Awaitable[object]]


class SynchronizedCameraImporter:
    """Serialize app automation when several cameras share one Android phone."""

    def __init__(self, importer: CameraImporter, operation_lock: threading.Lock) -> None:
        self.destination = importer.destination
        self._importer = importer
        self._operation_lock = operation_lock

    def probe(self) -> SonyPhoneProbe:
        return self._importer.probe()

    def import_all(
        self,
        progress: Callable[[SonyImportProgress], None],
    ) -> SonyImportResult:
        with self._operation_lock:
            return self._importer.import_all(progress)


def open_windows_directory(destination: Path) -> None:
    windows_directory = os.environ.get("WINDIR")
    if os.name != "nt" or not windows_directory:
        raise SonyCameraImportError(
            "SONY_DESTINATION_OPEN_UNAVAILABLE",
            "Opening the camera import folder is available on Windows only.",
        )
    explorer = (Path(windows_directory) / "explorer.exe").resolve()
    if not explorer.is_file():
        raise SonyCameraImportError(
            "SONY_DESTINATION_OPEN_UNAVAILABLE",
            "Windows File Explorer is unavailable.",
        )
    destination.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.Popen(
            (str(explorer), str(destination.resolve())),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError as error:
        raise SonyCameraImportError(
            "SONY_DESTINATION_OPEN_FAILED",
            "Windows could not open the camera import folder.",
        ) from error


class SonyCameraImportService:
    """Own exactly one import task and expose poll-friendly snapshots."""

    def __init__(
        self,
        importer: CameraImporter,
        *,
        camera_id: str = SONY_CAMERA_ID,
        display_name: str = "Sony ZV-E10",
        app_display_name: str = "Sony Imaging Edge Mobile",
        error_prefix: str = "SONY",
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        probe_interval: float = 10.0,
        automatic_interval: float | None = None,
        automatic_initial_delay: float = 15.0,
        directory_opener: DirectoryOpener | None = open_windows_directory,
        after_import: AfterImport | None = None,
    ) -> None:
        if automatic_interval is not None and automatic_interval <= 0:
            raise ValueError("automatic_interval must be positive or None")
        if automatic_initial_delay < 0:
            raise ValueError("automatic_initial_delay cannot be negative")
        self._importer = importer
        self.camera_id = camera_id
        self.display_name = display_name
        self._app_display_name = app_display_name
        self._error_prefix = error_prefix
        self._clock = clock or (lambda: datetime.now(UTC))
        self._monotonic = monotonic
        self._probe_interval = probe_interval
        self._automatic_interval = automatic_interval
        self._automatic_initial_delay = automatic_initial_delay
        self._directory_opener = directory_opener
        self._after_import = after_import
        self._last_probe_at = float("-inf")
        self._last_activity_at = float("-inf")
        self._task: asyncio.Task[None] | None = None
        self._automatic_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._snapshot = CameraImportSnapshot(
            cameraId=camera_id,
            displayName=display_name,
            state=CameraImportState.UNAVAILABLE,
            destination=str(importer.destination),
            phoneConnected=False,
            appInstalled=False,
            bluetoothEnabled=False,
            cameraWifiConnected=False,
            setupRequired=False,
            filesOnPhone=0,
            bytesOnPhone=0,
            automaticEnabled=automatic_interval is not None,
            automaticIntervalSeconds=(
                max(1, round(automatic_interval)) if automatic_interval is not None else None
            ),
            operations=CameraImportOperations(
                startImport=False,
                openDestination=directory_opener is not None,
            ),
        )

    @property
    def destination(self) -> Path:
        return self._importer.destination

    async def snapshot(self, *, refresh: bool = True) -> CameraImportSnapshot:
        async with self._lock:
            active = self._task is not None and not self._task.done()
            due = self._monotonic() - self._last_probe_at >= self._probe_interval
            if refresh and due and not active:
                probe = await asyncio.to_thread(self._importer.probe)
                self._apply_probe(probe)
                self._last_probe_at = self._monotonic()
            return self._snapshot.model_copy(deep=True)

    async def start_import(self, *, automatic: bool = False) -> CameraImportActionResult:
        async with self._lock:
            if self._task is not None and not self._task.done():
                raise SonyCameraImportError(
                    f"{self._error_prefix}_IMPORT_ALREADY_RUNNING",
                    f"A {self.display_name} import is already running.",
                )
            self._last_activity_at = self._monotonic()
            if automatic:
                self._snapshot.lastAutomaticAttemptAt = self._clock()
            probe = await asyncio.to_thread(self._importer.probe)
            self._apply_probe(probe)
            self._last_probe_at = self._monotonic()
            if not probe.phone_connected:
                raise SonyCameraImportError(
                    f"{self._error_prefix}_PHONE_NOT_CONNECTED",
                    probe.message or "The dedicated Android phone is not connected.",
                )
            if not probe.app_installed:
                raise SonyCameraImportError(
                    f"{self._error_prefix}_APP_NOT_INSTALLED",
                    f"{self._app_display_name} is not installed on the dedicated phone.",
                )
            require_battery_for_sync(
                probe.phone_battery or BatteryReading(),
                code=f"{self._error_prefix}_PHONE_BATTERY_LOW",
                device="phone",
                display_name="Dedicated Android phone",
            )
            self._snapshot.state = CameraImportState.CONNECTING
            self._snapshot.progress = CameraImportProgress(
                stage="connecting",
                message="Preparing the Android companion",
            )
            self._snapshot.errorCode = None
            self._snapshot.message = None
            self._snapshot.setupRequired = False
            self._snapshot.cameraBattery = CameraImportBattery()
            self._snapshot.operations.startImport = False
            self._task = asyncio.create_task(self._run_import())
            snapshot = self._snapshot.model_copy(deep=True)
        return CameraImportActionResult(
            accepted=True,
            message=f"{self.display_name} camera import started.",
            snapshot=snapshot,
        )

    async def start_automatic_imports(self) -> None:
        if self._automatic_interval is None:
            return
        async with self._lock:
            if self._automatic_task is not None and not self._automatic_task.done():
                return
            self._automatic_task = asyncio.create_task(
                self._automatic_loop(),
                name=f"{self.camera_id}-periodic-import",
            )

    async def open_destination(self) -> CameraDestinationActionResult:
        if self._directory_opener is None:
            raise SonyCameraImportError(
                f"{self._error_prefix}_DESTINATION_OPEN_UNAVAILABLE",
                "Opening the camera import folder is not configured.",
            )
        await asyncio.to_thread(self._directory_opener, self._importer.destination)
        return CameraDestinationActionResult(
            opened=True,
            destination=str(self._importer.destination),
            message="Camera import folder opened in Windows File Explorer.",
        )

    async def stop_automatic_imports(self) -> None:
        task = self._automatic_task
        self._automatic_task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        async with self._lock:
            self._snapshot.nextAutomaticRunAt = None

    async def wait_until_idle(self) -> CameraImportSnapshot:
        task = self._task
        if task is not None:
            await task
        return await self.snapshot(refresh=False)

    async def _automatic_loop(self) -> None:
        assert self._automatic_interval is not None
        first_run = True
        while True:
            now = self._monotonic()
            if first_run:
                delay = self._automatic_initial_delay
            else:
                elapsed = now - self._last_activity_at
                delay = max(0.0, self._automatic_interval - elapsed)
            activity_marker = self._last_activity_at
            async with self._lock:
                self._snapshot.nextAutomaticRunAt = self._clock() + timedelta(seconds=delay)
            await asyncio.sleep(delay)
            async with self._lock:
                self._snapshot.nextAutomaticRunAt = None
            first_run = False
            if self._last_activity_at != activity_marker:
                continue
            try:
                await self.start_import(automatic=True)
            except SonyCameraImportError:
                continue
            await asyncio.shield(self.wait_until_idle())

    async def _run_import(self) -> None:
        loop = asyncio.get_running_loop()

        def report(progress: SonyImportProgress) -> None:
            loop.call_soon_threadsafe(self._on_progress, progress)

        try:
            result = await asyncio.to_thread(self._importer.import_all, report)
            await asyncio.sleep(0)
        except SonyCameraBatteryLow as error:
            self._snapshot.state = CameraImportState.DEFERRED
            self._snapshot.setupRequired = False
            self._snapshot.errorCode = error.code
            self._snapshot.message = str(error)
            self._snapshot.progress = None
            battery = camera_import_battery(error.battery)
            if error.device == "phone":
                self._snapshot.phoneBattery = battery
            else:
                self._snapshot.cameraBattery = battery
        except SonyCameraSetupRequired as error:
            self._snapshot.state = CameraImportState.SETUP_REQUIRED
            self._snapshot.setupRequired = True
            self._snapshot.errorCode = error.code
            self._snapshot.message = str(error)
            self._snapshot.progress = None
        except SonyCameraImportError as error:
            self._snapshot.state = CameraImportState.FAILED
            self._snapshot.errorCode = error.code
            self._snapshot.message = str(error)
            self._snapshot.progress = None
        except Exception as error:  # defensive boundary around external app automation
            self._snapshot.state = CameraImportState.FAILED
            self._snapshot.errorCode = f"{self._error_prefix}_IMPORT_UNEXPECTED"
            self._snapshot.message = f"{self.display_name} import failed: {type(error).__name__}"
            self._snapshot.progress = None
        else:
            self._snapshot.state = CameraImportState.COMPLETED
            self._snapshot.lastResult = CameraImportResult(
                copiedFiles=result.copied_files,
                skippedFiles=result.skipped_files,
                verifiedFiles=result.verified_files,
                copiedBytes=result.copied_bytes,
                totalBytes=result.total_bytes,
                completedAt=self._clock(),
            )
            self._snapshot.filesOnPhone = result.verified_files
            self._snapshot.bytesOnPhone = result.total_bytes
            self._snapshot.progress = None
            self._snapshot.errorCode = None
            self._snapshot.message = "All available originals were copied and verified."
        finally:
            self._last_activity_at = self._monotonic()
            self._snapshot.operations.startImport = (
                self._snapshot.phoneConnected
                and self._snapshot.appInstalled
                and self._snapshot.phoneBattery.condition != "blocked"
            )
            if self._after_import is not None:
                with suppress(Exception):
                    await self._after_import()

    def _on_progress(self, progress: SonyImportProgress) -> None:
        try:
            state = CameraImportState(progress.stage)
        except ValueError:
            state = CameraImportState.INVENTORY
        self._snapshot.state = state
        self._snapshot.progress = CameraImportProgress(
            stage=progress.stage,
            message=progress.message,
            completedItems=progress.completed_items,
            totalItems=progress.total_items,
            bytesOnPhone=progress.bytes_on_phone,
        )
        if progress.bytes_on_phone:
            self._snapshot.bytesOnPhone = progress.bytes_on_phone
        if progress.phone_battery is not None:
            self._snapshot.phoneBattery = camera_import_battery(progress.phone_battery)
        if progress.camera_battery is not None:
            self._snapshot.cameraBattery = camera_import_battery(progress.camera_battery)

    def _apply_probe(self, probe: SonyPhoneProbe) -> None:
        self._snapshot.phoneConnected = probe.phone_connected
        self._snapshot.phoneModel = probe.phone_model
        self._snapshot.appInstalled = probe.app_installed
        self._snapshot.bluetoothEnabled = probe.bluetooth_enabled
        self._snapshot.cameraWifiConnected = probe.camera_wifi_connected
        self._snapshot.phoneBattery = camera_import_battery(probe.phone_battery)
        self._snapshot.filesOnPhone = probe.files_on_phone
        self._snapshot.bytesOnPhone = probe.bytes_on_phone
        phone_battery_blocked = self._snapshot.phoneBattery.condition == "blocked"
        self._snapshot.operations.startImport = (
            probe.phone_connected and probe.app_installed and not phone_battery_blocked
        )
        if self._snapshot.state in ACTIVE_CAMERA_STATES:
            return
        if phone_battery_blocked:
            level = self._snapshot.phoneBattery.levelPercent
            self._snapshot.state = CameraImportState.DEFERRED
            self._snapshot.setupRequired = False
            self._snapshot.errorCode = f"{self._error_prefix}_PHONE_BATTERY_LOW"
            self._snapshot.message = (
                f"Dedicated Android phone battery is {level}% and is not charging; "
                "sync will retry on the next automatic interval."
            )
            return
        phone_battery_error = f"{self._error_prefix}_PHONE_BATTERY_LOW"
        if (
            self._snapshot.state is CameraImportState.DEFERRED
            and self._snapshot.errorCode == phone_battery_error
        ):
            self._snapshot.state = CameraImportState.READY
            self._snapshot.errorCode = None
            self._snapshot.message = None
        if not probe.phone_connected or not probe.app_installed:
            self._snapshot.state = CameraImportState.UNAVAILABLE
            self._snapshot.message = probe.message
        elif self._snapshot.state not in {
            CameraImportState.COMPLETED,
            CameraImportState.SETUP_REQUIRED,
            CameraImportState.DEFERRED,
            CameraImportState.FAILED,
        }:
            self._snapshot.state = CameraImportState.READY
            self._snapshot.message = None


class _UnavailableImporter:
    def __init__(self, destination: Path) -> None:
        self.destination = destination

    def probe(self) -> SonyPhoneProbe:
        return SonyPhoneProbe(
            phone_connected=False,
            message="Sony Android import is not configured on this runtime.",
        )

    def import_all(
        self,
        _progress: Callable[[SonyImportProgress], None],
    ) -> SonyImportResult:
        raise SonyCameraImportError(
            "SONY_IMPORT_NOT_CONFIGURED",
            "Sony Android import is not configured on this runtime.",
        )


def disabled_sony_camera_import(destination: Path) -> SonyCameraImportService:
    return SonyCameraImportService(
        _UnavailableImporter(destination),
        directory_opener=None,
    )


def configured_sony_camera_import(
    *,
    operation_lock: threading.Lock | None = None,
    after_import: AfterImport | None = None,
) -> SonyCameraImportService:
    configured_destination = os.environ.get("CITXR_SONY_IMPORT_DIRECTORY")
    if configured_destination:
        destination = Path(configured_destination)
    elif user_profile := os.environ.get("USERPROFILE"):
        destination = Path(user_profile) / "Pictures" / "Sony Camera Imports"
    else:
        destination = Path.home() / "Pictures" / "Sony Camera Imports"
    if not destination.is_absolute():
        raise ValueError("CITXR_SONY_IMPORT_DIRECTORY must be an absolute path")
    configured_interval = os.environ.get("CITXR_SONY_AUTO_IMPORT_INTERVAL_SECONDS", "900").strip()
    if configured_interval.casefold() in {"0", "false", "off"}:
        automatic_interval: float | None = None
    else:
        try:
            automatic_interval = float(configured_interval)
        except ValueError as error:
            raise ValueError(
                "CITXR_SONY_AUTO_IMPORT_INTERVAL_SECONDS must be a number or 'off'"
            ) from error
        if not 60 <= automatic_interval <= 86_400:
            raise ValueError("CITXR_SONY_AUTO_IMPORT_INTERVAL_SECONDS must be between 60 and 86400")
    importer: CameraImporter = AdbSonyCameraImporter(
        destination,
        adb_path=os.environ.get("CITXR_ADB_PATH", "adb"),
        preferred_serial=os.environ.get("CITXR_SONY_PHONE_SERIAL"),
    )
    if operation_lock is not None:
        importer = SynchronizedCameraImporter(importer, operation_lock)
    return SonyCameraImportService(
        importer,
        automatic_interval=automatic_interval,
        after_import=after_import,
    )


def configured_dji_camera_import(
    *,
    operation_lock: threading.Lock | None = None,
    after_import: AfterImport | None = None,
) -> SonyCameraImportService:
    from .dji_camera_import import AdbDjiCameraImporter

    configured_destination = os.environ.get("CITXR_DJI_IMPORT_DIRECTORY")
    if configured_destination:
        destination = Path(configured_destination)
    elif user_profile := os.environ.get("USERPROFILE"):
        destination = Path(user_profile) / "Pictures" / "DJI Osmo Nano Imports"
    else:
        destination = Path.home() / "Pictures" / "DJI Osmo Nano Imports"
    if not destination.is_absolute():
        raise ValueError("CITXR_DJI_IMPORT_DIRECTORY must be an absolute path")
    configured_interval = os.environ.get("CITXR_DJI_AUTO_IMPORT_INTERVAL_SECONDS", "900").strip()
    if configured_interval.casefold() in {"0", "false", "off"}:
        automatic_interval: float | None = None
    else:
        try:
            automatic_interval = float(configured_interval)
        except ValueError as error:
            raise ValueError(
                "CITXR_DJI_AUTO_IMPORT_INTERVAL_SECONDS must be a number or 'off'"
            ) from error
        if not 60 <= automatic_interval <= 86_400:
            raise ValueError("CITXR_DJI_AUTO_IMPORT_INTERVAL_SECONDS must be between 60 and 86400")
    importer: CameraImporter = AdbDjiCameraImporter(
        destination,
        adb_path=os.environ.get("CITXR_ADB_PATH", "adb"),
        preferred_serial=os.environ.get(
            "CITXR_DJI_PHONE_SERIAL", os.environ.get("CITXR_SONY_PHONE_SERIAL")
        ),
    )
    if operation_lock is not None:
        importer = SynchronizedCameraImporter(importer, operation_lock)
    return SonyCameraImportService(
        importer,
        camera_id=DJI_CAMERA_ID,
        display_name="DJI Osmo Nano",
        app_display_name="DJI Mimo",
        error_prefix="DJI",
        automatic_interval=automatic_interval,
        automatic_initial_delay=45.0,
        after_import=after_import,
    )
