from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cit_brain2devices_demo.fleet_backend import (
    Brain2DevicesApiFleetSequenceBackend,
    FleetSequenceBackend,
    SimulatedFleetSequenceBackend,
)
from cit_brain2devices_demo.fleet_bridge import FleetSequenceCommandHandler
from cit_brain2devices_demo.fleet_contract import (
    ARM_CAPABILITY,
    START_CAPABILITY,
    STATUS_CAPABILITY,
    STOP_CAPABILITY,
    build_manifest,
    build_node,
)
from cit_protocol import FabricResolvedCommand

NOW = datetime(2026, 8, 23, 6, 0, 0, tzinfo=UTC)


def command(
    action: str,
    *,
    parameters: dict[str, object] | None = None,
    priority: str = "instructor_override",
    source_node_id: str | None = None,
) -> FabricResolvedCommand:
    now = datetime.now(UTC)
    return FabricResolvedCommand.model_validate(
        {
            "commandId": str(uuid4()),
            "requestMessageId": str(uuid4()),
            "schemaVersion": "1.0",
            "sessionId": "session-a",
            "targetNodeId": "fleet-sequence-a",
            "action": action,
            "parameters": parameters or {},
            "priority": priority,
            "idempotencyKey": str(uuid4()),
            "requestedAt": now,
            "expiresAt": now + timedelta(seconds=2),
            "safetyProfile": "classroom-drone-monitoring",
            "correlationId": str(uuid4()),
            "sourceNodeId": source_node_id,
        }
    )


def arm_settings(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "droneIds": ["primary", "drone-2", "drone-3"],
        "allowedSourceNodeIds": ["leap-a", "g2-a", "meta-a"],
        "launchIntervalSeconds": 2,
        "minimumBatteryPercent": 30,
        "instructorPresent": True,
        "flightAreaClear": True,
        "emergencyPlanReady": True,
        "independentRoutesConfirmed": True,
    }
    value.update(updates)
    return value


def test_fleet_controller_contract_exposes_only_the_bounded_sequence() -> None:
    manifest = build_manifest()
    node = build_node(
        at=NOW,
        host_id="host-a",
        site_id="local-site",
        room_id="local-room",
        node_id="fleet-sequence-a",
        simulated=False,
    )

    assert manifest.pluginId == node.pluginId == "cit.brain2devices-fleet"
    assert {item.name for item in node.consumedCapabilities} == {
        ARM_CAPABILITY,
        START_CAPABILITY,
        STOP_CAPABILITY,
    }
    assert {item.name for item in node.publishedCapabilities} == {STATUS_CAPABILITY}
    assert all(
        forbidden not in item.name
        for item in node.consumedCapabilities
        for forbidden in (".takeoff", ".move", ".rotate")
    )
    assert node.metadata.model_dump(mode="json") == {
        "brain2devicesRevision": node.metadata.model_dump(mode="json")["brain2devicesRevision"],
        "transport": "brain2devices-loopback-api",
        "oneShot": True,
        "requiresInstructorArm": True,
        "maximumAircraft": 8,
        "unrestrictedFlightCommands": False,
    }


@pytest.mark.asyncio
async def test_simulated_sequence_requires_arm_and_launches_once_in_selected_order() -> None:
    async def no_wait(_seconds: float) -> None:
        await asyncio.sleep(0)

    backend = SimulatedFleetSequenceBackend(
        drone_ids=("primary", "drone-2", "drone-3"),
        sleep=no_wait,
    )
    handler = FleetSequenceCommandHandler(backend, node_id="fleet-sequence-a")
    await backend.start()

    with pytest.raises(ValueError, match="not armed"):
        await handler.execute(
            command(
                START_CAPABILITY,
                priority="lesson_automation",
                source_node_id="leap-a",
            )
        )

    armed = await handler.execute(command(ARM_CAPABILITY, parameters=arm_settings()))
    assert armed["armed"] is True

    accepted = await handler.execute(
        command(
            START_CAPABILITY,
            priority="lesson_automation",
            source_node_id="g2-a",
        )
    )
    assert accepted["triggeredBy"] == "g2-a"
    for _ in range(20):
        if (await backend.status())["phase"] == "completed":
            break
        await asyncio.sleep(0)

    status = await backend.status()
    assert status["phase"] == "completed"
    assert status["launchedDroneIds"] == ["primary", "drone-2", "drone-3"]
    assert backend.command_log == [
        "takeoff:primary",
        "takeoff:drone-2",
        "takeoff:drone-3",
    ]
    assert status["armed"] is False

    with pytest.raises(ValueError, match="not armed"):
        await handler.execute(
            command(
                START_CAPABILITY,
                priority="lesson_automation",
                source_node_id="meta-a",
            )
        )


