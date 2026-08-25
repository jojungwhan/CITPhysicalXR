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
from tempfile import TemporaryFile
from types import MappingProxyType
from typing import Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from cit_protocol import IntegrationNode
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator

from .fabric_integration_catalog import IntegrationDescriptor, load_integration_catalog

DISCOVERY_REPORT_MAX_BYTES = 262_144
DISCOVERY_SCAN_TIMEOUT_SECONDS = 35.0
DISCOVERY_ACTION_TIMEOUT_SECONDS = 120.0
DISCOVERY_OUTPUT_SIZE_POLL_SECONDS = 0.05
SESSION_TARGET_ACTION_COURSE_PACKS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "cit.glasses-device-control.connect": frozenset(
            {"glasses-device-control", "synchronized-motor-control"}
        ),
        "cit.synchronized-mindwave.connect": frozenset({"synchronized-motor-control"}),
    }
)


class _ProcessOutputTooLarge(RuntimeError):
    pass


class _FleetMonitoringAttachment(BaseModel):
    """Validated hand-off written by the independently managed fleet launcher."""

    model_config = ConfigDict(extra="ignore")

    sessionId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    fleetNodeId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    siteId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    roomId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class FabricDiscoverySessionTarget(BaseModel):
    """Validated lesson scope passed to a fixed local connection launcher."""

    model_config = ConfigDict(extra="forbid")

    sessionId: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    coursePackId: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    siteId: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    roomId: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )


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


async def _run_with_bounded_file_output(
    *command: str,
    timeout_seconds: float,
    input_bytes: bytes | None = None,
    creationflags: int = 0,
) -> tuple[int, bytes, bytes]:
    """Run a launcher without pipes that detached Windows children can retain."""

    with TemporaryFile(mode="w+b") as stdout_file, TemporaryFile(mode="w+b") as stderr_file:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if input_bytes is not None else None,
            stdout=stdout_file,
            stderr=stderr_file,
            creationflags=creationflags,
        )
        wait_task = asyncio.create_task(process.wait())
        try:
            if input_bytes is not None:
                if process.stdin is None:
                    raise RuntimeError("Launcher input pipe is unavailable")
                process.stdin.write(input_bytes)
                with suppress(BrokenPipeError, ConnectionResetError):
                    await process.stdin.drain()
                process.stdin.close()
            async with asyncio.timeout(timeout_seconds):
                while not wait_task.done():
                    await asyncio.wait(
                        {wait_task},
                        timeout=DISCOVERY_OUTPUT_SIZE_POLL_SECONDS,
                    )
                    if (
                        os.fstat(stdout_file.fileno()).st_size
                        + os.fstat(stderr_file.fileno()).st_size
                        > DISCOVERY_REPORT_MAX_BYTES
                    ):
                        raise _ProcessOutputTooLarge
                returncode = await wait_task
            stdout_file.flush()
            stderr_file.flush()
            if (
                os.fstat(stdout_file.fileno()).st_size + os.fstat(stderr_file.fileno()).st_size
                > DISCOVERY_REPORT_MAX_BYTES
            ):
                raise _ProcessOutputTooLarge
            stdout_file.seek(0)
            stderr_file.seek(0)
            return returncode, stdout_file.read(), stderr_file.read()
        except BaseException:
            wait_task.cancel()
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                await process.wait()
            await asyncio.gather(wait_task, return_exceptions=True)
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
    model: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
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
            "ring",
            "sphero",
            "terminal",
            "wonder",
        ]
        | None
    ) = None
    imagePath: str | None = Field(
        default=None,
        pattern=r"^\./device-images/[a-z0-9][a-z0-9._-]*\.webp$",
        max_length=160,
    )
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


class FabricRememberedConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actionId: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=96)
    requiresGroundedConfirmation: bool
    rememberedAt: datetime


class FabricRememberedConnections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["1.0"] = "1.0"
    hostId: str = Field(min_length=1, max_length=160)
    connections: list[FabricRememberedConnection] = Field(default_factory=list, max_length=32)


class FabricRememberedConnectionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actionId: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=96)
    status: Literal["connected", "already_connected", "skipped", "failed"]
    message: str = Field(min_length=1, max_length=500)
    code: str | None = Field(default=None, max_length=96)


class FabricRememberedConnectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["1.0"] = "1.0"
    connectedCount: int = Field(ge=0, le=32)
    alreadyConnectedCount: int = Field(ge=0, le=32)
    skippedCount: int = Field(ge=0, le=32)
    failedCount: int = Field(ge=0, le=32)
    outcomes: list[FabricRememberedConnectionOutcome] = Field(
        default_factory=list,
        max_length=32,
    )
    report: FabricDiscoveryReport


@dataclass(frozen=True, slots=True)
class RememberedConnectionPolicy:
    action_id: str
    integration_ids: tuple[str, ...]
    requires_grounded_confirmation: bool = False


