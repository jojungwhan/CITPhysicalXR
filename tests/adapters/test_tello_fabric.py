from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError
from uuid import uuid4

import pytest
from cit_protocol import FabricResolvedCommand
from cit_tello.backend import (
    Brain2DevicesApiTelloBackend,
    SimulatedTelloBackend,
    TelloBackendError,
)
from cit_tello.bridge import TelloCommandHandler, tello_health_report
from cit_tello.contract import (
    BRAIN2DEVICES_REVISION,
    EMERGENCY_STOP_CAPABILITY,
    LAND_CAPABILITY,
    MOVE_CAPABILITY,
    ROTATE_CAPABILITY,
    TAKEOFF_CAPABILITY,
    build_manifest,
    build_node,
)


def _command(action: str, *, parameters: dict[str, object] | None = None) -> FabricResolvedCommand:
    now = datetime.now(UTC)
    return FabricResolvedCommand.model_validate(
        {
            "commandId": str(uuid4()),
            "requestMessageId": str(uuid4()),
            "schemaVersion": "1.0",
            "sessionId": "session-a",
            "targetNodeId": "tello-a",
            "action": action,
            "parameters": parameters or {},
            "priority": "instructor_override",
            "idempotencyKey": str(uuid4()),
            "requestedAt": now,
            "expiresAt": now + timedelta(seconds=1),
            "safetyProfile": "classroom-drone-monitoring",
            "correlationId": str(uuid4()),
        }
    )


def _flight_confirmations() -> dict[str, object]:
    return {
        "instructorPresent": True,
        "flightAreaClear": True,
        "emergencyPlanReady": True,
    }


def test_tello_contract_exposes_bounded_manual_flight_commands() -> None:
    manifest = build_manifest()
    node = build_node(
        at=datetime.now(UTC),
        host_id="host-a",
        site_id="site-a",
        room_id="room-a",
        node_id="tello-a",
        simulated=False,
        ip_address=None,
    )

    assert [item.name for item in manifest.consumedCapabilities] == [
        TAKEOFF_CAPABILITY,
        MOVE_CAPABILITY,
        ROTATE_CAPABILITY,
        LAND_CAPABILITY,
        EMERGENCY_STOP_CAPABILITY,
    ]
    assert node.metadata.model_dump()["brain2devicesRevision"] == BRAIN2DEVICES_REVISION
    assert node.metadata.model_dump()["takeoffEnabled"] is True


def test_tello_health_report_disables_flight_when_upstream_link_is_lost() -> None:
    report = tello_health_report(
        node_id="tello-a",
        at=datetime(2026, 8, 25, 4, 0, tzinfo=UTC),
        telemetry={
            "connection": "error",
            "connectionError": {
                "title": "Tello connection lost",
                "detail": "Wi-Fi 2 disconnected from TELLO-58C5B7",
            },
        },
        last_error=None,
        telemetry_active=True,
        camera_frames_published=0,
        camera_error=None,
    )

    assert report.connectionState.value == "disconnected"
    assert report.healthState.value == "unhealthy"
    assert report.message == "Wi-Fi 2 disconnected from TELLO-58C5B7"
    assert report.metrics.model_dump()["takeoffEnabled"] is False


@pytest.mark.asyncio
async def test_tello_duplicate_safe_state_command_executes_once() -> None:
    backend = SimulatedTelloBackend()
    await backend.start()
    handler = TelloCommandHandler(backend, node_id="tello-a")
    command = _command(LAND_CAPABILITY)

    first = await handler.execute(command)
    second = await handler.execute(command)

    assert first["duplicatePrevented"] is False
    assert second == {"duplicatePrevented": True}
    assert backend.command_log.count("land:fabric_command") == 1


@pytest.mark.asyncio
async def test_tello_duplicate_takeoff_command_executes_once() -> None:
    backend = SimulatedTelloBackend()
    await backend.start()
    handler = TelloCommandHandler(backend, node_id="tello-a")
    command = _command(TAKEOFF_CAPABILITY, parameters=_flight_confirmations())

    first = await handler.execute(command)
    second = await handler.execute(command)

    assert first["duplicatePrevented"] is False
    assert second == {"duplicatePrevented": True}
    assert backend.command_log.count("takeoff") == 1


