"""The local API: routes, the loopback refusal, and what it must not expose."""

from __future__ import annotations

import pytest
from cit_runtime import ManualClock, Runtime, SafetyPolicy
from cit_runtime.api import DEFAULT_ALLOWED_ORIGINS, create_app, serve
from fastapi.testclient import TestClient

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def client(clock: ManualClock, physical_policy: SafetyPolicy) -> TestClient:
    runtime = Runtime(clock=clock, policies=(physical_policy,), physical_enabled=True)
    return TestClient(create_app(runtime))


# ------------------------------------------------------------------- exposure


def test_binding_a_routable_interface_is_refused() -> None:
    with pytest.raises(PermissionError, match="routable interface"):
        serve(host="0.0.0.0", port=8791)


def test_binding_a_lan_address_is_refused() -> None:
    with pytest.raises(PermissionError, match="Refusing to bind"):
        serve(host="192.168.1.20", port=8791)


def test_browser_origins_are_an_allowlist_not_a_wildcard() -> None:
    assert "*" not in DEFAULT_ALLOWED_ORIGINS
    assert all(
        origin.startswith(("http://localhost", "http://127.0.0.1"))
        for origin in DEFAULT_ALLOWED_ORIGINS
    )


def test_there_is_no_shell_or_eval_route(client: TestClient) -> None:
    """The PRD forbids arbitrary execution endpoints. Assert none exist."""

    with client:
        paths = set(client.app.openapi()["paths"])  # type: ignore[attr-defined]
    forbidden = {"exec", "eval", "shell", "run", "command/raw", "python", "subprocess"}
    assert not any(any(word in path for word in forbidden) for path in paths)


# --------------------------------------------------------------------- routes


def test_health_reports_simulation_by_default() -> None:
    with TestClient(create_app(Runtime())) as client:
        payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["executionMode"] == "simulation"
    assert payload["physicalEnabled"] is False


def test_devices_appear_after_startup(client: TestClient) -> None:
    with client:
        devices = client.get("/api/devices").json()["devices"]
    ids = {device["deviceId"] for device in devices}
    assert ids == {
        "fake-s1-main",
        "fake-lego-main",
        "fake-leap-main",
        "fake-quest-main",
    }
    assert all(device["state"] == "connected" for device in devices)


def test_full_lesson_flow_over_http(client: TestClient) -> None:
    with client:
        session = client.post(
            "/api/sessions",
            json={
                "project_id": "lesson-1",
                "user_id": "student-1",
                "instructor_id": "instructor-1",
                "execution_mode": "simulation",
                "safety_policy_id": "classroom-physical",
            },
        ).json()
        session_id = session["sessionId"]

        bound = client.post(
            f"/api/sessions/{session_id}/devices", json={"device_ids": ["fake-s1-main"]}
        ).json()
        assert bound["deviceBindings"] == ["fake-s1-main"]

        ready = client.post(f"/api/sessions/{session_id}/validate").json()
        assert ready["state"] == "ready"

        response = client.post(
            "/api/commands",
            json={
                "session_id": session_id,
                "device_id": "fake-s1-main",
                "capability": "drive.velocity",
                "action": "set",
                "arguments": {"speed": 0.2, "durationSeconds": 1.0},
            },
        ).json()

    assert response["accepted"] is True
    assert response["status"] == "completed"


def test_command_speed_is_clamped_and_reported(client: TestClient) -> None:
    with client:
        session_id = client.post(
            "/api/sessions",
            json={
                "project_id": "lesson-1",
                "user_id": "student-1",
                "execution_mode": "simulation",
                "safety_policy_id": "classroom-physical",
            },
        ).json()["sessionId"]
        client.post(f"/api/sessions/{session_id}/devices", json={"device_ids": ["fake-s1-main"]})
        client.post(f"/api/sessions/{session_id}/validate")

        response = client.post(
            "/api/commands",
            json={
                "session_id": session_id,
                "device_id": "fake-s1-main",
                "capability": "drive.velocity",
                "action": "set",
                "arguments": {"speed": 99.0},
            },
        ).json()

    assert response["accepted"] is True
    assert set(response["clampedFields"]) == {"speed", "durationSeconds"}