@pytest.mark.asyncio
async def test_single_drone_sequence_can_be_armed_for_an_r1_trigger() -> None:
    async def no_wait(_seconds: float) -> None:
        await asyncio.sleep(0)

    backend = SimulatedFleetSequenceBackend(
        drone_ids=("primary",),
        sleep=no_wait,
    )
    handler = FleetSequenceCommandHandler(backend, node_id="fleet-sequence-a")
    await backend.start()
    settings = arm_settings(
        droneIds=["primary"],
        allowedSourceNodeIds=["r1-a"],
    )

    armed = await handler.execute(command(ARM_CAPABILITY, parameters=settings))
    started = await handler.execute(
        command(
            START_CAPABILITY,
            priority="lesson_automation",
            source_node_id="r1-a",
        )
    )
    for _ in range(20):
        if (await backend.status())["phase"] == "completed":
            break
        await asyncio.sleep(0)

    assert armed["armed"] is True
    assert started["triggeredBy"] == "r1-a"
    assert backend.command_log == ["takeoff:primary"]


class FakeBrain2DevicesFleetApi:
    def __init__(self, *, reject_drone_id: str | None = None) -> None:
        self.opened = False
        self.reject_drone_id = reject_drone_id
        self.commands: list[tuple[str, tuple[str, ...]]] = []
        self.drones: dict[str, dict[str, object]] = {
            drone_id: {
                "id": drone_id,
                "label": label,
                "connection": "connected",
                "flight": "landed",
                "telemetry": {"battery_percent": battery},
                "command_error": None,
            }
            for drone_id, label, battery in (
                ("primary", "Front Tello", 84),
                ("drone-2", "Middle Tello", 78),
                ("drone-3", "Rear Tello", 72),
            )
        }

    async def open(self) -> None:
        self.opened = True

    async def state(self) -> Mapping[str, object]:
        return {"fleet": {"drones": [dict(drone) for drone in self.drones.values()]}}

    async def fleet_command(self, action: str, drone_ids: Sequence[str]) -> Mapping[str, object]:
        target_ids = tuple(drone_ids)
        self.commands.append((action, target_ids))
        for drone_id in target_ids:
            drone = self.drones[drone_id]
            if action == "takeoff":
                if drone_id == self.reject_drone_id:
                    drone["command_error"] = {
                        "title": "Takeoff failed",
                        "detail": "motor stop",
                    }
                else:
                    drone["flight"] = "flying"
            elif action == "land":
                drone["flight"] = "landed"
        return {"accepted": True}


@pytest.mark.asyncio
async def test_physical_controller_is_available_with_one_connected_tello() -> None:
    api = FakeBrain2DevicesFleetApi()
    api.drones = {"primary": api.drones["primary"]}
    backend = Brain2DevicesApiFleetSequenceBackend(api=api)

    status = await backend.start()

    assert status["available"] is True
    assert status["phase"] == "idle"
    available = status["availableDrones"]
    assert isinstance(available, list)
    assert [drone["id"] for drone in available if isinstance(drone, Mapping)] == ["primary"]