_REMEMBERED_CONNECTION_POLICIES: Mapping[str, RememberedConnectionPolicy] = MappingProxyType(
    {
        policy.action_id: policy
        for policy in (
            RememberedConnectionPolicy(
                "cit.glasses-agent.connect",
                ("meta-rayban", "coding-agents"),
            ),
            RememberedConnectionPolicy(
                "cit.even-g2.connect",
                ("even-realities-g2",),
            ),
            RememberedConnectionPolicy(
                "cit.even-r1.connect",
                ("even-realities-r1",),
            ),
            RememberedConnectionPolicy(
                "cit.robomaster-leap.connect",
                ("leap-motion", "robomaster-s1"),
            ),
            RememberedConnectionPolicy(
                "cit.matter-smart-plug.connect",
                ("matter-smart-plugs",),
            ),
            RememberedConnectionPolicy(
                "cit.lego-pybricks.connect",
                ("lego-hubs",),
            ),
            RememberedConnectionPolicy(
                "cit.wonder-workshop.reconnect",
                ("wonder-workshop-dash-dot",),
            ),
            RememberedConnectionPolicy(
                "cit.sphero-bolt.reconnect",
                ("sphero-bolt",),
            ),
            RememberedConnectionPolicy(
                "cit.sphero-ollie.reconnect",
                ("sphero-ollie",),
            ),
            RememberedConnectionPolicy(
                "brain2devices.mindwave.connect",
                ("mindwave-mobile2",),
            ),
            RememberedConnectionPolicy(
                "brain2devices.tello.connect-all",
                ("tello-drones",),
                requires_grounded_confirmation=True,
            ),
        )
    }
)

_REMEMBERED_CONNECTION_ALIASES: Mapping[str, str] = MappingProxyType(
    {"brain2devices.tello.connect-primary": "brain2devices.tello.connect-all"}
)


def remembered_connection_policy(action_id: str) -> RememberedConnectionPolicy | None:
    canonical_action = _REMEMBERED_CONNECTION_ALIASES.get(action_id, action_id)
    return _REMEMBERED_CONNECTION_POLICIES.get(canonical_action)


def remembered_connection_policies_for_nodes(
    nodes: Iterable[IntegrationNode],
) -> tuple[tuple[RememberedConnectionPolicy, datetime], ...]:
    physical_nodes = tuple(node for node in nodes if node.physical and not node.simulated)
    catalog = load_integration_catalog()
    matches: list[tuple[RememberedConnectionPolicy, datetime]] = []
    for policy in _REMEMBERED_CONNECTION_POLICIES.values():
        descriptors = tuple(catalog.require(value) for value in policy.integration_ids)
        matching = tuple(
            node
            for node in physical_nodes
            if any(descriptor.matches(node) for descriptor in descriptors)
        )
        if matching:
            matches.append((policy, max(node.lastSeenAt for node in matching)))
    return tuple(matches)


class MatterWifiConfiguration(BaseModel):
    """Ephemeral credentials used only to provision the local Matter controller."""

    model_config = ConfigDict(extra="forbid")

    ssid: str = Field(min_length=1, max_length=32)
    password: SecretStr = Field(min_length=8, max_length=63)

    @model_validator(mode="after")
    def validate_wifi_values(self) -> MatterWifiConfiguration:
        if (
            self.ssid != self.ssid.strip()
            or len(self.ssid.encode("utf-8")) > 32
            or any(ord(character) < 32 or ord(character) == 127 for character in self.ssid)
        ):
            raise ValueError("Wi-Fi name must be trimmed printable text of at most 32 bytes")
        password = self.password.get_secret_value()
        if any(ord(character) < 32 or ord(character) == 127 for character in password):
            raise ValueError("Wi-Fi password must not contain control characters")
        return self


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


class WonderRobotSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidateId: str = Field(pattern=r"^wonder-[a-f0-9]{12}$")
    model: Literal["dash", "dot"]


class WonderWorkshopConnectionConfiguration(BaseModel):
    """Exact opaque BLE candidates selected by a tutor in the local UI."""

    model_config = ConfigDict(extra="forbid")

    robots: list[WonderRobotSelection] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_candidate_ids(self) -> WonderWorkshopConnectionConfiguration:
        candidate_ids = [robot.candidateId for robot in self.robots]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("Dash/Dot candidates must be unique")
        return self


class SpheroBoltSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidateId: str = Field(pattern=r"^sphero-[a-f0-9]{12}$")


class SpheroBoltConnectionConfiguration(BaseModel):
    """Exact opaque BOLT candidates selected by a tutor in the local UI."""

    model_config = ConfigDict(extra="forbid")

    robots: list[SpheroBoltSelection] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_candidate_ids(self) -> SpheroBoltConnectionConfiguration:
        candidate_ids = [robot.candidateId for robot in self.robots]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("Sphero BOLT candidates must be unique")
        return self


class SpheroOllieSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidateId: str = Field(pattern=r"^sphero-ollie-[a-f0-9]{12}$")