def test_agent_mesh_movement_is_refused_over_http(client: TestClient) -> None:
    with client:
        session_id = client.post(
            "/api/sessions",
            json={
                "project_id": "lesson-1",
                "user_id": "student-1",
                "execution_mode": "simulation",
                "safety_policy_id": "classroom-physical",
            },
        ).json()["sessionId"]
        client.post(f"/api/sessions/{session_id}/devices", json={"device_ids": ["fake-s1-main"]})
        client.post(f"/api/sessions/{session_id}/validate")

        response = client.post(
            "/api/commands",
            json={
                "session_id": session_id,
                "device_id": "fake-s1-main",
                "capability": "drive.velocity",
                "action": "set",
                "arguments": {"speed": 0.1},
                "source": "agent_mesh",
            },
        ).json()

    assert response["accepted"] is False
    assert response["code"] == "SAFETY_POLICY_DENIED"


def test_stop_all_over_http(client: TestClient) -> None:
    with client:
        response = client.post(
            "/api/safety/stop", json={"actor_id": "instructor-1", "reason": "class over"}
        ).json()
    assert response["scope"] == "all"
    assert len(response["stopped"]) == 4


def test_arming_an_unvalidated_session_is_403(client: TestClient) -> None:
    with client:
        session_id = client.post(
            "/api/sessions",
            json={
                "project_id": "lesson-1",
                "user_id": "student-1",
                "execution_mode": "simulation",
                "safety_policy_id": "classroom-physical",
            },
        ).json()["sessionId"]
        response = client.post(
            "/api/safety/arm",
            json={
                "session_id": session_id,
                "device_id": "fake-s1-main",
                "instructor_id": "instructor-1",
            },
        )
    assert response.status_code == 403


def test_binding_a_device_twice_across_sessions_is_409(client: TestClient) -> None:
    with client:
        first = client.post(
            "/api/sessions",
            json={"project_id": "a", "user_id": "u1", "execution_mode": "simulation"},
        ).json()["sessionId"]
        second = client.post(
            "/api/sessions",
            json={"project_id": "b", "user_id": "u2", "execution_mode": "simulation"},
        ).json()["sessionId"]
        client.post(f"/api/sessions/{first}/devices", json={"device_ids": ["fake-s1-main"]})
        response = client.post(
            f"/api/sessions/{second}/devices", json={"device_ids": ["fake-s1-main"]}
        )
    assert response.status_code == 409


def test_illegal_state_transition_is_409(client: TestClient) -> None:
    with client:
        session_id = client.post(
            "/api/sessions",
            json={"project_id": "a", "user_id": "u1", "execution_mode": "simulation"},
        ).json()["sessionId"]
        response = client.post(f"/api/sessions/{session_id}/state", json={"state": "running"})
    assert response.status_code == 409


def test_unknown_session_is_404(client: TestClient) -> None:
    with client:
        response = client.post("/api/sessions/nope/devices", json={"device_ids": ["fake-s1-main"]})
    assert response.status_code == 404


def test_audit_endpoint_returns_redacted_entries(client: TestClient) -> None:
    with client:
        client.post(
            "/api/sessions",
            json={"project_id": "a", "user_id": "u1", "execution_mode": "simulation"},
        )
        entries = client.get("/api/audit").json()["entries"]
    assert entries
    assert entries[-1]["action"] == "session.created"


def test_events_websocket_streams_device_events(client: TestClient) -> None:
    with client, client.websocket_connect("/ws/events") as socket:
        client.post("/api/devices/discover")
        message = socket.receive_json()
    assert message["kind"] == "device_event"
    assert "eventId" in message["event"]