@pytest.mark.asyncio
async def test_tello_executes_bounded_manual_flight_commands() -> None:
    backend = SimulatedTelloBackend()
    await backend.start()
    handler = TelloCommandHandler(backend, node_id="tello-a")

    await handler.execute(_command(TAKEOFF_CAPABILITY, parameters=_flight_confirmations()))
    await handler.execute(
        _command(
            MOVE_CAPABILITY,
            parameters={
                **_flight_confirmations(),
                "direction": "forward",
                "distanceCentimeters": 20,
            },
        )
    )
    await handler.execute(
        _command(
            ROTATE_CAPABILITY,
            parameters={
                **_flight_confirmations(),
                "clockwise": True,
                "degrees": 30,
            },
        )
    )

    assert backend.command_log[-3:] == ["takeoff", "move:forward:20", "rotate:true:30"]


@pytest.mark.parametrize(
    ("action", "parameters"),
    [
        (TAKEOFF_CAPABILITY, {}),
        (
            MOVE_CAPABILITY,
            {
                **_flight_confirmations(),
                "direction": "forward",
                "distanceCentimeters": 19,
            },
        ),
        (
            MOVE_CAPABILITY,
            {
                **_flight_confirmations(),
                "direction": "diagonal",
                "distanceCentimeters": 20,
            },
        ),
        (
            ROTATE_CAPABILITY,
            {
                **_flight_confirmations(),
                "clockwise": True,
                "degrees": 91,
            },
        ),
        (LAND_CAPABILITY, {"height": 1}),
    ],
)
def test_tello_rejects_unconfirmed_or_out_of_bounds_commands(
    action: str,
    parameters: dict[str, object],
) -> None:
    handler = TelloCommandHandler(SimulatedTelloBackend(), node_id="tello-a")
    with pytest.raises(ValueError):
        handler.validate(_command(action, parameters=parameters))


@pytest.mark.asyncio
async def test_brain2devices_api_backend_maps_canonical_manual_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Brain2DevicesApiTelloBackend(drone_id="primary")
    backend._token = "test-token"
    requests: list[tuple[str, dict[str, object] | None]] = []

    def capture(
        path: str,
        body: dict[str, object] | None,
    ) -> dict[str, object]:
        requests.append((path, body))
        if path == "/api/state":
            return {
                "fleet": {
                    "drones": [
                        {
                            "id": "primary",
                            "connection": "connected",
                            "flight": "flying",
                            "telemetry": {},
                            "command_error": None,
                        }
                    ]
                }
            }
        return {"accepted": True}

    monkeypatch.setattr(backend, "_request", capture)

    await backend.takeoff()
    await backend.move(direction="left", distance_centimeters=20)
    await backend.rotate(clockwise=False, degrees=30)

    assert [request for request in requests if request[0] == "/api/fleet/command"] == [
        (
            "/api/fleet/command",
            {"action": "takeoff", "drone_ids": ["primary"], "confirmed": True},
        ),
        (
            "/api/fleet/command",
            {
                "action": "move",
                "drone_ids": ["primary"],
                "confirmed": True,
                "direction": "left",
                "distance_cm": 20,
            },
        ),
        (
            "/api/fleet/command",
            {
                "action": "rotate",
                "drone_ids": ["primary"],
                "confirmed": True,
                "clockwise": False,
                "degrees": 30,
            },
        ),
    ]


@pytest.mark.asyncio
async def test_brain2devices_takeoff_waits_for_airborne_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_wait(_seconds: float) -> None:
        return

    backend = Brain2DevicesApiTelloBackend(
        drone_id="primary",
        sleep=no_wait,
        confirmation_attempts=3,
    )
    backend._token = "test-token"
    reported_flights = iter(("landed", "flying"))
    requests: list[tuple[str, dict[str, object] | None]] = []

    def respond(
        path: str,
        body: dict[str, object] | None,
    ) -> dict[str, object]:
        requests.append((path, body))
        if path == "/api/fleet/command":
            return {"accepted": True}
        return {
            "fleet": {
                "drones": [
                    {
                        "id": "primary",
                        "connection": "connected",
                        "flight": next(reported_flights),
                        "telemetry": {},
                        "command_error": None,
                    }
                ]
            }
        }

    monkeypatch.setattr(backend, "_request", respond)

    result = await backend.takeoff()

    assert result == {"takeoffConfirmed": True}
    assert [path for path, _body in requests] == [
        "/api/fleet/command",
        "/api/state",
        "/api/state",
    ]