@pytest.mark.asyncio
@pytest.mark.parametrize("backend_kind", ["simulation", "physical"])
async def test_fleet_arm_expires_independently_of_the_session(backend_kind: str) -> None:
    monotonic_now = [10.0]

    async def no_wait(_seconds: float) -> None:
        await asyncio.sleep(0)

    backend: FleetSequenceBackend
    if backend_kind == "simulation":
        backend = SimulatedFleetSequenceBackend(
            drone_ids=("primary", "drone-2", "drone-3"),
            sleep=no_wait,
            monotonic=lambda: monotonic_now[0],
            arm_ttl_seconds=60,
        )
    else:
        backend = Brain2DevicesApiFleetSequenceBackend(
            api=FakeBrain2DevicesFleetApi(),
            sleep=no_wait,
            monotonic=lambda: monotonic_now[0],
            arm_ttl_seconds=60,
        )
    await backend.start()
    await backend.arm(arm_settings())
    monotonic_now[0] = 71.0

    status = await backend.status()

    assert status["armed"] is False
    assert status["active"] is False
    assert status["phase"] == "expired"
    with pytest.raises(ValueError, match="not armed"):
        await backend.trigger(source_node_id="leap-a")


@pytest.mark.asyncio
async def test_physical_sequence_confirms_each_takeoff_and_lands_on_partial_failure() -> None:
    async def no_wait(_seconds: float) -> None:
        await asyncio.sleep(0)

    api = FakeBrain2DevicesFleetApi(reject_drone_id="drone-2")
    backend = Brain2DevicesApiFleetSequenceBackend(api=api, sleep=no_wait)
    await backend.start()
    await backend.arm(arm_settings())
    await backend.trigger(source_node_id="leap-a")

    for _ in range(30):
        if (await backend.status())["phase"] == "failed":
            break
        await asyncio.sleep(0)

    status = await backend.status()
    assert status["phase"] == "failed"
    assert "drone-2" in str(status["error"])
    assert api.commands == [
        ("takeoff", ("primary",)),
        ("takeoff", ("drone-2",)),
        ("land", ("primary",)),
        ("land", ("drone-2",)),
    ]
    assert api.drones["primary"]["flight"] == "landed"


@pytest.mark.asyncio
async def test_physical_stop_cancels_the_remaining_order_and_lands_every_selection() -> None:
    first_launch_confirmed = asyncio.Event()
    release_spacing = asyncio.Event()

    async def controlled_wait(seconds: float) -> None:
        if seconds >= 1:
            first_launch_confirmed.set()
            await release_spacing.wait()
        else:
            await asyncio.sleep(0)

    api = FakeBrain2DevicesFleetApi()
    backend = Brain2DevicesApiFleetSequenceBackend(api=api, sleep=controlled_wait)
    await backend.start()
    await backend.arm(arm_settings())
    await backend.trigger(source_node_id="meta-a")
    await asyncio.wait_for(first_launch_confirmed.wait(), timeout=1)

    status = await backend.stop(reason="instructor_button")

    assert status["phase"] == "stopped"
    assert status["armed"] is False
    assert status["active"] is False
    assert api.commands == [
        ("takeoff", ("primary",)),
        ("land", ("primary",)),
        ("land", ("drone-2",)),
        ("land", ("drone-3",)),
    ]


@pytest.mark.asyncio
async def test_trigger_rejects_an_unarmed_source_and_deduplicates_an_allowed_source() -> None:
    release_spacing = asyncio.Event()

    async def controlled_wait(_seconds: float) -> None:
        await release_spacing.wait()

    backend = SimulatedFleetSequenceBackend(
        drone_ids=("primary", "drone-2", "drone-3"),
        sleep=controlled_wait,
    )
    handler = FleetSequenceCommandHandler(backend, node_id="fleet-sequence-a")
    await backend.start()
    await handler.execute(command(ARM_CAPABILITY, parameters=arm_settings()))

    with pytest.raises(ValueError, match="not allowed"):
        await handler.execute(
            command(
                START_CAPABILITY,
                priority="lesson_automation",
                source_node_id="unknown-input",
            )
        )
    assert (await backend.status())["armed"] is True

    accepted_command = command(
        START_CAPABILITY,
        priority="lesson_automation",
        source_node_id="g2-a",
    )
    first = await handler.execute(accepted_command)
    duplicate = await handler.execute(accepted_command)

    assert first["duplicatePrevented"] is False
    assert duplicate == {"duplicatePrevented": True}
    await asyncio.sleep(0)
    assert backend.command_log == ["takeoff:primary"]
    await backend.stop(reason="test_cleanup")