class SpheroOllieConnectionConfiguration(BaseModel):
    """Exact opaque Ollie candidates selected by a tutor in the local UI."""

    model_config = ConfigDict(extra="forbid")

    robots: list[SpheroOllieSelection] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_candidate_ids(self) -> SpheroOllieConnectionConfiguration:
        candidate_ids = [robot.candidateId for robot in self.robots]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("Sphero Ollie candidates must be unique")
        return self


class FabricDiscoveryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _is_orphaned_brain2devices_radio_route(error: FabricDiscoveryError) -> bool:
    """Match only Brain2Devices' deterministic stale managed-route refusal."""

    message = str(error).casefold()
    return (
        error.code == "BRAIN2DEVICES_CONNECTION_REJECTED"
        and "brain2devices-managed static ipv4 assignment" in message
        and "restore dhcp first" in message
    )


def _is_brain2devices_imported_radio_route_refusal(
    error: FabricDiscoveryError,
) -> bool:
    """Match reassignment refusal when the safe route is already imported."""

    message = str(error).casefold()
    return (
        error.code == "BRAIN2DEVICES_CONNECTION_REJECTED"
        and "is already imported for" in message
        and "remove that disconnected mapping before assigning a different tello" in message
    )


def _is_brain2devices_radio_capacity_refusal(error: FabricDiscoveryError) -> bool:
    """Match the safe partial-connect case where aircraft outnumber radios."""

    message = str(error).casefold()
    return (
        error.code == "BRAIN2DEVICES_CONNECTION_REJECTED"
        and "could safely assign only" in message
        and "physical wi-fi adapter" in message
        and "each standard tello needs its own adapter" in message
        and "no wi-fi association" in message
        and "flight command was changed" in message
    )


def _is_brain2devices_existing_landed_session_refusal(
    error: FabricDiscoveryError,
) -> bool:
    """Match a redundant route change blocked by already connected landed Tellos."""

    message = str(error).casefold()
    affected_sessions = message.count("currently uses")
    return (
        error.code == "BRAIN2DEVICES_CONNECTION_REJECTED"
        and "local wi-fi routes cannot change while an affected aircraft session may be active"
        in message
        and affected_sessions > 0
        and message.count("(connected, landed)") == affected_sessions
        and "land and disconnect any connected or busy affected sessions first" in message
    )


class DiscoveryRunner(Protocol):
    async def scan(self) -> FabricDiscoveryReport: ...

    async def perform(
        self,
        action_id: str,
        *,
        confirm_grounded: bool,
        session_target: FabricDiscoverySessionTarget | None = None,
    ) -> str: ...

    async def configure_matter_wifi(self, configuration: MatterWifiConfiguration) -> str: ...

    async def commission_matter(self, setup_code: str) -> str: ...

    async def connect_lego(self, configuration: LegoConnectionConfiguration) -> str: ...

    async def connect_wonder_workshop(
        self, configuration: WonderWorkshopConnectionConfiguration
    ) -> str: ...

    async def connect_sphero_bolts(
        self, configuration: SpheroBoltConnectionConfiguration
    ) -> str: ...

    async def connect_sphero_ollies(
        self, configuration: SpheroOllieConnectionConfiguration
    ) -> str: ...


