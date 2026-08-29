"""Unattended reconnection of remembered adapters that opted in."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from cit_protocol import IntegrationNode
from cit_runtime.fabric import InteractionFabric
from cit_runtime.fabric_discovery import (
    AUTO_RECONNECT_BASE_DELAY_SECONDS,
    AUTO_RECONNECT_MAX_DELAY_SECONDS,
    FabricDiscoveryError,
    FabricDiscoveryReport,
    FabricDiscoveryService,
    FabricDiscoverySessionTarget,
    FabricRememberedConnection,
    LegoConnectionConfiguration,
    MatterWifiConfiguration,
    SpheroBoltConnectionConfiguration,
    SpheroOllieConnectionConfiguration,
    WonderWorkshopConnectionConfiguration,
    auto_reconnect_delay_seconds,
    initial_discovery_report,
)
from cit_runtime.fabric_repository import SQLiteFabricRepository
from cit_runtime.fabric_service import supervise_remembered_reconnects

NOW = datetime(2026, 8, 21, 7, 0, 0, tzinfo=UTC)
PLUG_ACTION = "cit.matter-smart-plug.connect"
SAFE_REMEMBERED_ACTIONS = (
    "cit.glasses-agent.connect",
    "cit.even-g2.connect",
    "cit.even-r1.connect",
    "cit.robomaster-leap.connect",
    PLUG_ACTION,
    "cit.lego-pybricks.connect",
    "cit.wonder-workshop.reconnect",
    "cit.sphero-bolt.reconnect",
    "cit.sphero-ollie.reconnect",
    "brain2devices.mindwave.connect",
)


class RecordingRunner:
    """Records every attempted action and always refuses to connect."""

    def __init__(self) -> None:
        self.actions: list[tuple[str, bool]] = []
        self.scans = 0

    async def scan(self) -> FabricDiscoveryReport:
        self.scans += 1
        return initial_discovery_report(at=NOW)

    async def perform(
        self,
        action_id: str,
        *,
        confirm_grounded: bool,
        session_target: FabricDiscoverySessionTarget | None = None,
    ) -> str:
        self.actions.append((action_id, confirm_grounded))
        raise FabricDiscoveryError(
            "DISCOVERY_ACTION_NOT_ALLOWED",
            "The adapter is still unavailable.",
        )

    async def configure_matter_wifi(self, configuration: MatterWifiConfiguration) -> str:
        raise NotImplementedError

    async def commission_matter(self, setup_code: str) -> str:
        raise NotImplementedError

    async def connect_lego(self, configuration: LegoConnectionConfiguration) -> str:
        raise NotImplementedError

    async def connect_wonder_workshop(
        self, configuration: WonderWorkshopConnectionConfiguration
    ) -> str:
        raise NotImplementedError

    async def connect_sphero_bolts(self, configuration: SpheroBoltConnectionConfiguration) -> str:
        raise NotImplementedError

    async def connect_sphero_ollies(self, configuration: SpheroOllieConnectionConfiguration) -> str:
        raise NotImplementedError


def _remembered(action_id: str) -> FabricRememberedConnection:
    return FabricRememberedConnection(
        actionId=action_id,
        requiresGroundedConfirmation=False,
        rememberedAt=NOW,
    )


def test_auto_reconnect_delay_grows_exponentially_then_caps() -> None:
    assert auto_reconnect_delay_seconds(0) == AUTO_RECONNECT_BASE_DELAY_SECONDS
    assert auto_reconnect_delay_seconds(1) == AUTO_RECONNECT_BASE_DELAY_SECONDS * 2
    assert auto_reconnect_delay_seconds(2) == AUTO_RECONNECT_BASE_DELAY_SECONDS * 4
    assert auto_reconnect_delay_seconds(99) == AUTO_RECONNECT_MAX_DELAY_SECONDS


def test_supervisor_attempts_every_remembered_non_aircraft_profile() -> None:
    runner = RecordingRunner()
    service = FabricDiscoveryService(runner, clock=lambda: NOW)

    asyncio.run(
        service.supervise_remembered_reconnects(
            tuple(_remembered(action_id) for action_id in SAFE_REMEMBERED_ACTIONS),
            nodes=lambda: (),
        )
    )

    assert runner.actions == [(action_id, False) for action_id in SAFE_REMEMBERED_ACTIONS]
    assert runner.scans == 0


def test_supervisor_never_confirms_grounded_aircraft() -> None:
    runner = RecordingRunner()
    service = FabricDiscoveryService(runner, clock=lambda: NOW)

    result = asyncio.run(
        service.supervise_remembered_reconnects(
            (_remembered("brain2devices.tello.connect-all"),),
            nodes=lambda: (),
        )
    )

    assert runner.actions == []
    assert result.connectedCount == 0


def test_supervisor_backs_off_after_a_failed_attempt() -> None:
    runner = RecordingRunner()
    service = FabricDiscoveryService(runner, clock=lambda: NOW)
    remembered = (_remembered(PLUG_ACTION),)

    async def scenario() -> None:
        await service.supervise_remembered_reconnects(remembered, nodes=lambda: ())
        await service.supervise_remembered_reconnects(remembered, nodes=lambda: ())

    asyncio.run(scenario())

    assert runner.actions == [(PLUG_ACTION, False)]


def test_supervisor_retries_once_the_backoff_delay_elapses() -> None:
    runner = RecordingRunner()
    moment = {"now": NOW}
    service = FabricDiscoveryService(runner, clock=lambda: moment["now"])
    remembered = (_remembered(PLUG_ACTION),)

    asyncio.run(service.supervise_remembered_reconnects(remembered, nodes=lambda: ()))
    moment["now"] = NOW + timedelta(seconds=AUTO_RECONNECT_MAX_DELAY_SECONDS + 1)
    asyncio.run(service.supervise_remembered_reconnects(remembered, nodes=lambda: ()))

    assert runner.actions == [(PLUG_ACTION, False), (PLUG_ACTION, False)]


def test_service_supervisor_reconnects_a_remembered_plug_without_a_principal() -> None:
    runner = RecordingRunner()
    discovery = FabricDiscoveryService(runner, clock=lambda: NOW)
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW)
        report = discovery.current(fabric.list_nodes())
        repository.remember_fabric_connection(
            host_id=report.hostId,
            reconnect_action_id=PLUG_ACTION,
            requires_grounded_confirmation=False,
            remembered_at=NOW,
            remembered_by="runtime-node-history",
        )

        asyncio.run(supervise_remembered_reconnects(fabric, repository, discovery))

    assert runner.actions == [(PLUG_ACTION, False)]
    assert runner.scans == 0


class RecoveringRunner(RecordingRunner):
    """Fails until `succeed_from` attempts have been made."""

    def __init__(self, succeed_from: int) -> None:
        super().__init__()
        self._succeed_from = succeed_from

    async def perform(
        self,
        action_id: str,
        *,
        confirm_grounded: bool,
        session_target: FabricDiscoverySessionTarget | None = None,
    ) -> str:
        self.actions.append((action_id, confirm_grounded))
        if len(self.actions) >= self._succeed_from:
            return "Connection started; no actuation command was sent."
        raise FabricDiscoveryError(
            "DISCOVERY_ACTION_NOT_ALLOWED",
            "The adapter is still unavailable.",
        )


def test_supervisor_reports_only_the_first_failure_of_a_streak() -> None:
    runner = RecordingRunner()
    moment = {"now": NOW}
    service = FabricDiscoveryService(runner, clock=lambda: moment["now"])
    remembered = (_remembered(PLUG_ACTION),)
    seen: list[tuple[str, str]] = []

    async def scenario() -> None:
        for _ in range(3):
            await service.supervise_remembered_reconnects(
                remembered,
                nodes=lambda: (),
                on_transition=lambda action_id, status: seen.append((action_id, status)),
            )
            moment["now"] += timedelta(seconds=AUTO_RECONNECT_MAX_DELAY_SECONDS + 1)

    asyncio.run(scenario())

    assert len(runner.actions) == 3
    assert seen == [(PLUG_ACTION, "failed")]


def test_supervisor_reports_the_recovery_after_a_failure() -> None:
    runner = RecoveringRunner(succeed_from=2)
    moment = {"now": NOW}
    service = FabricDiscoveryService(runner, clock=lambda: moment["now"])
    remembered = (_remembered(PLUG_ACTION),)
    seen: list[tuple[str, str]] = []

    async def scenario() -> None:
        for _ in range(2):
            await service.supervise_remembered_reconnects(
                remembered,
                nodes=lambda: (),
                on_transition=lambda action_id, status: seen.append((action_id, status)),
            )
            moment["now"] += timedelta(seconds=AUTO_RECONNECT_MAX_DELAY_SECONDS + 1)

    asyncio.run(scenario())

    assert seen == [(PLUG_ACTION, "failed"), (PLUG_ACTION, "connected")]


def test_supervisor_reports_nothing_for_a_profile_it_never_attempts() -> None:
    runner = RecordingRunner()
    service = FabricDiscoveryService(runner, clock=lambda: NOW)
    seen: list[tuple[str, str]] = []

    asyncio.run(
        service.supervise_remembered_reconnects(
            (_remembered("brain2devices.tello.connect-all"),),
            nodes=lambda: (),
            on_transition=lambda action_id, status: seen.append((action_id, status)),
        )
    )

    assert runner.actions == []
    assert seen == []


def test_service_supervisor_audits_a_reconnect_transition() -> None:
    runner = RecordingRunner()
    discovery = FabricDiscoveryService(runner, clock=lambda: NOW)
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW)
        report = discovery.current(fabric.list_nodes())
        repository.remember_fabric_connection(
            host_id=report.hostId,
            reconnect_action_id=PLUG_ACTION,
            requires_grounded_confirmation=False,
            remembered_at=NOW,
            remembered_by="runtime-node-history",
        )

        asyncio.run(supervise_remembered_reconnects(fabric, repository, discovery))

        records = repository.list_fabric_audit(limit=10)

    supervised = [
        record for record in records if record.action == "fabric.discovery.reconnect_remembered"
    ]
    assert len(supervised) == 1
    assert supervised[0].actor_id == "system.reconnect-supervisor"
    assert supervised[0].outcome == "failed"


def _plug_node(node_id: str, *, state: str, last_seen: datetime) -> IntegrationNode:
    return IntegrationNode.model_validate(
        {
            "schemaVersion": "1.0",
            "nodeId": node_id,
            "pluginId": "cit.matter-smart-plug",
            "pluginVersion": "0.1.0",
            "runtimeVersion": "python-3.11",
            "displayName": "Smart Wi-Fi Plug",
            "hostId": "test-host",
            "siteId": "local-site",
            "roomId": "local-room",
            "connectionState": state,
            "healthState": "healthy",
            "physical": True,
            "simulated": False,
            "publishedCapabilities": [],
            "consumedCapabilities": [
                {
                    "name": "power.switch.set",
                    "version": "1.0",
                    "direction": "consume",
                    "latencyClass": "interactive",
                    "safetyClassification": "electrical",
                    "dataClassification": "operational",
                    "constraints": {},
                }
            ],
            "configurationSchema": {},
            "safetyClassification": "electrical",
            "dataClassifications": ["operational"],
            "simulatorAvailable": False,
            "requiredPermissions": [],
            "lastSeenAt": last_seen,
            "metadata": {},
        }
    )


def test_a_recently_dropped_plug_is_retried_even_though_its_sibling_is_live() -> None:
    """One healthy plug must not mask a sibling that just dropped.

    The live-node check is per integration, so a partially connected Matter
    fabric used to report already_connected and never recover the dropped
    endpoint -- for the console button as much as for the supervisor.
    """

    runner = RecordingRunner()
    service = FabricDiscoveryService(runner, clock=lambda: NOW)
    nodes = (
        _plug_node("matter-8-ep1", state="connected", last_seen=NOW),
        _plug_node(
            "matter-c-ep1",
            state="disconnected",
            last_seen=NOW - timedelta(minutes=4),
        ),
    )

    asyncio.run(
        service.supervise_remembered_reconnects(
            (_remembered(PLUG_ACTION),),
            nodes=lambda: nodes,
        )
    )

    assert runner.actions == [(PLUG_ACTION, False)]


def test_a_long_gone_node_is_not_retried_while_a_sibling_is_live() -> None:
    """Stale records must not relaunch an adapter that is working.

    Relaunching the Matter adapter briefly drops every endpoint it owns, so a
    device absent for days must not keep bouncing the plugs that are fine.
    """

    runner = RecordingRunner()
    service = FabricDiscoveryService(runner, clock=lambda: NOW)
    nodes = (
        _plug_node("matter-8-ep1", state="connected", last_seen=NOW),
        _plug_node(
            "matter-c-ep1",
            state="disconnected",
            last_seen=NOW - timedelta(days=3),
        ),
    )

    asyncio.run(
        service.supervise_remembered_reconnects(
            (_remembered(PLUG_ACTION),),
            nodes=lambda: nodes,
        )
    )

    assert runner.actions == []


def test_a_fully_connected_integration_is_left_alone() -> None:
    runner = RecordingRunner()
    service = FabricDiscoveryService(runner, clock=lambda: NOW)
    nodes = (
        _plug_node("matter-8-ep1", state="connected", last_seen=NOW),
        _plug_node("matter-c-ep1", state="connected", last_seen=NOW),
    )

    asyncio.run(
        service.supervise_remembered_reconnects(
            (_remembered(PLUG_ACTION),),
            nodes=lambda: nodes,
        )
    )

    assert runner.actions == []