@pytest.mark.asyncio
async def test_brain2devices_takeoff_reports_the_authoritative_disconnect_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Brain2DevicesApiTelloBackend(drone_id="primary")
    backend._token = "test-token"

    def respond(
        path: str,
        _body: dict[str, object] | None,
    ) -> dict[str, object]:
        if path == "/api/fleet/command":
            return {"accepted": True}
        return {
            "fleet": {
                "drones": [
                    {
                        "id": "primary",
                        "connection": "error",
                        "flight": "unknown",
                        "telemetry": {},
                        "error": {
                            "title": "Tello connection lost",
                            "detail": (
                                "No live telemetry refresh completed through Wi-Fi 2 "
                                "on TELLO-58C5B7"
                            ),
                        },
                        "command_error": None,
                    }
                ]
            }
        }

    monkeypatch.setattr(backend, "_request", respond)

    with pytest.raises(
        RuntimeError,
        match="No live telemetry refresh completed through Wi-Fi 2 on TELLO-58C5B7",
    ):
        await backend.takeoff()


@pytest.mark.asyncio
async def test_brain2devices_takeoff_preserves_http_rejection_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Brain2DevicesApiTelloBackend(drone_id="primary")
    backend._token = "test-token"

    def reject(*_args: object, **_kwargs: object) -> object:
        raise HTTPError(
            url="http://127.0.0.1:8765/api/fleet/command",
            code=409,
            msg="Conflict",
            hdrs=Message(),
            fp=BytesIO(b'{"accepted":false,"error":"[TELLO] is not connected"}'),
        )

    monkeypatch.setattr("cit_tello.backend.urlopen", reject)

    with pytest.raises(RuntimeError, match=r"\[TELLO\] is not connected"):
        await backend.takeoff()


@pytest.mark.asyncio
async def test_brain2devices_telemetry_preserves_link_and_command_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Brain2DevicesApiTelloBackend(drone_id="primary")
    backend._token = "test-token"
    state = {
        "fleet": {
            "drones": [
                {
                    "id": "primary",
                    "connection": "error",
                    "flight": "unknown",
                    "busy_command": None,
                    "telemetry": {},
                    "error": {
                        "title": "Tello connection lost",
                        "detail": "Wi-Fi 2 driver disconnected",
                    },
                    "command_error": {
                        "title": "Takeoff failed",
                        "detail": "The aircraft did not acknowledge takeoff",
                    },
                }
            ]
        }
    }
    monkeypatch.setattr(backend, "_request", lambda _path, _body: state)

    telemetry = await backend.telemetry()

    assert telemetry["connection"] == "error"
    assert telemetry["connectionError"] == {
        "title": "Tello connection lost",
        "detail": "Wi-Fi 2 driver disconnected",
    }
    assert telemetry["commandError"] == {
        "title": "Takeoff failed",
        "detail": "The aircraft did not acknowledge takeoff",
    }
    assert telemetry["busyCommand"] is None


@pytest.mark.asyncio
async def test_brain2devices_start_reports_the_authoritative_link_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Brain2DevicesApiTelloBackend(drone_id="primary")
    state = {
        "fleet": {
            "drones": [
                {
                    "id": "primary",
                    "connection": "error",
                    "flight": "unknown",
                    "telemetry": {},
                    "error": {
                        "title": "Tello connection lost",
                        "detail": "Wi-Fi 2 is no longer associated with TELLO-58C5B7",
                    },
                    "command_error": None,
                }
            ]
        }
    }
    monkeypatch.setattr(backend, "_read_token", lambda: "test-token")
    monkeypatch.setattr(backend, "_request", lambda _path, _body: state)

    with pytest.raises(
        RuntimeError,
        match="Wi-Fi 2 is no longer associated with TELLO-58C5B7",
    ):
        await backend.start()


@pytest.mark.asyncio
async def test_brain2devices_land_waits_for_grounded_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_wait(_seconds: float) -> None:
        return

    backend = Brain2DevicesApiTelloBackend(
        drone_id="primary",
        sleep=no_wait,
        confirmation_attempts=3,
    )
    backend._token = "test-token"
    reported_flights = iter(("flying", "landed"))

    def respond(
        path: str,
        _body: dict[str, object] | None,
    ) -> dict[str, object]:
        if path == "/api/fleet/command":
            return {"accepted": True}
        return {
            "fleet": {
                "drones": [
                    {
                        "id": "primary",
                        "connection": "connected",
                        "flight": next(reported_flights),
                        "telemetry": {},
                        "command_error": None,
                    }
                ]
            }
        }

    monkeypatch.setattr(backend, "_request", respond)

    result = await backend.land(reason="fabric_command")

    assert result == {"landConfirmed": True, "reason": "fabric_command"}


