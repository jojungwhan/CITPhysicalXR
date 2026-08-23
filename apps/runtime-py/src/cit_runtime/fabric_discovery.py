"""Host discovery and allowlisted local connection/commissioning actions.

The Interaction Fabric core never imports a vendor SDK. This module invokes
fixed, repository-owned host probes and a closed set of loopback-only connection
operations. Browser input is passed only to fixed adapter launchers; no path
accepts a shell command or arbitrary URL. Sensitive commissioning values are
streamed over stdin rather than process arguments.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from cit_protocol import IntegrationNode
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .fabric_integration_catalog import IntegrationDescriptor, load_integration_catalog

DISCOVERY_REPORT_MAX_BYTES = 262_144
DISCOVERY_SCAN_TIMEOUT_SECONDS = 35.0
DISCOVERY_ACTION_TIMEOUT_SECONDS = 120.0


class _ProcessOutputTooLarge(RuntimeError):
    pass


class _FleetMonitoringAttachment(BaseModel):
    """Validated hand-off written by the independently managed fleet launcher."""

    model_config = ConfigDict(extra="ignore")

    sessionId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    fleetNodeId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    siteId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    roomId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


async def _read_bounded_stream(
    stream: asyncio.StreamReader | None,
    *,
    limit: int,
) -> bytes:
    if stream is None:
        return b""
    result = bytearray()
    while True:
        chunk = await stream.read(min(65_536, limit - len(result) + 1))
        if not chunk:
            return bytes(result)
        result.extend(chunk)
        if len(result) > limit:
            raise _ProcessOutputTooLarge


async def _communicate_bounded(
    process: asyncio.subprocess.Process,
    *,
    timeout_seconds: float,
    input_bytes: bytes | None = None,
) -> tuple[bytes, bytes]:
    stdout_task = asyncio.create_task(
        _read_bounded_stream(process.stdout, limit=DISCOVERY_REPORT_MAX_BYTES)
    )
    stderr_task = asyncio.create_task(
        _read_bounded_stream(process.stderr, limit=DISCOVERY_REPORT_MAX_BYTES)
    )
    try:
        if input_bytes is not None:
            if process.stdin is None:
                raise RuntimeError("Launcher input pipe is unavailable")
            process.stdin.write(input_bytes)
            with suppress(BrokenPipeError, ConnectionResetError):
                await process.stdin.drain()
            process.stdin.close()
        async with asyncio.timeout(timeout_seconds):
            stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
            await process.wait()
        return stdout, stderr
    except BaseException:
        stdout_task.cancel()
        stderr_task.cancel()
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        raise


DiscoveryStatus = Literal[
    "not_scanned",
    "connected",
    "found",
    "ready",
    "setup_required",
    "not_found",
    "unavailable",
]


class FabricDiscoveryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidateId: str = Field(min_length=1, max_length=160)
    displayName: str = Field(min_length=1, max_length=160)
    transport: str = Field(min_length=1, max_length=80)
    status: Literal["found", "ready", "setup_required", "not_found"]
    detail: str = Field(min_length=1, max_length=500)
    signalPercent: int | None = Field(default=None, ge=0, le=100)
    connectionPath: (
        Literal[
            "usb",
            "bluetooth",
            "wifi",
            "android",
            "android_usb",
            "android_wifi",
            "local_service",
        ]
        | None
    ) = None
    linkState: (
        Literal[
            "attached",
            "connected",
            "recently_active",
            "visible",
            "paired",
            "provisioned",
            "ready",
        ]
        | None
    ) = None


class FabricIntegrationDiscovery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    integrationId: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=96)
    displayName: str = Field(min_length=1, max_length=160)
    category: Literal[
        "interaction",
        "sensor",
        "robot",
        "drone",
        "smart_device",
        "coding_agent",
    ]
    ioType: Literal["input", "output", "bidirectional"] = "bidirectional"
    icon: (
        Literal[
            "brain",
            "drone",
            "glasses",
            "hand",
            "lego",
            "plug",
            "robot",
            "sphero",
            "terminal",
        ]
        | None
    ) = None
    status: DiscoveryStatus
    summary: str = Field(min_length=1, max_length=500)
    connectionMethod: str = Field(min_length=1, max_length=160)
    connectedNodeIds: list[str] = Field(default_factory=list, max_length=64)
    candidates: list[FabricDiscoveryCandidate] = Field(default_factory=list, max_length=64)
    setupSteps: list[str] = Field(default_factory=list, max_length=8)
    setupCommand: str | None = Field(default=None, max_length=1_024)
    actionId: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
        max_length=96,
    )
    actionLabel: str | None = Field(default=None, min_length=1, max_length=100)
    requiresGroundedConfirmation: bool = False
    safetyNote: str = Field(min_length=1, max_length=500)


class FabricDiscoveryReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["1.0"] = "1.0"
    scanId: str = Field(min_length=1, max_length=128)
    scannedAt: datetime
    hostId: str = Field(min_length=1, max_length=160)
    platform: str = Field(min_length=1, max_length=80)
    physicalActuationEnabled: bool
    integrations: list[FabricIntegrationDiscovery] = Field(min_length=1, max_length=32)
    warnings: list[str] = Field(default_factory=list, max_length=16)


class FabricDiscoveryActionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actionId: str
    accepted: bool
    message: str
    report: FabricDiscoveryReport


class LegoConnectionConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hubName: str = Field(min_length=1, max_length=80)
    hubModel: Literal["spike-prime", "spike-essential", "robot-inventor"]
    ports: dict[str, Literal["empty", "motor", "distance", "color", "force"]] = Field(
        min_length=1,
        max_length=6,
    )

    @model_validator(mode="after")
    def validate_exact_hub_profile(self) -> LegoConnectionConfiguration:
        if self.hubName != self.hubName.strip() or any(
            ord(character) < 32 or ord(character) == 127 for character in self.hubName
        ):
            raise ValueError("LEGO hub name must be trimmed printable text")
        allowed_ports = (
            {"A", "B"} if self.hubModel == "spike-essential" else {"A", "B", "C", "D", "E", "F"}
        )
        if set(self.ports) - allowed_ports or any(port != port.upper() for port in self.ports):
            raise ValueError("LEGO port map does not match the selected hub")
        if all(kind == "empty" for kind in self.ports.values()):
            raise ValueError("LEGO monitoring requires at least one connected port")
        return self


class FabricDiscoveryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DiscoveryRunner(Protocol):
    async def scan(self) -> FabricDiscoveryReport: ...

    async def perform(self, action_id: str, *, confirm_grounded: bool) -> str: ...

    async def commission_matter(self, setup_code: str) -> str: ...

    async def connect_lego(self, configuration: LegoConnectionConfiguration) -> str: ...


class FabricDiscoveryService:
    """Serialize host scans, cache their result, and overlay live Fabric nodes."""

    def __init__(
        self,
        runner: DiscoveryRunner,
        *,
        clock: Callable[[], datetime] | None = None,
        physical_actuation_enabled: bool = False,
    ) -> None:
        self._runner = runner
        self._clock = clock or (lambda: datetime.now(UTC))
        self._physical_actuation_enabled = physical_actuation_enabled
        self._scan_lock = asyncio.Lock()
        self._connection_lock = asyncio.Lock()
        self._last_report = initial_discovery_report(
            at=self._clock(),
            physical_actuation_enabled=physical_actuation_enabled,
        )

    def current(self, nodes: Iterable[IntegrationNode]) -> FabricDiscoveryReport:
        return _overlay_connected_nodes(self._last_report, nodes)

    async def scan(self, nodes: Iterable[IntegrationNode]) -> FabricDiscoveryReport:
        async with self._scan_lock:
            report = await self._runner.scan()
            report = _canonicalize_discovery_report(report)
            report = report.model_copy(
                update={"physicalActuationEnabled": self._physical_actuation_enabled}
            )
            self._last_report = report
        return _overlay_connected_nodes(report, nodes)

    async def perform(
        self,
        action_id: str,
        *,
        confirm_grounded: bool,
        nodes: Iterable[IntegrationNode],
    ) -> FabricDiscoveryActionResult:
        async with self._connection_lock:
            message = await self._runner.perform(
                action_id,
                confirm_grounded=confirm_grounded,
            )
        report = await self.scan(nodes)
        return FabricDiscoveryActionResult(
            actionId=action_id,
            accepted=True,
            message=message,
            report=report,
        )

    async def commission_matter(
        self,
        setup_code: str,
        *,
        nodes: Iterable[IntegrationNode],
    ) -> FabricDiscoveryActionResult:
        if (
            setup_code != setup_code.strip()
            or not 11 <= len(setup_code) <= 103
            or any(ord(character) < 32 for character in setup_code)
        ):
            raise FabricDiscoveryError(
                "MATTER_SETUP_CODE_INVALID",
                "Enter the Matter QR or manual setup code printed on the plug",
            )
        async with self._connection_lock:
            message = await self._runner.commission_matter(setup_code)
        report = await self.scan(nodes)
        return FabricDiscoveryActionResult(
            actionId="cit.matter-smart-plug.commission",
            accepted=True,
            message=message,
            report=report,
        )

    async def connect_lego(
        self,
        configuration: LegoConnectionConfiguration,
        *,
        nodes: Iterable[IntegrationNode],
    ) -> FabricDiscoveryActionResult:
        async with self._connection_lock:
            message = await self._runner.connect_lego(configuration)
        report = await self.scan(nodes)
        return FabricDiscoveryActionResult(
            actionId="cit.lego-pybricks.configure-connect",
            accepted=True,
            message=message,
            report=report,
        )


class UnavailableDiscoveryRunner:
    """Safe default for tests and embedded runtimes without a host probe."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))

    async def scan(self) -> FabricDiscoveryReport:
        return initial_discovery_report(at=self._clock())

    async def perform(self, action_id: str, *, confirm_grounded: bool) -> str:
        del action_id, confirm_grounded
        raise FabricDiscoveryError(
            "DISCOVERY_ACTION_UNAVAILABLE",
            "Local device connection actions are unavailable in this runtime",
        )

    async def commission_matter(self, setup_code: str) -> str:
        del setup_code
        raise FabricDiscoveryError(
            "MATTER_COMMISSIONING_UNAVAILABLE",
            "Local Matter commissioning is unavailable in this runtime",
        )

    async def connect_lego(self, configuration: LegoConnectionConfiguration) -> str:
        del configuration
        raise FabricDiscoveryError(
            "LEGO_CONNECTION_UNAVAILABLE",
            "Local LEGO connection is unavailable in this runtime",
        )


