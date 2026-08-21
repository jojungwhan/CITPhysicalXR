"""Credential-free host discovery and allowlisted local connection actions.

The Interaction Fabric core never imports a vendor SDK.  This module invokes a
fixed, repository-owned host probe and, for the already-running Brain2Devices
compatibility service, a closed set of loopback-only connection operations.
Neither path accepts a shell command, device credential, address, or arbitrary
URL from the browser.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from cit_protocol import IntegrationNode
from pydantic import BaseModel, ConfigDict, Field, ValidationError

DISCOVERY_REPORT_MAX_BYTES = 262_144
DISCOVERY_SCAN_TIMEOUT_SECONDS = 35.0
DISCOVERY_ACTION_TIMEOUT_SECONDS = 120.0

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


class FabricDiscoveryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DiscoveryRunner(Protocol):
    async def scan(self) -> FabricDiscoveryReport: ...

    async def perform(self, action_id: str, *, confirm_grounded: bool) -> str: ...


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
        self._last_report = initial_discovery_report(
            at=self._clock(),
            physical_actuation_enabled=physical_actuation_enabled,
        )

    def current(self, nodes: Iterable[IntegrationNode]) -> FabricDiscoveryReport:
        return _overlay_connected_nodes(self._last_report, nodes)

    async def scan(self, nodes: Iterable[IntegrationNode]) -> FabricDiscoveryReport:
        async with self._scan_lock:
            report = await self._runner.scan()
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


class PowerShellDiscoveryRunner:
    """Run the fixed Windows probe and closed Brain2Devices actions."""

    def __init__(
        self,
        *,
        script_path: Path,
        state_root: Path,
        brain2devices_root: Path,
        robomaster_root: Path,
        fabric_port: int = 8766,
        powershell_path: str | None = None,
        brain2devices_origin: str = "http://127.0.0.1:8765",
    ) -> None:
        self._script_path = script_path.resolve()
        self._state_root = state_root.resolve()
        self._brain2devices_root = brain2devices_root.resolve()
        self._robomaster_root = robomaster_root.resolve()
        if not 1024 <= fabric_port <= 65535:
            raise ValueError("fabric_port must be between 1024 and 65535")
        self._fabric_port = fabric_port
        self._powershell_path = powershell_path
        if brain2devices_origin != "http://127.0.0.1:8765":
            raise ValueError("Brain2Devices discovery is restricted to its loopback origin")
        self._brain = _Brain2DevicesClient(brain2devices_origin)

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
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=DISCOVERY_SCAN_TIMEOUT_SECONDS,
            )
        except TimeoutError as error:
            process.kill()
            await process.wait()
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
        if action_id == "cit.glasses-agent.connect":
            await self._run_launcher(
                "glasses-agent-hardware-test.ps1",
                "-Mode",
                "Start",
                "-SharedFabricRoot",
                str(self._state_root),
                "-FabricPort",
                str(self._fabric_port),
                "-SelectMostRecentAgentSession",
                "-SkipBuild",
                "-NoOpenConsole",
            )
            return (
                "Glasses and coding-agent adapters connected through the existing "
                "Agent Mesh bridge."
            )
        if action_id == "cit.robomaster-leap.connect":
            await self._run_launcher(
                "robomaster-leap-hardware-test.ps1",
                "-Mode",
                "Start",
                "-SharedFabricRoot",
                str(self._state_root),
                "-FabricPort",
                str(self._fabric_port),
                "-Live",
                "-ConnectOnly",
                "-MaxSpeed",
                "0.10",
                "-MaxYaw",
                "10",
                "-SkipBuild",
                "-NoOpenConsole",
            )
            return (
                "Leap Motion and RoboMaster connected in an unstarted lesson. "
                "The robot remains disarmed and no movement command was enabled."
            )
        if action_id == "cit.smart-plug.connect":
            await self._run_launcher(
                "smart-plug-hardware-test.ps1",
                "-Mode",
                "Start",
                "-SharedFabricRoot",
                str(self._state_root),
                "-FabricPort",
                str(self._fabric_port),
                "-Live",
                "-ConnectOnly",
                "-NoOpenConsole",
            )
            return (
                "The approved smart-plug adapter connected and read its state. "
                "The outlet was not switched and its unstarted lesson remains disarmed."
            )
        if action_id == "brain2devices.tello.connect-all":
            if not confirm_grounded:
                raise FabricDiscoveryError(
                    "GROUNDED_CONFIRMATION_REQUIRED",
                    "Confirm that every Tello is grounded with propellers removed or guarded",
                )
            await self._brain.post("/api/fleet/local-radios/auto-connect")
            return (
                "Tello radio association and SDK handshakes started. "
                "No takeoff, movement, landing, or emergency command was sent."
            )
        if action_id == "brain2devices.tello.connect-primary":
            if not confirm_grounded:
                raise FabricDiscoveryError(
                    "GROUNDED_CONFIRMATION_REQUIRED",
                    "Confirm that the Tello is grounded with propellers removed or guarded",
                )
            await self._brain.post("/api/drone/connect")
            return "The grounded Tello SDK handshake started; no flight command was sent."
        if action_id == "brain2devices.mindwave.connect":
            await self._brain.post("/api/headset/connect")
            return "MindWave connection started through the preserved Brain2Devices boundary."
        raise FabricDiscoveryError(
            "DISCOVERY_ACTION_NOT_ALLOWED",
            "That device connection action is not allowlisted",
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
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=DISCOVERY_ACTION_TIMEOUT_SECONDS,
            )
        except TimeoutError as error:
            process.kill()
            await process.wait()
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
        _not_scanned(
            "even-meta-glasses",
            "Even G2 and Meta glasses",
            "interaction",
            "Phone bridge / Agent Mesh",
            "Start Agent Mesh, then open or wear each provisioned pair of glasses.",
        ),
        _not_scanned(
            "coding-agents",
            "Codex and Claude coding agents",
            "coding_agent",
            "Local supervised process",
            "Start an approved Codex or Claude session in the lesson workspace.",
        ),
        _not_scanned(
            "leap-motion",
            "Leap Motion",
            "interaction",
            "USB / Ultraleap service",
            "Plug in the Leap controller and start the Ultraleap tracking service.",
        ),
        _not_scanned(
            "robomaster-s1",
            "DJI RoboMaster S1",
            "robot",
            "Wi-Fi, USB/RNDIS, or DJI app bridge",
            "Connect the robot without arming it; movement remains lesson-gated.",
        ),
        _not_scanned(
            "tello-drones",
            "DJI / Ryze Tello drones",
            "drone",
            "One Wi-Fi route per aircraft",
            "Power on grounded aircraft before scanning; no scan sends a flight command.",
        ),
        _not_scanned(
            "mindwave-mobile2",
            "MindWave Mobile 2",
            "sensor",
            "Bluetooth through ThinkGear Connector",
            "Pair the headset and run ThinkGear Connector on localhost:13854.",
        ),
        _not_scanned(
            "tuya-gosund-plugs",
            "Tuya and Gosund smart plugs",
            "smart_device",
            "Local Tuya LAN profile",
            "Add each approved plug's local key once; CIT never sends it through discovery.",
        ),
        _not_scanned(
            "lego-hubs",
            "LEGO SPIKE and MINDSTORMS",
            "robot",
            "Bluetooth / Pybricks",
            "Pair a named Pybricks hub and keep motor control disarmed during setup.",
        ),
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
    integration_id: str,
    display_name: str,
    category: str,
    connection_method: str,
    setup_step: str,
) -> FabricIntegrationDiscovery:
    return FabricIntegrationDiscovery.model_validate(
        {
            "integrationId": integration_id,
            "displayName": display_name,
            "category": category,
            "status": "not_scanned",
            "summary": "Choose Find devices to check this computer and its local connections.",
            "connectionMethod": connection_method,
            "setupSteps": [setup_step],
            "safetyNote": "Discovery never arms or actuates this integration.",
        }
    )


def _overlay_connected_nodes(
    report: FabricDiscoveryReport,
    nodes: Iterable[IntegrationNode],
) -> FabricDiscoveryReport:
    active = tuple(
        node for node in nodes if node.connectionState.value in {"connected", "degraded"}
    )
    integrations = []
    for integration in report.integrations:
        matches = [node for node in active if _node_matches(integration.integrationId, node)]
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


def _node_matches(integration_id: str, node: IntegrationNode) -> bool:
    if integration_id in {"even-meta-glasses", "coding-agents"}:
        if node.pluginId != "cit.agent-mesh-bridge":
            return False
        names = {
            capability.name
            for capability in (*node.publishedCapabilities, *node.consumedCapabilities)
        }
        expected = (
            {"interaction.intent.agent_prompt", "display.text.render"}
            if integration_id == "even-meta-glasses"
            else {"agent.prompt.submit", "agent.output.completed"}
        )
        return bool(names & expected)
    if integration_id in {"leap-motion", "robomaster-s1"}:
        if node.pluginId != "cit.robomaster-gesture-control":
            return False
        model = str(node.metadata.model_dump(mode="python").get("model", ""))
        return model == (
            "ultraleap-leap-motion" if integration_id == "leap-motion" else "robomaster-s1"
        )
    if integration_id == "tuya-gosund-plugs":
        return node.pluginId == "cit.tuya-smart-plug"
    if integration_id == "tello-drones":
        return node.pluginId in {"cit.brain2devices", "cit.tello"} and any(
            capability.name.startswith("mobility.flight.")
            for capability in node.consumedCapabilities
        )
    if integration_id == "mindwave-mobile2":
        return node.pluginId in {"cit.brain2devices", "cit.mindwave-mobile2"}
    if integration_id == "lego-hubs":
        return node.pluginId in {"cit.lego-pybricks", "cit.lego-spike", "cit.lego-mindstorms"}
    return False


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
