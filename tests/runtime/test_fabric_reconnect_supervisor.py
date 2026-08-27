"""Unattended reconnection of remembered adapters that opted in."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

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


def test_supervisor_attempts_only_policies_marked_auto_reconnect() -> None:
    runner = RecordingRunner()
    service = FabricDiscoveryService(runner, clock=lambda: NOW)

    asyncio.run(
        service.supervise_remembered_reconnects(
            (_remembered("cit.robomaster-leap.connect"), _remembered(PLUG_ACTION)),
            nodes=lambda: (),
        )
    )

    assert runner.actions == [(PLUG_ACTION, False)]
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