@dataclass(frozen=True, slots=True)
class _LauncherAction:
    script_name: str
    arguments: tuple[str, ...]
    success_message: str


class PowerShellDiscoveryRunner:
    """Run the fixed Windows probe and closed Brain2Devices actions."""

    def __init__(
        self,
        *,
        script_path: Path,
        state_root: Path,
        brain2devices_root: Path,
        robomaster_root: Path,
        agent_mesh_root: Path,
        fabric_port: int = 8766,
        powershell_path: str | None = None,
        brain2devices_origin: str = "http://127.0.0.1:8765",
    ) -> None:
        self._script_path = script_path.resolve()
        self._state_root = state_root.resolve()
        self._brain2devices_root = brain2devices_root.resolve()
        self._robomaster_root = robomaster_root.resolve()
        self._agent_mesh_root = agent_mesh_root.resolve()
        if not 1024 <= fabric_port <= 65535:
            raise ValueError("fabric_port must be between 1024 and 65535")
        self._fabric_port = fabric_port
        self._powershell_path = powershell_path
        if brain2devices_origin != "http://127.0.0.1:8765":
            raise ValueError("Brain2Devices discovery is restricted to its loopback origin")
        self._brain = _Brain2DevicesClient(brain2devices_origin)
        common = (
            "-SharedFabricRoot",
            str(self._state_root),
            "-FabricPort",
            str(self._fabric_port),
        )
        self._launcher_actions: Mapping[str, _LauncherAction] = MappingProxyType(
            {
                "cit.glasses-agent.connect": _LauncherAction(
                    "glasses-agent-hardware-test.ps1",
                    (
                        "-Mode",
                        "Start",
                        *common,
                        "-StateRoot",
                        str(self._state_root.parent / "glasses-agent"),
                        "-SelectMostRecentAgentSession",
                        "-SkipBuild",
                        "-NoOpenConsole",
                    ),
                    "Glasses and coding-agent adapters connected through the existing "
                    "Agent Mesh bridge.",
                ),
                "cit.robomaster-leap.connect": _LauncherAction(
                    "robomaster-leap-hardware-test.ps1",
                    (
                        "-Mode",
                        "Start",
                        *common,
                        "-StateRoot",
                        str(self._state_root.parent / "robomaster-leap"),
                        "-Live",
                        "-ConnectOnly",
                        "-MaxSpeed",
                        "0.10",
                        "-MaxYaw",
                        "10",
                        "-SkipBuild",
                        "-NoOpenConsole",
                    ),
                    "Leap Motion and RoboMaster connected in an unstarted lesson. "
                    "The robot remains disarmed and no movement command was enabled.",
                ),
                "cit.matter-smart-plug.connect": _LauncherAction(
                    "matter-smart-plug.ps1",
                    (
                        "-Mode",
                        "Start",
                        *common,
                        "-SkipBuild",
                        "-NoOpenConsole",
                    ),
                    "Every commissioned local Matter plug connected through the CIT "
                    "controller. Approved plug endpoints were placed in the off safe "
                    "state and lessons remain disarmed.",
                ),
                "cit.lego-pybricks.connect": _LauncherAction(
                    "lego-pybricks.ps1",
                    (
                        "-Mode",
                        "Start",
                        *common,
                        "-StateRoot",
                        str(self._state_root.parent / "lego-pybricks"),
                        "-SkipBuild",
                        "-NoOpenConsole",
                    ),
                    "The configured LEGO hub connected for unarmed sensor monitoring. "
                    "Motor control remains locked until it is assigned to an armed lesson.",
                ),
            }
        )

    async def scan(self) -> FabricDiscoveryReport:
        powershell = self._powershell_path or shutil.which("pwsh")
        if os.name != "nt" or powershell is None or not self._script_path.is_file():
            return initial_discovery_report(
                at=datetime.now(UTC),
                warning="Windows host discovery is unavailable on this installation.",
            )
        process = await asyncio.create_subprocess_exec(
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(self._script_path),
            "-StateRoot",
            str(self._state_root),
            "-Brain2DevicesRoot",
            str(self._brain2devices_root),
            "-RoboMasterRoot",
            str(self._robomaster_root),
            "-AgentMeshRoot",
            str(self._agent_mesh_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        )
        try:
            stdout, stderr = await _communicate_bounded(
                process,
                timeout_seconds=DISCOVERY_SCAN_TIMEOUT_SECONDS,
            )
        except _ProcessOutputTooLarge as error:
            raise FabricDiscoveryError(
                "DISCOVERY_REPORT_TOO_LARGE",
                "The local discovery report exceeded its size limit",
            ) from error
        except TimeoutError as error:
            raise FabricDiscoveryError(
                "DISCOVERY_SCAN_TIMED_OUT",
                "Device discovery took too long; no connection or device command was sent",
            ) from error
        if len(stdout) > DISCOVERY_REPORT_MAX_BYTES:
            raise FabricDiscoveryError(
                "DISCOVERY_REPORT_TOO_LARGE",
                "The local discovery report exceeded its size limit",
            )
        if process.returncode != 0:
            diagnostic = stderr.decode("utf-8", errors="replace").strip()
            raise FabricDiscoveryError(
                "DISCOVERY_SCAN_FAILED",
                (diagnostic or "The Windows host probe failed")[:500],
            )
        try:
            raw = json.loads(stdout.decode("utf-8"), object_pairs_hook=_unique_object)
            return FabricDiscoveryReport.model_validate(raw)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
            raise FabricDiscoveryError(
                "DISCOVERY_REPORT_INVALID",
                "The Windows host probe returned an invalid report",
            ) from error

    async def perform(self, action_id: str, *, confirm_grounded: bool) -> str:
        launcher_action = self._launcher_actions.get(action_id)
        if launcher_action is not None:
            attachment = self._fleet_monitoring_attachment()
            if attachment is not None and action_id in {
                "cit.glasses-agent.connect",
                "cit.robomaster-leap.connect",
            }:
                arguments = (
                    *(
                        argument
                        for argument in launcher_action.arguments
                        if argument not in {"-SelectMostRecentAgentSession", "-ConnectOnly"}
                    ),
                    "-FleetInputOnly",
                    "-FabricSessionId",
                    attachment.sessionId,
                    "-SiteId",
                    attachment.siteId,
                    "-RoomId",
                    attachment.roomId,
                )
                await self._run_launcher(launcher_action.script_name, *arguments)
                input_name = (
                    "G2/Meta" if action_id == "cit.glasses-agent.connect" else "Leap Motion"
                )
                return (
                    f"{input_name} joined the active fleet-control page as an input only. "
                    "It cannot bypass the tutor's one-shot arm and safety confirmations."
                )
            await self._run_launcher(
                launcher_action.script_name,
                *launcher_action.arguments,
            )
            return launcher_action.success_message
        if action_id == "brain2devices.tello.connect-all":
            if not confirm_grounded:
                raise FabricDiscoveryError(
                    "GROUNDED_CONFIRMATION_REQUIRED",
                    "Confirm that every Tello is grounded with propellers removed or guarded",
                )
            await self._brain.post("/api/fleet/local-radios/auto-connect")
            await self._brain.wait_for("tello")
            await self._reconcile_brain_adapters()
            return (
                "Connected Tello sessions now have independent Fabric nodes. "
                "Only telemetry, land, and emergency stop are enabled."
            )
        if action_id == "brain2devices.tello.connect-primary":
            if not confirm_grounded:
                raise FabricDiscoveryError(
                    "GROUNDED_CONFIRMATION_REQUIRED",
                    "Confirm that the Tello is grounded with propellers removed or guarded",
                )
            await self._brain.post("/api/drone/connect")
            await self._brain.wait_for("tello")
            await self._reconcile_brain_adapters()
            return "The grounded Tello is connected as an independent safe Fabric node."
        if action_id == "brain2devices.mindwave.connect":
            await self._brain.post("/api/headset/connect")
            await self._brain.wait_for("mindwave")
            await self._reconcile_brain_adapters()
            return "MindWave is connected as an independent publish-only Fabric node."
        raise FabricDiscoveryError(
            "DISCOVERY_ACTION_NOT_ALLOWED",
            "That device connection action is not allowlisted",
        )

    async def _reconcile_brain_adapters(self) -> None:
        device_group = await self._brain.adapter_device_group()
        await self._run_launcher(
            "brain2devices-fabric-adapters.ps1",
            "-Mode",
            "Start",
            "-Device",
            device_group,
            "-Brain2DevicesRoot",
            str(self._brain2devices_root),
            "-StateRoot",
            str(self._state_root.parent / "brain2devices-fabric"),
            "-SharedFabricRoot",
            str(self._state_root),
            "-FabricPort",
            str(self._fabric_port),
            "-CompatibilityApi",
            "-SkipBuild",
            "-NoOpenConsole",
        )

    def _fleet_monitoring_attachment(self) -> _FleetMonitoringAttachment | None:
        state_path = self._state_root.parent / "brain2devices-fabric" / "state.json"
        try:
            payload = state_path.read_text(encoding="utf-8")
            return _FleetMonitoringAttachment.model_validate_json(payload)
        except (OSError, UnicodeDecodeError, ValidationError, ValueError):
            return None

    async def commission_matter(self, setup_code: str) -> str:
        if not 11 <= len(setup_code) <= 103 or any(ord(character) < 32 for character in setup_code):
            raise FabricDiscoveryError(
                "MATTER_SETUP_CODE_INVALID",
                "Enter the Matter QR or manual setup code printed on the plug",
            )
        await self._run_input_launcher(
            "matter-smart-plug.ps1",
            "-Mode",
            "Commission",
            "-SharedFabricRoot",
            str(self._state_root),
            "-FabricPort",
            str(self._fabric_port),
            "-SkipBuild",
            "-NoOpenConsole",
            input_text=json.dumps({"setupCode": setup_code}, separators=(",", ":")),
            redactions=(setup_code,),
            timeout_seconds=280,
            error_prefix="MATTER_COMMISSIONING",
            operation_name="Matter commissioning",
            timeout_message=(
                "Matter commissioning timed out; put the plug back in pairing mode and try again"
            ),
            failure_message=(
                "Matter commissioning failed; confirm pairing mode and classroom Wi-Fi"
            ),
        )
        return (
            "The plug joined the local CIT Matter fabric without a vendor account. "
            "Its bounded adapter is connected in an unstarted, disarmed lesson."
        )

    async def connect_lego(self, configuration: LegoConnectionConfiguration) -> str:
        await self._run_input_launcher(
            "lego-pybricks.ps1",
            "-Mode",
            "ConfigureStart",
            "-SharedFabricRoot",
            str(self._state_root),
            "-StateRoot",
            str(self._state_root.parent / "lego-pybricks"),
            "-FabricPort",
            str(self._fabric_port),
            "-SkipBuild",
            "-NoOpenConsole",
            input_text=configuration.model_dump_json(),
            redactions=(),
            timeout_seconds=90,
            error_prefix="LEGO_CONNECTION",
            operation_name="LEGO connection",
            timeout_message=(
                "LEGO connection timed out; confirm the exact hub name, Pybricks firmware, "
                "Bluetooth, and the running hub agent"
            ),
            failure_message=(
                "LEGO connection failed; check the hub name, model, port map, and Pybricks setup"
            ),
        )
        return (
            f"{configuration.hubName} connected for unarmed sensor monitoring. "
            "CIT selected no anonymous hub and issued no motor command."
        )

    async def _run_launcher(self, script_name: str, *arguments: str) -> None:
        powershell = self._powershell_path or shutil.which("pwsh")
        launcher = (self._script_path.parent / script_name).resolve()
        if (
            os.name != "nt"
            or powershell is None
            or launcher.parent != self._script_path.parent
            or not launcher.is_file()
        ):
            raise FabricDiscoveryError(
                "DISCOVERY_ACTION_UNAVAILABLE",
                "The fixed local adapter launcher is unavailable on this host",
            )
        process = await asyncio.create_subprocess_exec(
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(launcher),
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        )
        try:
            stdout, stderr = await _communicate_bounded(
                process,
                timeout_seconds=DISCOVERY_ACTION_TIMEOUT_SECONDS,
            )
        except _ProcessOutputTooLarge as error:
            raise FabricDiscoveryError(
                "DISCOVERY_ACTION_OUTPUT_TOO_LARGE",
                "The local adapter launcher exceeded its diagnostic output limit",
            ) from error
        except TimeoutError as error:
            raise FabricDiscoveryError(
                "DISCOVERY_ACTION_TIMED_OUT",
                "The local adapter took too long to connect and remains disarmed",
            ) from error
        if len(stdout) + len(stderr) > DISCOVERY_REPORT_MAX_BYTES:
            raise FabricDiscoveryError(
                "DISCOVERY_ACTION_OUTPUT_TOO_LARGE",
                "The local adapter launcher exceeded its diagnostic output limit",
            )
        if process.returncode != 0:
            diagnostic = stderr.decode("utf-8", errors="replace").strip()
            if not diagnostic:
                diagnostic = stdout.decode("utf-8", errors="replace").strip()
            raise FabricDiscoveryError(
                "DISCOVERY_CONNECTION_FAILED",
                (diagnostic.rsplit("\n", maxsplit=1)[-1] or "Adapter connection failed")[:500],
            )

    async def _run_input_launcher(
        self,
        script_name: str,
        *arguments: str,
        input_text: str,
        redactions: tuple[str, ...],
        timeout_seconds: float,
        error_prefix: str,
        operation_name: str,
        timeout_message: str,
        failure_message: str,
    ) -> None:
        powershell = self._powershell_path or shutil.which("pwsh")
        launcher = (self._script_path.parent / script_name).resolve()
        if (
            os.name != "nt"
            or powershell is None
            or launcher.parent != self._script_path.parent
            or not launcher.is_file()
        ):
            raise FabricDiscoveryError(
                f"{error_prefix}_UNAVAILABLE",
                f"The fixed local {operation_name} launcher is unavailable on this host",
            )
        process = await asyncio.create_subprocess_exec(
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(launcher),
            *arguments,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        )
        try:
            stdout, stderr = await _communicate_bounded(
                process,
                timeout_seconds=timeout_seconds,
                input_bytes=input_text.encode("utf-8"),
            )
        except _ProcessOutputTooLarge as error:
            raise FabricDiscoveryError(
                "DISCOVERY_ACTION_OUTPUT_TOO_LARGE",
                f"The {operation_name} launcher exceeded its diagnostic output limit",
            ) from error
        except TimeoutError as error:
            raise FabricDiscoveryError(
                f"{error_prefix}_TIMED_OUT",
                timeout_message,
            ) from error
        if len(stdout) + len(stderr) > DISCOVERY_REPORT_MAX_BYTES:
            raise FabricDiscoveryError(
                "DISCOVERY_ACTION_OUTPUT_TOO_LARGE",
                f"The {operation_name} launcher exceeded its diagnostic output limit",
            )
        if process.returncode != 0:
            diagnostic = stderr.decode("utf-8", errors="replace").strip()
            if not diagnostic:
                diagnostic = stdout.decode("utf-8", errors="replace").strip()
            for secret in redactions:
                diagnostic = diagnostic.replace(secret, "[redacted]")
            raise FabricDiscoveryError(
                f"{error_prefix}_FAILED",
                (diagnostic.rsplit("\n", maxsplit=1)[-1] or failure_message)[:500],
            )


class _ControlTokenParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "meta":
            return
        values = {name.casefold(): value for name, value in attrs if value is not None}
        if values.get("name") == "brain2devices-token":
            candidate = values.get("content", "")
            if 32 <= len(candidate) <= 512:
                self.token = candidate


class _Brain2DevicesClient:
    def __init__(self, origin: str) -> None:
        self._origin = origin

    async def post(self, path: str) -> None:
        allowed = {
            "/api/fleet/local-radios/auto-connect",
            "/api/drone/connect",
            "/api/headset/connect",
        }
        if path not in allowed:
            raise FabricDiscoveryError(
                "DISCOVERY_ACTION_NOT_ALLOWED",
                "That Brain2Devices operation is not allowlisted",
            )
        await asyncio.to_thread(self._post_sync, path)

    async def wait_for(self, device: Literal["tello", "mindwave"]) -> None:
        deadline = asyncio.get_running_loop().time() + 70
        while asyncio.get_running_loop().time() < deadline:
            state = await asyncio.to_thread(self._get_state_sync)
            if device == "mindwave":
                headset = state.get("headset")
                if isinstance(headset, dict) and headset.get("connection") == "connected":
                    return
            else:
                fleet = state.get("fleet")
                drones = fleet.get("drones") if isinstance(fleet, dict) else None
                if isinstance(drones, list) and any(
                    isinstance(drone, dict) and drone.get("connection") == "connected"
                    for drone in drones
                ):
                    return
            await asyncio.sleep(0.25)
        raise FabricDiscoveryError(
            "BRAIN2DEVICES_CONNECTION_TIMED_OUT",
            f"Brain2Devices did not finish the {device} connection; check its activity log",
        )

    async def adapter_device_group(self) -> Literal["All", "Tello", "MindWave"]:
        state = await asyncio.to_thread(self._get_state_sync)
        headset = state.get("headset")
        mindwave_connected = isinstance(headset, dict) and headset.get("connection") == "connected"
        fleet = state.get("fleet")
        drones = fleet.get("drones") if isinstance(fleet, dict) else None
        tello_connected = isinstance(drones, list) and any(
            isinstance(drone, dict) and drone.get("connection") == "connected" for drone in drones
        )
        if tello_connected and mindwave_connected:
            return "All"
        if tello_connected:
            return "Tello"
        if mindwave_connected:
            return "MindWave"
        raise FabricDiscoveryError(
            "BRAIN2DEVICES_CONNECTION_LOST",
            "Brain2Devices no longer reports the device as connected",
        )

    def _get_state_sync(self) -> dict[str, object]:
        try:
            with urlopen(
                Request(f"{self._origin}/api/state", headers={"Accept": "application/json"}),
                timeout=5,
            ) as response:
                raw = response.read(262_144)
            value: object = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FabricDiscoveryError(
                "BRAIN2DEVICES_UNAVAILABLE",
                "Brain2Devices stopped responding while the device connected",
            ) from error
        if not isinstance(value, dict):
            raise FabricDiscoveryError(
                "BRAIN2DEVICES_RESPONSE_INVALID",
                "Brain2Devices state must be an object",
            )
        return value

    def _post_sync(self, path: str) -> None:
        try:
            with urlopen(
                Request(f"{self._origin}/", headers={"Accept": "text/html"}),
                timeout=5,
            ) as response:
                page = response.read(65_536).decode("utf-8")
            parser = _ControlTokenParser()
            parser.feed(page)
            if parser.token is None:
                raise FabricDiscoveryError(
                    "BRAIN2DEVICES_AUTH_UNAVAILABLE",
                    "Brain2Devices did not expose its local page-scoped control grant",
                )
            request = Request(
                f"{self._origin}{path}",
                data=b"{}",
                method="POST",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Brain2Devices-Token": parser.token,
                },
            )
            with urlopen(request, timeout=DISCOVERY_ACTION_TIMEOUT_SECONDS) as response:
                raw = response.read(65_536)
            body = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
            if not isinstance(body, dict) or body.get("accepted") is not True:
                message = body.get("error") if isinstance(body, dict) else None
                raise FabricDiscoveryError(
                    "BRAIN2DEVICES_CONNECTION_REJECTED",
                    str(message or "Brain2Devices rejected the connection request")[:500],
                )
        except FabricDiscoveryError:
            raise
        except HTTPError as error:
            detail = ""
            try:
                body = json.loads(error.read(65_536).decode("utf-8"))
                if isinstance(body, dict):
                    detail = str(body.get("error", ""))
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            raise FabricDiscoveryError(
                "BRAIN2DEVICES_CONNECTION_REJECTED",
                (detail or f"Brain2Devices returned HTTP {error.code}")[:500],
            ) from error
        except (OSError, URLError, TimeoutError) as error:
            raise FabricDiscoveryError(
                "BRAIN2DEVICES_UNAVAILABLE",
                "Start the local Brain2Devices hardware service, then scan again",
            ) from error
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise FabricDiscoveryError(
                "BRAIN2DEVICES_RESPONSE_INVALID",
                "Brain2Devices returned an invalid local response",
            ) from error