NodeProvider = Callable[[], Iterable[IntegrationNode]]


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
        nodes: NodeProvider,
        session_target: FabricDiscoverySessionTarget | None = None,
    ) -> FabricDiscoveryActionResult:
        async with self._connection_lock:
            if session_target is None:
                # Keep compatibility with small embedded discovery runners that
                # implement the original two-argument protocol.
                message = await self._runner.perform(
                    action_id,
                    confirm_grounded=confirm_grounded,
                )
            else:
                message = await self._runner.perform(
                    action_id,
                    confirm_grounded=confirm_grounded,
                    session_target=session_target,
                )
        # Adapter launchers wait for Fabric registration before returning. Use
        # that live-node overlay instead of repeating the broad host scan; the
        # explicit Find devices action remains the single scan entry point.
        report = self.current(nodes())
        return FabricDiscoveryActionResult(
            actionId=action_id,
            accepted=True,
            message=message,
            report=report,
        )

    async def reconnect_remembered(
        self,
        connections: Iterable[FabricRememberedConnection],
        *,
        confirm_grounded: bool,
        nodes: NodeProvider,
    ) -> FabricRememberedConnectionResult:
        outcomes: list[FabricRememberedConnectionOutcome] = []
        async with self._connection_lock:
            for connection in connections:
                policy = remembered_connection_policy(connection.actionId)
                if policy is None:
                    outcomes.append(
                        FabricRememberedConnectionOutcome(
                            actionId=connection.actionId,
                            status="failed",
                            code="REMEMBERED_CONNECTION_NOT_ALLOWED",
                            message="The remembered connection action is no longer allowlisted.",
                        )
                    )
                    continue
                if _policy_has_live_node(policy, nodes()):
                    outcomes.append(
                        FabricRememberedConnectionOutcome(
                            actionId=connection.actionId,
                            status="already_connected",
                            message="A matching CIT adapter is already connected.",
                        )
                    )
                    continue
                if policy.requires_grounded_confirmation and not confirm_grounded:
                    outcomes.append(
                        FabricRememberedConnectionOutcome(
                            actionId=connection.actionId,
                            status="skipped",
                            code="GROUNDED_CONFIRMATION_REQUIRED",
                            message=(
                                "The remembered aircraft connection was skipped until a tutor "
                                "confirms that every aircraft is grounded."
                            ),
                        )
                    )
                    continue
                try:
                    message = await self._runner.perform(
                        connection.actionId,
                        confirm_grounded=confirm_grounded,
                    )
                except FabricDiscoveryError as error:
                    outcomes.append(
                        FabricRememberedConnectionOutcome(
                            actionId=connection.actionId,
                            status="failed",
                            code=error.code,
                            message=str(error),
                        )
                    )
                    continue
                outcomes.append(
                    FabricRememberedConnectionOutcome(
                        actionId=connection.actionId,
                        status="connected",
                        message=message,
                    )
                )
        # Deliberately avoid the broad host scan used by perform(). Adapter
        # launchers wait for registration, so the live-node overlay is enough.
        report = self.current(nodes())
        return FabricRememberedConnectionResult(
            connectedCount=sum(outcome.status == "connected" for outcome in outcomes),
            alreadyConnectedCount=sum(
                outcome.status == "already_connected" for outcome in outcomes
            ),
            skippedCount=sum(outcome.status == "skipped" for outcome in outcomes),
            failedCount=sum(outcome.status == "failed" for outcome in outcomes),
            outcomes=outcomes,
            report=report,
        )

    async def commission_matter(
        self,
        setup_code: str,
        *,
        nodes: NodeProvider,
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
        report = await self.scan(nodes())
        return FabricDiscoveryActionResult(
            actionId="cit.matter-smart-plug.commission",
            accepted=True,
            message=message,
            report=report,
        )

    async def configure_matter_wifi(
        self,
        configuration: MatterWifiConfiguration,
        *,
        nodes: NodeProvider,
    ) -> FabricDiscoveryActionResult:
        async with self._connection_lock:
            message = await self._runner.configure_matter_wifi(configuration)
        report = await self.scan(nodes())
        return FabricDiscoveryActionResult(
            actionId="cit.matter-smart-plug.configure-wifi",
            accepted=True,
            message=message,
            report=report,
        )

    async def connect_lego(
        self,
        configuration: LegoConnectionConfiguration,
        *,
        nodes: NodeProvider,
    ) -> FabricDiscoveryActionResult:
        async with self._connection_lock:
            message = await self._runner.connect_lego(configuration)
        report = await self.scan(nodes())
        return FabricDiscoveryActionResult(
            actionId="cit.lego-pybricks.configure-connect",
            accepted=True,
            message=message,
            report=report,
        )

    async def connect_wonder_workshop(
        self,
        configuration: WonderWorkshopConnectionConfiguration,
        *,
        nodes: NodeProvider,
    ) -> FabricDiscoveryActionResult:
        async with self._connection_lock:
            message = await self._runner.connect_wonder_workshop(configuration)
        report = await self.scan(nodes())
        return FabricDiscoveryActionResult(
            actionId="cit.wonder-workshop.configure-connect",
            accepted=True,
            message=message,
            report=report,
        )

    async def connect_sphero_bolts(
        self,
        configuration: SpheroBoltConnectionConfiguration,
        *,
        nodes: NodeProvider,
    ) -> FabricDiscoveryActionResult:
        async with self._connection_lock:
            message = await self._runner.connect_sphero_bolts(configuration)
        report = await self.scan(nodes())
        return FabricDiscoveryActionResult(
            actionId="cit.sphero-bolt.configure-connect",
            accepted=True,
            message=message,
            report=report,
        )

    async def connect_sphero_ollies(
        self,
        configuration: SpheroOllieConnectionConfiguration,
        *,
        nodes: NodeProvider,
    ) -> FabricDiscoveryActionResult:
        async with self._connection_lock:
            message = await self._runner.connect_sphero_ollies(configuration)
        report = await self.scan(nodes())
        return FabricDiscoveryActionResult(
            actionId="cit.sphero-ollie.configure-connect",
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

    async def perform(
        self,
        action_id: str,
        *,
        confirm_grounded: bool,
        session_target: FabricDiscoverySessionTarget | None = None,
    ) -> str:
        del action_id, confirm_grounded, session_target
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

    async def configure_matter_wifi(self, configuration: MatterWifiConfiguration) -> str:
        del configuration
        raise FabricDiscoveryError(
            "MATTER_WIFI_CONFIGURATION_UNAVAILABLE",
            "Local Matter Wi-Fi configuration is unavailable in this runtime",
        )

    async def connect_lego(self, configuration: LegoConnectionConfiguration) -> str:
        del configuration
        raise FabricDiscoveryError(
            "LEGO_CONNECTION_UNAVAILABLE",
            "Local LEGO connection is unavailable in this runtime",
        )

    async def connect_wonder_workshop(
        self, configuration: WonderWorkshopConnectionConfiguration
    ) -> str:
        del configuration
        raise FabricDiscoveryError(
            "WONDER_CONNECTION_UNAVAILABLE",
            "Local Dash and Dot connection is unavailable in this runtime",
        )

    async def connect_sphero_bolts(self, configuration: SpheroBoltConnectionConfiguration) -> str:
        del configuration
        raise FabricDiscoveryError(
            "SPHERO_CONNECTION_UNAVAILABLE",
            "Local Sphero BOLT connection is unavailable in this runtime",
        )

    async def connect_sphero_ollies(self, configuration: SpheroOllieConnectionConfiguration) -> str:
        del configuration
        raise FabricDiscoveryError(
            "SPHERO_OLLIE_CONNECTION_UNAVAILABLE",
            "Local Sphero Ollie connection is unavailable in this runtime",
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
                "cit.even-g2.connect": _LauncherAction(
                    "glasses-agent-hardware-test.ps1",
                    (
                        "-Mode",
                        "Start",
                        *common,
                        "-StateRoot",
                        str(self._state_root.parent / "glasses-agent"),
                        "-SkipBuild",
                        "-NoOpenConsole",
                    ),
                    "The G2 bridge is ready. Keep Tailscale on and open the CIT "
                    "prototype in the paired Even app to confirm the live glasses.",
                ),
                "cit.even-r1.connect": _LauncherAction(
                    "glasses-agent-hardware-test.ps1",
                    (
                        "-Mode",
                        "Start",
                        *common,
                        "-StateRoot",
                        str(self._state_root.parent / "glasses-agent"),
                        "-SkipBuild",
                        "-NoOpenConsole",
                    ),
                    "The R1 input bridge connected through the existing Even and "
                    "Agent Mesh path. Touch the ring once to publish its node.",
                ),
                "cit.glasses-device-control.connect": _LauncherAction(
                    "glasses-agent-hardware-test.ps1",
                    (
                        "-Mode",
                        "Start",
                        *common,
                        "-StateRoot",
                        str(self._state_root.parent / "glasses-agent"),
                        "-SkipBuild",
                        "-NoOpenConsole",
                    ),
                    "The available G2 and Meta inputs were attached to this device-control lesson.",
                ),
                "cit.synchronized-mindwave.connect": _LauncherAction(
                    "brain2devices-fabric-adapters.ps1",
                    (
                        "-Mode",
                        "Start",
                        "-Device",
                        "MindWave",
                        "-MindWaveNodeId",
                        "mindwave-synchronized-01",
                        "-Brain2DevicesRoot",
                        str(self._brain2devices_root),
                        "-StateRoot",
                        str(self._state_root.parent / "synchronized-mindwave-input"),
                        *common,
                        "-CompatibilityApi",
                        "-SkipBuild",
                        "-NoOpenConsole",
                    ),
                    "The connected MindWave was attached to this synchronized-control lesson.",
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
                "cit.wonder-workshop.reconnect": _LauncherAction(
                    "wonder-workshop.ps1",
                    (
                        "-Mode",
                        "Start",
                        *common,
                        "-StateRoot",
                        str(self._state_root.parent / "wonder-workshop"),
                        "-SkipBuild",
                        "-NoOpenConsole",
                    ),
                    "Remembered Dash and Dot profiles reconnected for unarmed sensor "
                    "monitoring. No movement command was issued.",
                ),
                "cit.sphero-bolt.reconnect": _LauncherAction(
                    "sphero-bolt.ps1",
                    (
                        "-Mode",
                        "Start",
                        *common,
                        "-StateRoot",
                        str(self._state_root.parent / "sphero-bolt"),
                        "-SkipBuild",
                        "-NoOpenConsole",
                    ),
                    "Remembered Sphero BOLT profiles reconnected for unarmed sensor "
                    "monitoring. No aim or movement command was issued.",
                ),
                "cit.sphero-ollie.reconnect": _LauncherAction(
                    "sphero-ollie.ps1",
                    (
                        "-Mode",
                        "Start",
                        *common,
                        "-StateRoot",
                        str(self._state_root.parent / "sphero-ollie"),
                        "-SkipBuild",
                        "-NoOpenConsole",
                    ),
                    "Remembered Sphero Ollie profiles reconnected for unarmed sensor "
                    "monitoring. No aim or movement command was issued.",
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

    async def perform(
        self,
        action_id: str,
        *,
        confirm_grounded: bool,
        session_target: FabricDiscoverySessionTarget | None = None,
    ) -> str:
        launcher_action = self._launcher_actions.get(action_id)
        if launcher_action is not None:
            allowed_course_packs = SESSION_TARGET_ACTION_COURSE_PACKS.get(action_id)
            if allowed_course_packs is not None:
                if session_target is None:
                    raise FabricDiscoveryError(
                        "DEVICE_CONTROL_SESSION_REQUIRED",
                        "Set up and select a compatible device-control lesson first",
                    )
                if session_target.coursePackId not in allowed_course_packs:
                    raise FabricDiscoveryError(
                        "DEVICE_CONTROL_SESSION_INVALID",
                        "The selected lesson is not compatible with this input",
                    )
            if action_id == "cit.glasses-device-control.connect":
                target = session_target
                if target is None:
                    raise FabricDiscoveryError(
                        "DEVICE_CONTROL_SESSION_REQUIRED",
                        "Set up and select a compatible device-control lesson first",
                    )
                input_mode = (
                    "-DeviceControlInputOnly"
                    if target.coursePackId == "glasses-device-control"
                    else "-FleetInputOnly"
                )
                await self._run_launcher(
                    launcher_action.script_name,
                    *launcher_action.arguments,
                    input_mode,
                    *(
                        ("-DoNotStartSession",)
                        if target.coursePackId == "synchronized-motor-control"
                        else ()
                    ),
                    "-FabricSessionId",
                    target.sessionId,
                    "-SiteId",
                    target.siteId,
                    "-RoomId",
                    target.roomId,
                )
                return launcher_action.success_message
            if action_id == "cit.synchronized-mindwave.connect":
                target = session_target
                if target is None:
                    raise FabricDiscoveryError(
                        "DEVICE_CONTROL_SESSION_REQUIRED",
                        "Set up and select a compatible device-control lesson first",
                    )
                if not await self._brain.is_connected("mindwave"):
                    await self._brain.post("/api/headset/connect")
                await self._brain.wait_for("mindwave")
                await self._run_launcher(
                    launcher_action.script_name,
                    *launcher_action.arguments,
                    "-DoNotStartSession",
                    "-FabricSessionId",
                    target.sessionId,
                    "-SiteId",
                    target.siteId,
                    "-RoomId",
                    target.roomId,
                )
                return launcher_action.success_message
            attachment = self._fleet_monitoring_attachment()
            if attachment is not None and action_id in {
                "cit.glasses-agent.connect",
                "cit.even-g2.connect",
                "cit.even-r1.connect",
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
                input_name = {
                    "cit.glasses-agent.connect": "G2/Meta",
                    "cit.even-g2.connect": "G2",
                    "cit.even-r1.connect": "R1",
                    "cit.robomaster-leap.connect": "Leap Motion",
                }[action_id]
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
            fallback_reason: (
                Literal[
                    "existing_landed_session",
                    "orphaned_route",
                    "imported_route",
                    "radio_capacity",
                ]
                | None
            ) = None
            try:
                await self._brain.post("/api/fleet/local-radios/auto-connect")
            except FabricDiscoveryError as error:
                if _is_brain2devices_existing_landed_session_refusal(error):
                    fallback_reason = "existing_landed_session"
                elif _is_orphaned_brain2devices_radio_route(error):
                    fallback_reason = "orphaned_route"
                elif _is_brain2devices_imported_radio_route_refusal(error):
                    fallback_reason = "imported_route"
                elif _is_brain2devices_radio_capacity_refusal(error):
                    fallback_reason = "radio_capacity"
                else:
                    raise
                if fallback_reason == "existing_landed_session":
                    # The requested route is already owned by a connected,
                    # landed aircraft. Preserve that valid session instead of
                    # turning a redundant radio reconciliation into a Fabric
                    # connection failure.
                    pass
                elif fallback_reason == "imported_route":
                    # The cached route is explicitly disconnected, so select one
                    # currently visible aircraft for this radio. Grounded
                    # confirmation permits the loss-of-link handoff, and the
                    # Brain2Devices endpoint performs no takeoff.
                    await self._brain.reconnect_first_visible_tello()
                else:
                    # Brain2Devices' preparation path deliberately reconciles the
                    # currently present Windows radio and performs an SDK handshake
                    # without issuing takeoff. It safely repairs an orphaned route
                    # or prepares the first aircraft when radios are scarce.
                    await self._brain.post("/api/fleet/local-radios/fully-automatic/prepare")
            await self._brain.wait_for("tello")
            await self._reconcile_brain_adapters()
            return (
                "Connected Tello sessions now have independent Fabric nodes. "
                + (
                    "The existing Tello session was already connected and landed; "
                    "its Wi-Fi route was left unchanged. "
                    if fallback_reason == "existing_landed_session"
                    else (
                        "The stale Windows radio route was reconciled. "
                        if fallback_reason == "orphaned_route"
                        else (
                            "Brain2Devices prepared the first available Tello from its existing "
                            "safe route. "
                            if fallback_reason == "imported_route"
                            else (
                                "Brain2Devices prepared the first available Tello; the remaining "
                                "visible aircraft need another Wi-Fi adapter or a sequential "
                                "handoff. "
                                if fallback_reason == "radio_capacity"
                                else ""
                            )
                        )
                    )
                )
                + "No takeoff command was sent."
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

    async def configure_matter_wifi(self, configuration: MatterWifiConfiguration) -> str:
        password = configuration.password.get_secret_value()
        await self._run_input_launcher(
            "matter-smart-plug.ps1",
            "-Mode",
            "ConfigureWifi",
            "-SharedFabricRoot",
            str(self._state_root),
            "-FabricPort",
            str(self._fabric_port),
            "-SkipBuild",
            "-NoOpenConsole",
            input_text=json.dumps(
                {"ssid": configuration.ssid, "password": password},
                separators=(",", ":"),
            ),
            redactions=(password,),
            timeout_seconds=45,
            error_prefix="MATTER_WIFI_CONFIGURATION",
            operation_name="Matter Wi-Fi configuration",
            timeout_message="Matter Wi-Fi configuration timed out; retry from the local console",
            failure_message=(
                "Matter Wi-Fi configuration failed; confirm the local controller and credentials"
            ),
        )
        return (
            "Classroom Wi-Fi was stored only in the local Matter controller. "
            "No vendor account or cloud service was used."
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

    async def connect_wonder_workshop(
        self, configuration: WonderWorkshopConnectionConfiguration
    ) -> str:
        await self._run_input_launcher(
            "wonder-workshop.ps1",
            "-Mode",
            "ConfigureStart",
            "-SharedFabricRoot",
            str(self._state_root),
            "-StateRoot",
            str(self._state_root.parent / "wonder-workshop"),
            "-FabricPort",
            str(self._fabric_port),
            "-SkipBuild",
            "-NoOpenConsole",
            input_text=configuration.model_dump_json(),
            redactions=(),
            timeout_seconds=120,
            error_prefix="WONDER_CONNECTION",
            operation_name="Dash/Dot connection",
            timeout_message=(
                "Dash/Dot connection timed out; keep the selected robots awake, nearby, "
                "and disconnected from other apps"
            ),
            failure_message=(
                "Dash/Dot connection failed; check Bluetooth, robot power, and exact selection"
            ),
        )
        count = len(configuration.robots)
        return (
            f"{count} selected Dash/Dot robot(s) connected for unarmed sensor monitoring. "
            "CIT issued no movement command."
        )

    async def connect_sphero_bolts(self, configuration: SpheroBoltConnectionConfiguration) -> str:
        await self._run_input_launcher(
            "sphero-bolt.ps1",
            "-Mode",
            "ConfigureStart",
            "-SharedFabricRoot",
            str(self._state_root),
            "-StateRoot",
            str(self._state_root.parent / "sphero-bolt"),
            "-FabricPort",
            str(self._fabric_port),
            "-SkipBuild",
            "-NoOpenConsole",
            input_text=configuration.model_dump_json(),
            redactions=(),
            timeout_seconds=120,
            error_prefix="SPHERO_CONNECTION",
            operation_name="Sphero BOLT connection",
            timeout_message=(
                "Sphero BOLT connection timed out; keep the selected SB-XXXX robots awake, "
                "nearby, and disconnected from other apps"
            ),
            failure_message=(
                "Sphero BOLT connection failed; check Bluetooth, robot power, and exact selection"
            ),
        )
        count = len(configuration.robots)
        return (
            f"{count} selected Sphero BOLT robot(s) connected for unarmed sensor monitoring. "
            "CIT issued no aim or movement command."
        )

    async def connect_sphero_ollies(self, configuration: SpheroOllieConnectionConfiguration) -> str:
        await self._run_input_launcher(
            "sphero-ollie.ps1",
            "-Mode",
            "ConfigureStart",
            "-SharedFabricRoot",
            str(self._state_root),
            "-StateRoot",
            str(self._state_root.parent / "sphero-ollie"),
            "-FabricPort",
            str(self._fabric_port),
            "-SkipBuild",
            "-NoOpenConsole",
            input_text=configuration.model_dump_json(),
            redactions=(),
            timeout_seconds=120,
            error_prefix="SPHERO_OLLIE_CONNECTION",
            operation_name="Sphero Ollie connection",
            timeout_message=(
                "Sphero Ollie connection timed out; keep the selected 2B-XXXX robots "
                "awake, nearby, and disconnected from other apps"
            ),
            failure_message=(
                "Sphero Ollie connection failed; check Bluetooth, robot power, and exact selection"
            ),
        )
        count = len(configuration.robots)
        return (
            f"{count} selected Sphero Ollie robot(s) connected for unarmed sensor monitoring. "
            "CIT issued no aim or movement command."
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
        try:
            returncode, stdout, stderr = await _run_with_bounded_file_output(
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(launcher),
                *arguments,
                timeout_seconds=DISCOVERY_ACTION_TIMEOUT_SECONDS,
                creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
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
        if returncode != 0:
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
        try:
            returncode, stdout, stderr = await _run_with_bounded_file_output(
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(launcher),
                *arguments,
                timeout_seconds=timeout_seconds,
                input_bytes=input_text.encode("utf-8"),
                creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
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
        if returncode != 0:
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
            "/api/fleet/local-radios/fully-automatic/prepare",
            "/api/drone/connect",
            "/api/headset/connect",
        }
        if path not in allowed:
            raise FabricDiscoveryError(
                "DISCOVERY_ACTION_NOT_ALLOWED",
                "That Brain2Devices operation is not allowlisted",
            )
        await asyncio.to_thread(self._post_sync, path)

    async def reconnect_first_visible_tello(self) -> None:
        """Move a disconnected imported radio to one visible Tello without takeoff."""

        await asyncio.to_thread(self._reconnect_first_visible_tello_sync)

    async def wait_for(self, device: Literal["tello", "mindwave"]) -> None:
        deadline = asyncio.get_running_loop().time() + 70
        while asyncio.get_running_loop().time() < deadline:
            state = await asyncio.to_thread(self._get_state_sync)
            if self._is_connected_state(state, device):
                return
            await asyncio.sleep(0.25)
        raise FabricDiscoveryError(
            "BRAIN2DEVICES_CONNECTION_TIMED_OUT",
            f"Brain2Devices did not finish the {device} connection; check its activity log",
        )

    async def is_connected(self, device: Literal["tello", "mindwave"]) -> bool:
        state = await asyncio.to_thread(self._get_state_sync)
        return self._is_connected_state(state, device)

    async def adapter_device_group(self) -> Literal["All", "Tello", "MindWave"]:
        state = await asyncio.to_thread(self._get_state_sync)
        mindwave_connected = self._is_connected_state(state, "mindwave")
        tello_connected = self._is_connected_state(state, "tello")
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

    @staticmethod
    def _is_connected_state(
        state: Mapping[str, object],
        device: Literal["tello", "mindwave"],
    ) -> bool:
        if device == "mindwave":
            headset = state.get("headset")
            return isinstance(headset, dict) and headset.get("connection") == "connected"
        fleet = state.get("fleet")
        drones = fleet.get("drones") if isinstance(fleet, dict) else None
        return isinstance(drones, list) and any(
            isinstance(drone, dict) and drone.get("connection") == "connected" for drone in drones
        )

    def _reconnect_first_visible_tello_sync(self) -> None:
        scan = self._post_json_sync("/api/fleet/local-radios/scan", {})
        adapters = scan.get("adapters")
        if not isinstance(adapters, list):
            raise FabricDiscoveryError(
                "BRAIN2DEVICES_RESPONSE_INVALID",
                "Brain2Devices radio scan did not return an adapter list",
            )
        candidates: list[tuple[int, str, str]] = []
        for adapter in adapters:
            if not isinstance(adapter, dict):
                continue
            interface = adapter.get("interface_name")
            network = adapter.get("recommended_tello_network")
            if not isinstance(interface, str) or not isinstance(network, str):
                continue
            interface = interface.strip()
            network = network.strip()
            if (
                not interface
                or len(interface) > 128
                or any(ord(character) < 32 for character in interface)
                or not network.upper().startswith(("TELLO-", "RMTT-"))
                or len(network) > 128
                or any(ord(character) < 32 for character in network)
            ):
                continue
            interface_index = adapter.get("interface_index")
            rank = interface_index if isinstance(interface_index, int) else 2**31 - 1
            candidates.append((rank, interface, network))
        if not candidates:
            raise FabricDiscoveryError(
                "BRAIN2DEVICES_CONNECTION_REJECTED",
                "No safe visible Tello radio assignment is available; scan again",
            )
        _rank, interface, network = min(
            candidates,
            key=lambda candidate: (candidate[0], candidate[1].casefold()),
        )
        self._post_json_sync(
            "/api/fleet/local-radios/sequential-switch",
            {
                "interface_name": interface,
                "ssid": network,
                "label": network,
                "accept_loss_of_link": True,
            },
        )

    def _post_sync(self, path: str) -> None:
        self._post_json_sync(path, {})

    def _post_json_sync(
        self,
        path: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        allowed = {
            "/api/fleet/local-radios/auto-connect",
            "/api/fleet/local-radios/fully-automatic/prepare",
            "/api/fleet/local-radios/scan",
            "/api/fleet/local-radios/sequential-switch",
            "/api/drone/connect",
            "/api/headset/connect",
        }
        if path not in allowed:
            raise FabricDiscoveryError(
                "DISCOVERY_ACTION_NOT_ALLOWED",
                "That Brain2Devices operation is not allowlisted",
            )
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
                data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
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
            return body
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
            "imagePath": descriptor.imagePath,
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


def _policy_has_live_node(
    policy: RememberedConnectionPolicy,
    nodes: Iterable[IntegrationNode],
) -> bool:
    catalog = load_integration_catalog()
    descriptors = tuple(catalog.require(value) for value in policy.integration_ids)
    return any(
        node.connectionState.value in {"connected", "degraded"}
        and any(descriptor.matches(node) for descriptor in descriptors)
        for node in nodes
    )


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
                    "imagePath": descriptor.imagePath,
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