@pytest.mark.asyncio
async def test_brain2devices_land_does_not_repeat_a_command_when_already_grounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Brain2DevicesApiTelloBackend(drone_id="primary")
    backend._token = "test-token"
    requests: list[tuple[str, dict[str, object] | None]] = []

    def respond(
        path: str,
        body: dict[str, object] | None,
    ) -> dict[str, object]:
        requests.append((path, body))
        return {
            "fleet": {
                "drones": [
                    {
                        "id": "primary",
                        "connection": "connected",
                        "flight": "landed",
                        "telemetry": {"height_cm": 0},
                        "command_error": None,
                    }
                ]
            }
        }

    monkeypatch.setattr(backend, "_request", respond)

    result = await backend.land(reason="adapter_shutdown")

    assert result == {
        "landConfirmed": True,
        "alreadyLanded": True,
        "reason": "adapter_shutdown",
    }
    assert requests == [("/api/state", None)]


@pytest.mark.asyncio
async def test_brain2devices_emergency_stop_does_not_disturb_a_confirmed_landed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Brain2DevicesApiTelloBackend(drone_id="primary")
    backend._token = "test-token"
    requests: list[tuple[str, dict[str, object] | None]] = []

    def respond(
        path: str,
        body: dict[str, object] | None,
    ) -> dict[str, object]:
        requests.append((path, body))
        return {
            "fleet": {
                "drones": [
                    {
                        "id": "primary",
                        "connection": "connected",
                        "flight": "landed",
                        "telemetry": {"height_cm": 0},
                        "command_error": None,
                    }
                ]
            }
        }

    monkeypatch.setattr(backend, "_request", respond)

    result = await backend.emergency_stop(reason="fabric_emergency_stop")

    assert result == {
        "emergencyStopRequested": False,
        "alreadyLanded": True,
        "reason": "fabric_emergency_stop",
    }
    assert requests == [("/api/state", None)]


@pytest.mark.asyncio
async def test_brain2devices_emergency_stop_still_runs_when_state_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Brain2DevicesApiTelloBackend(drone_id="primary")
    backend._token = "test-token"
    requests: list[tuple[str, dict[str, object] | None]] = []

    def respond(
        path: str,
        body: dict[str, object] | None,
    ) -> dict[str, object]:
        requests.append((path, body))
        if path == "/api/state":
            raise TelloBackendError("state lookup failed")
        return {"accepted": True}

    monkeypatch.setattr(backend, "_request", respond)

    result = await backend.emergency_stop(reason="fabric_emergency_stop")

    assert result == {
        "emergencyStopRequested": True,
        "reason": "fabric_emergency_stop",
    }
    assert requests == [
        ("/api/state", None),
        (
            "/api/fleet/command",
            {
                "action": "emergency",
                "drone_ids": ["primary"],
                "confirmed": True,
            },
        ),
    ]


@pytest.mark.asyncio
async def test_brain2devices_move_waits_for_command_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_wait(_seconds: float) -> None:
        return

    backend = Brain2DevicesApiTelloBackend(
        drone_id="primary",
        sleep=no_wait,
        confirmation_attempts=3,
    )
    backend._token = "test-token"
    busy_commands = iter(("move forward 20cm", None))

    def respond(
        path: str,
        _body: dict[str, object] | None,
    ) -> dict[str, object]:
        if path == "/api/fleet/command":
            return {"accepted": True}
        return {
            "fleet": {
                "drones": [
                    {
                        "id": "primary",
                        "connection": "connected",
                        "flight": "flying",
                        "busy_command": next(busy_commands),
                        "telemetry": {},
                        "command_error": None,
                    }
                ]
            }
        }

    monkeypatch.setattr(backend, "_request", respond)

    result = await backend.move(direction="forward", distance_centimeters=20)

    assert result == {
        "moveConfirmed": True,
        "direction": "forward",
        "distanceCentimeters": 20,
    }


@pytest.mark.asyncio
async def test_brain2devices_rotate_waits_for_command_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_wait(_seconds: float) -> None:
        return

    backend = Brain2DevicesApiTelloBackend(
        drone_id="primary",
        sleep=no_wait,
        confirmation_attempts=2,
    )
    backend._token = "test-token"
    busy_commands = iter(("rotate clockwise 30 degrees", None))

    def respond(
        path: str,
        _body: dict[str, object] | None,
    ) -> dict[str, object]:
        if path == "/api/fleet/command":
            return {"accepted": True}
        return {
            "fleet": {
                "drones": [
                    {
                        "id": "primary",
                        "connection": "connected",
                        "flight": "flying",
                        "busy_command": next(busy_commands),
                        "telemetry": {},
                        "command_error": None,
                    }
                ]
            }
        }

    monkeypatch.setattr(backend, "_request", respond)

    result = await backend.rotate(clockwise=True, degrees=30)

    assert result == {"rotateConfirmed": True, "clockwise": True, "degrees": 30}