def initial_discovery_report(
    *,
    at: datetime,
    physical_actuation_enabled: bool = False,
    warning: str | None = None,
) -> FabricDiscoveryReport:
    integrations = [
        _not_scanned(descriptor) for descriptor in load_integration_catalog().integrations
    ]
    return FabricDiscoveryReport(
        scanId=f"not-scanned-{uuid4()}",
        scannedAt=at,
        hostId=os.environ.get("COMPUTERNAME") or "local-host",
        platform=os.name,
        physicalActuationEnabled=physical_actuation_enabled,
        integrations=integrations,
        warnings=[] if warning is None else [warning],
    )


def _not_scanned(
    descriptor: IntegrationDescriptor,
) -> FabricIntegrationDiscovery:
    return FabricIntegrationDiscovery.model_validate(
        {
            "integrationId": descriptor.integrationId,
            "displayName": descriptor.displayName,
            "category": descriptor.category,
            "ioType": descriptor.ioType,
            "icon": descriptor.icon,
            "status": "not_scanned",
            "summary": "Choose Find devices to check this computer and its local connections.",
            "connectionMethod": descriptor.connectionMethod,
            "setupSteps": descriptor.setupSteps,
            "safetyNote": descriptor.safetyNote,
        }
    )


def _overlay_connected_nodes(
    report: FabricDiscoveryReport,
    nodes: Iterable[IntegrationNode],
) -> FabricDiscoveryReport:
    active = tuple(
        node for node in nodes if node.connectionState.value in {"connected", "degraded"}
    )
    catalog = load_integration_catalog()
    integrations = []
    for integration in report.integrations:
        descriptor = catalog.require(integration.integrationId)
        matches = [node for node in active if descriptor.matches(node)]
        if not matches:
            integrations.append(integration)
            continue
        integrations.append(
            integration.model_copy(
                update={
                    "status": "connected",
                    "connectedNodeIds": sorted(node.nodeId for node in matches),
                    "summary": _connected_summary(integration.integrationId, matches),
                }
            )
        )
    return report.model_copy(update={"integrations": integrations})


