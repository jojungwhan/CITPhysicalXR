"""A LEGO hub inside the real runtime: pipeline, safety, and coordination.

The hub here is the in-memory one from `cit_lego_pybricks.fakes`, so no radio
and no LEGO hardware is involved. What is being proved is that a real adapter
plugged into the Milestone 1 pipeline is bound by the same gates as everything
else: it cannot move unarmed, it is clamped, it is stopped by the watchdog, and
a command for it never reaches the robot beside it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from cit_device_simulator import create_fake_s1_adapter
from cit_lego_pybricks import (
    FakeHubTransport,
    HubBinding,
    Operation,
    PortKind,
    PybricksDiscoveryProvider,
    PybricksHubAdapter,
    hub_model,
)
from cit_runtime import ManualClock, Runtime, SafetyPolicy
from cit_runtime.config import ConfigurationError
from cit_runtime.physical_devices import (
    LEGO_STUDENT_POLICY,
    build_providers,
    lego_bindings,
    runtime_from_config,
)
from cit_runtime.sessions import ExecutionMode
from cit_runtime.supervisor import MotionBounds, WatchdogKind
from conftest import make_command

PORTS = {
    "A": PortKind.MOTOR,
    "B": PortKind.MOTOR,
    "C": PortKind.DISTANCE,
    "D": PortKind.EMPTY,
    "E": PortKind.EMPTY,
    "F": PortKind.EMPTY,
}

LEGO_POLICY = SafetyPolicy(
    policy_id="lego-student",
    bounds=MotionBounds(max_speed=0.5, max_duration_seconds=2.0),
)


@pytest.fixture
def transport() -> FakeHubTransport:
    return FakeHubTransport(hub_name="cit-hub-1", model=hub_model("spike-prime"), ports=PORTS)


@pytest.fixture
def lego_runtime(clock: ManualClock, transport: FakeHubTransport) -> Runtime:
    hub = PybricksHubAdapter(
        device_id="lego-spike-01",
        display_name="Class hub 1",
        transport=transport,
        model=hub_model("spike-prime"),
        ports=PORTS,
    )
    s1 = create_fake_s1_adapter()
    s1.physical = True
    return Runtime(
        clock=clock,
        adapters=(hub, s1),
        policies=(LEGO_POLICY,),
        physical_enabled=True,
    )


async def ready_session(runtime: Runtime, *devices: str) -> str:
    await runtime.start()
    session = runtime.create_session(
        project_id="lego-lesson",
        user_id="student-1",
        execution_mode=ExecutionMode.PHYSICAL,
        instructor_id="teacher-1",
        safety_policy_id="lego-student",
    )
    runtime.bind_devices(session.session_id, list(devices))
    runtime.advance_to_ready(session.session_id)
    return session.session_id


def motor_command(session_id: str, **overrides: Any) -> Any:
    arguments = overrides.pop("arguments", {"port": "A", "speed": 0.3, "durationSeconds": 1.0})
    return make_command(
        session_id=session_id,
        device_id="lego-spike-01",
        capability="motor.run",
        arguments=arguments,
        policy_id="lego-student",
        **overrides,
    )


@pytest.mark.asyncio
async def test_a_hub_joins_the_registry_as_a_physical_device(lego_runtime: Runtime) -> None:
    await lego_runtime.start()

    device = lego_runtime.registry.get("lego-spike-01")

    assert device.physical is True
    assert device.state.value == "connected"
    assert "motor.run" in {capability.root for capability in device.descriptor.capabilities}


@pytest.mark.asyncio
async def test_an_unarmed_hub_refuses_to_move(
    lego_runtime: Runtime, transport: FakeHubTransport
) -> None:
    session_id = await ready_session(lego_runtime, "lego-spike-01")

    dispatch = await lego_runtime.submit(motor_command(session_id))

    assert dispatch.accepted is False
    assert dispatch.error is not None
    assert dispatch.error.code == "DEVICE_NOT_ARMED"
    assert [frame.operation for frame in transport.received] == [Operation.HELLO]


@pytest.mark.asyncio
async def test_an_armed_hub_moves_and_the_frame_is_clamped_by_the_policy(
    lego_runtime: Runtime, transport: FakeHubTransport
) -> None:
    session_id = await ready_session(lego_runtime, "lego-spike-01")
    lego_runtime.arm(session_id=session_id, device_id="lego-spike-01", instructor_id="teacher-1")

    dispatch = await lego_runtime.submit(
        motor_command(
            session_id, arguments={"port": "A", "speed": 0.9, "durationSeconds": 30}, armed=True
        )
    )

    assert dispatch.accepted is True
    assert sorted(dispatch.clamped_fields) == ["durationSeconds", "speed"]
    # 0.9 was clamped to the profile's 0.5 before the adapter saw it, and the
    # adapter turned that into hub percent.
    runs = [
        frame.arguments for frame in transport.received if frame.operation is Operation.MOTOR_RUN
    ]
    assert runs == [("A", "50", "2000")]


@pytest.mark.asyncio
async def test_stop_all_reaches_the_hub(lego_runtime: Runtime, transport: FakeHubTransport) -> None:
    session_id = await ready_session(lego_runtime, "lego-spike-01")
    lego_runtime.arm(session_id=session_id, device_id="lego-spike-01", instructor_id="teacher-1")
    await lego_runtime.submit(motor_command(session_id, armed=True))

    stopped = await lego_runtime.stop_all(actor_id="teacher-1")

    assert "lego-spike-01" in stopped
    assert transport.motors_running is False
    assert transport.stops[-1] == "instructor stop-all"


@pytest.mark.asyncio
async def test_the_lego_watchdog_stops_the_hub_after_its_own_timeout(
    lego_runtime: Runtime, clock: ManualClock, transport: FakeHubTransport
) -> None:
    """FR-070 gives LEGO continuous motion 500 ms."""

    session_id = await ready_session(lego_runtime, "lego-spike-01")
    lego_runtime.arm(session_id=session_id, device_id="lego-spike-01", instructor_id="teacher-1")
    await lego_runtime.submit(motor_command(session_id, armed=True))
    lego_runtime.heartbeat(device_id="lego-spike-01", kind=WatchdogKind.LEGO_CONTINUOUS_MOTION)

    clock.advance(0.4)
    await lego_runtime.tick()
    assert transport.motors_running is True

    clock.advance(0.2)
    await lego_runtime.tick()

    assert transport.motors_running is False
    assert lego_runtime.supervisor.is_armed("lego-spike-01") is False


@pytest.mark.asyncio
async def test_the_runtime_tick_keeps_the_hub_link_alive(
    lego_runtime: Runtime, clock: ManualClock, transport: FakeHubTransport
) -> None:
    await lego_runtime.start()

    clock.advance(0.3)
    await lego_runtime.tick()

    heartbeats = [frame for frame in transport.received if frame.operation is Operation.HEARTBEAT]
    assert len(heartbeats) == 1


@pytest.mark.asyncio
async def test_one_program_drives_the_hub_and_the_s1_without_crossing_them(
    lego_runtime: Runtime, transport: FakeHubTransport
) -> None:
    """AC-13 in simulation: exact routing, and one failure does not retarget."""

    session_id = await ready_session(lego_runtime, "lego-spike-01", "fake-s1-main")
    for device_id in ("lego-spike-01", "fake-s1-main"):
        lego_runtime.arm(session_id=session_id, device_id=device_id, instructor_id="teacher-1")

    lego = await lego_runtime.submit(motor_command(session_id, armed=True))
    s1 = await lego_runtime.submit(
        make_command(
            session_id=session_id,
            device_id="fake-s1-main",
            capability="drive.velocity",
            arguments={"speed": 0.2, "durationSeconds": 1.0},
            policy_id="lego-student",
            armed=True,
        )
    )
    # The S1 has no motor.run capability; asking it for one must fail on the S1
    # rather than quietly land on the hub that does.
    misrouted = await lego_runtime.submit(
        make_command(
            session_id=session_id,
            device_id="fake-s1-main",
            capability="motor.run",
            arguments={"port": "A", "speed": 0.2},
            policy_id="lego-student",
            armed=True,
        )
    )

    assert lego.accepted is True
    assert s1.accepted is True
    assert misrouted.accepted is False
    assert misrouted.result is not None
    assert misrouted.result.deviceId == "fake-s1-main"
    lego_frames = [frame for frame in transport.received if frame.operation is Operation.MOTOR_RUN]
    assert len(lego_frames) == 1


@pytest.mark.asyncio
async def test_a_hub_that_will_not_connect_does_not_stop_the_class(
    clock: ManualClock, transport: FakeHubTransport
) -> None:
    from cit_lego_pybricks.diagnostics import bluetooth_unavailable

    transport.fail_connect = bluetooth_unavailable("no adapter found")
    hub = PybricksHubAdapter(
        device_id="lego-spike-01",
        display_name="Class hub 1",
        transport=transport,
        model=hub_model("spike-prime"),
        ports=PORTS,
    )
    runtime = Runtime(clock=clock, adapters=(hub, create_fake_s1_adapter()), physical_enabled=True)

    await runtime.start()

    assert runtime.registry.get("lego-spike-01").state.value == "failed"
    assert runtime.registry.get("fake-s1-main").state.value == "connected"


# ---------------------------------------------------------------- configuration


def write_config(path: Path, *, physical: bool, devices: dict[str, Any]) -> Path:
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "runtime": {
                    "bindHost": "127.0.0.1",
                    "bindPort": 8791,
                    "physicalDevicesEnabled": physical,
                    "agentMeshBridgeEnabled": False,
                },
                "externalRepositories": {},
                "devices": devices,
            }
        ),
        encoding="utf-8",
    )
    return path


LEGO_ENTRY = {
    "lego-spike-01": {
        "adapter": "lego-pybricks",
        "displayName": "Class hub 1",
        "hubName": "cit-hub-1",
        "hubModel": "spike-prime",
        "ports": {"A": "motor", "B": "motor", "C": "distance"},
    }
}


def test_a_configured_hub_becomes_a_discovery_provider(tmp_path: Path) -> None:
    from cit_runtime.config import load_config

    config = load_config(write_config(tmp_path / "class.yaml", physical=True, devices=LEGO_ENTRY))

    bindings = lego_bindings(config)
    providers = build_providers(config)

    assert bindings == (
        HubBinding(
            device_id="lego-spike-01",
            display_name="Class hub 1",
            hub_name="cit-hub-1",
            model_id="spike-prime",
            ports={"A": "motor", "B": "motor", "C": "distance"},
        ),
    )
    assert isinstance(providers[0], PybricksDiscoveryProvider)


def test_a_configuration_naming_hubs_with_physical_devices_off_is_refused(
    tmp_path: Path,
) -> None:
    path = write_config(tmp_path / "class.yaml", physical=False, devices=LEGO_ENTRY)

    with pytest.raises(ConfigurationError, match="physicalDevicesEnabled"):
        runtime_from_config(path)


def test_a_hub_entry_missing_its_name_says_what_is_missing(tmp_path: Path) -> None:
    from cit_runtime.config import load_config

    entry = {"lego-spike-01": {"adapter": "lego-pybricks", "displayName": "Class hub 1"}}
    config = load_config(write_config(tmp_path / "class.yaml", physical=True, devices=entry))

    with pytest.raises(ConfigurationError, match="hubName"):
        lego_bindings(config)


def test_a_configured_runtime_registers_the_lego_profile(tmp_path: Path) -> None:
    path = write_config(tmp_path / "class.yaml", physical=True, devices=LEGO_ENTRY)

    runtime = runtime_from_config(path)

    assert runtime.physical_enabled is True
    assert runtime.supervisor.policy("lego-student") == LEGO_STUDENT_POLICY
    assert runtime.supervisor.policy("lego-student").require_deadman is True


def test_a_runtime_without_a_configuration_is_still_simulation_only() -> None:
    runtime = Runtime()

    assert runtime.physical_enabled is False
    assert runtime.info().execution_mode == "simulation"


def test_the_lego_profile_caps_speed_and_duration() -> None:
    bounds = LEGO_STUDENT_POLICY.bounds

    assert bounds.max_speed == 0.5
    assert bounds.max_duration_seconds == 2.0
    assert LEGO_STUDENT_POLICY.permits("weapon.blaster") is False


@pytest.mark.asyncio
async def test_a_device_refusal_reaches_the_student_with_its_reason(
    lego_runtime: Runtime,
) -> None:
    """A hub that refuses must not look like a hub that obeyed."""

    from cit_runtime.student_bridge import StudentBridge

    session_id = await ready_session(lego_runtime, "lego-spike-01")
    lego_runtime.arm(session_id=session_id, device_id="lego-spike-01", instructor_id="teacher-1")
    bridge = StudentBridge(lego_runtime, session_id=session_id, source="student_blocks")
    bridge.deadman_active = True

    answer = await bridge.call(
        "command",
        {
            "device_id": "lego-spike-01",
            "capability": "motor.run",
            "action": "set",
            # Port D is empty on this hub.
            "arguments": {"port": "D", "speed": 0.2},
        },
    )

    assert answer["accepted"] is False
    assert answer["status"] == "rejected"
    assert "Port D has no motor" in str(answer["message"])
    assert answer["recovery"]
