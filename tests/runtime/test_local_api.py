"""The local API: routes, the loopback refusal, and what it must not expose."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from cit_runtime import ManualClock, Runtime, SafetyPolicy
from cit_runtime.api import DEFAULT_ALLOWED_ORIGINS, create_app, serve
from fastapi.testclient import TestClient

pytestmark = pytest.mark.anyio

PASSCODE = "test-passcode"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def runtime(clock: ManualClock, physical_policy: SafetyPolicy, tmp_path: Path) -> Runtime:
    return Runtime(
        clock=clock,
        policies=(physical_policy,),
        physical_enabled=True,
        data_dir=tmp_path,
        instructor_passcode=PASSCODE,
    )


@pytest.fixture
def client(runtime: Runtime) -> Iterator[TestClient]:
    with TestClient(create_app(runtime)) as started:
        yield started


def join(client: TestClient, actor_id: str, *, role: str = "student") -> str:
    """Sign in and return the token, the way every Studio client starts."""

    body: dict[str, object] = {"actor_id": actor_id, "role": role}
    if role == "instructor":
        body["passcode"] = PASSCODE
    response = client.post("/api/auth/join", json=body)
    assert response.status_code == 200, response.text
    return str(response.json()["token"])


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def ready_session(client: TestClient, token: str, device_id: str = "fake-s1-main") -> str:
    session_id = str(
        client.post(
            "/api/sessions",
            json={
                "project_id": "lesson-1",
                "execution_mode": "simulation",
                "safety_policy_id": "classroom-physical",
            },
            headers=auth(token),
        ).json()["sessionId"]
    )
    client.post(
        f"/api/sessions/{session_id}/devices",
        json={"device_ids": [device_id]},
        headers=auth(token),
    )
    client.post(f"/api/sessions/{session_id}/validate", headers=auth(token))
    return session_id


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

    paths = set(client.app.openapi()["paths"])  # type: ignore[attr-defined]
    forbidden = {"exec", "eval", "shell", "command/raw", "python", "subprocess"}
    assert not any(any(word in path for word in forbidden) for path in paths)


# ------------------------------------------------------------------- identity


def test_health_is_reachable_before_anyone_joins() -> None:
    """The Studio has to find the runtime in order to sign in to it."""

    with TestClient(create_app(Runtime())) as client:
        payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["executionMode"] == "simulation"
    assert payload["physicalEnabled"] is False


def test_a_request_without_a_token_is_401(client: TestClient) -> None:
    assert client.get("/api/devices").status_code == 401


def test_an_invented_token_is_401(client: TestClient) -> None:
    assert client.get("/api/devices", headers=auth("not-a-real-token")).status_code == 401


def test_the_instructor_role_needs_the_passcode(client: TestClient) -> None:
    response = client.post(
        "/api/auth/join",
        json={"actor_id": "pretender", "role": "instructor", "passcode": "guess"},
    )
    assert response.status_code == 403


def test_leaving_revokes_the_token(client: TestClient) -> None:
    token = join(client, "student-1")
    assert client.post("/api/auth/leave", headers=auth(token)).json()["released"] is True
    assert client.get("/api/devices", headers=auth(token)).status_code == 401


# --------------------------------------------------------------------- routes


def test_devices_appear_after_startup(client: TestClient) -> None:
    token = join(client, "student-1")
    devices = client.get("/api/devices", headers=auth(token)).json()["devices"]
    ids = {device["deviceId"] for device in devices}
    assert ids == {
        "fake-s1-main",
        "fake-lego-main",
        "fake-leap-main",
        "fake-quest-main",
    }
    assert all(device["state"] == "connected" for device in devices)


def test_full_lesson_flow_over_http(client: TestClient) -> None:
    token = join(client, "student-1")
    session_id = ready_session(client, token)

    response = client.post(
        "/api/commands",
        json={
            "session_id": session_id,
            "device_id": "fake-s1-main",
            "capability": "drive.velocity",
            "action": "set",
            "arguments": {"speed": 0.2, "durationSeconds": 1.0},
        },
        headers=auth(token),
    ).json()

    assert response["accepted"] is True
    assert response["status"] == "completed"


def test_command_speed_is_clamped_and_reported(client: TestClient) -> None:
    token = join(client, "student-1")
    session_id = ready_session(client, token)

    response = client.post(
        "/api/commands",
        json={
            "session_id": session_id,
            "device_id": "fake-s1-main",
            "capability": "drive.velocity",
            "action": "set",
            "arguments": {"speed": 99.0},
        },
        headers=auth(token),
    ).json()

    assert response["accepted"] is True
    assert set(response["clampedFields"]) == {"speed", "durationSeconds"}


def test_stop_all_over_http(client: TestClient) -> None:
    token = join(client, "teacher-1", role="instructor")
    response = client.post(
        "/api/safety/stop", json={"reason": "class over"}, headers=auth(token)
    ).json()
    assert response["scope"] == "all"
    assert len(response["stopped"]) == 4


def test_arming_an_unvalidated_session_is_409(client: TestClient) -> None:
    student = join(client, "student-1")
    teacher = join(client, "teacher-1", role="instructor")
    session_id = str(
        client.post(
            "/api/sessions",
            json={"project_id": "lesson-1", "execution_mode": "simulation"},
            headers=auth(student),
        ).json()["sessionId"]
    )
    response = client.post(
        "/api/safety/arm",
        json={"session_id": session_id, "device_id": "fake-s1-main"},
        headers=auth(teacher),
    )
    assert response.status_code == 409


def test_binding_a_device_twice_across_sessions_is_409(client: TestClient) -> None:
    first = join(client, "student-1")
    second = join(client, "student-2")
    first_session = ready_session(client, first)
    second_session = str(
        client.post(
            "/api/sessions",
            json={"project_id": "b", "execution_mode": "simulation"},
            headers=auth(second),
        ).json()["sessionId"]
    )
    assert first_session
    response = client.post(
        f"/api/sessions/{second_session}/devices",
        json={"device_ids": ["fake-s1-main"]},
        headers=auth(second),
    )
    assert response.status_code == 409


def test_illegal_state_transition_is_409(client: TestClient) -> None:
    token = join(client, "student-1")
    session_id = str(
        client.post(
            "/api/sessions",
            json={"project_id": "a", "execution_mode": "simulation"},
            headers=auth(token),
        ).json()["sessionId"]
    )
    response = client.post(
        f"/api/sessions/{session_id}/state", json={"state": "running"}, headers=auth(token)
    )
    assert response.status_code == 409


def test_unknown_session_is_404(client: TestClient) -> None:
    token = join(client, "student-1")
    response = client.post(
        "/api/sessions/nope/devices", json={"device_ids": ["fake-s1-main"]}, headers=auth(token)
    )
    assert response.status_code == 404


def test_audit_endpoint_returns_redacted_entries(client: TestClient) -> None:
    token = join(client, "teacher-1", role="instructor")
    client.post(
        "/api/sessions",
        json={"project_id": "a", "execution_mode": "simulation"},
        headers=auth(token),
    )
    entries = client.get("/api/audit", headers=auth(token)).json()["entries"]
    assert entries
    assert entries[-1]["action"] == "session.created"


def test_events_websocket_streams_device_events(client: TestClient) -> None:
    token = join(client, "teacher-1", role="instructor")
    with client.websocket_connect(f"/ws/events?token={token}") as socket:
        client.post("/api/devices/discover", headers=auth(token))
        message = socket.receive_json()
    assert message["kind"] == "device_event"
    assert "eventId" in message["event"]


def test_the_events_websocket_refuses_an_unauthenticated_client(client: TestClient) -> None:
    with pytest.raises(Exception):  # noqa: B017 - starlette closes before handshake completes
        with client.websocket_connect("/ws/events") as socket:
            socket.receive_json()