def _canonicalize_discovery_report(report: FabricDiscoveryReport) -> FabricDiscoveryReport:
    """Replace probe-owned presentation metadata with catalog values."""

    catalog = load_integration_catalog()
    dynamic = {item.integrationId: item for item in report.integrations}
    canonical: list[FabricIntegrationDiscovery] = []
    for descriptor in catalog.integrations:
        discovered = dynamic.get(descriptor.integrationId)
        if discovered is None:
            canonical.append(_not_scanned(descriptor))
            continue
        canonical.append(
            discovered.model_copy(
                update={
                    "displayName": descriptor.displayName,
                    "category": descriptor.category,
                    "ioType": descriptor.ioType,
                    "icon": descriptor.icon,
                    "connectionMethod": descriptor.connectionMethod,
                    "setupSteps": descriptor.setupSteps,
                    "safetyNote": descriptor.safetyNote,
                    # Shell commands are never part of the browser contract.
                    "setupCommand": None,
                }
            )
        )
    unknown = sorted(set(dynamic) - {item.integrationId for item in catalog.integrations})
    warnings = list(report.warnings)
    if unknown:
        warnings.append("Ignored unregistered discovery integrations: " + ", ".join(unknown))
    return report.model_copy(update={"integrations": canonical, "warnings": warnings})


def _connected_summary(integration_id: str, nodes: list[IntegrationNode]) -> str:
    healthy = sum(node.healthState.value == "healthy" for node in nodes)
    label = "device" if len(nodes) == 1 else "devices"
    if integration_id == "coding-agents":
        label = "agent session" if len(nodes) == 1 else "agent sessions"
    return f"{len(nodes)} {label} connected to CIT; {healthy} reporting healthy."


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Discovery JSON repeats key {key!r}")
        result[key] = value
    return result
