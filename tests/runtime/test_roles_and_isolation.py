"""FR-068 roles, and the classroom isolation that makes them mean anything.

Each test here names something a student must not be able to do, and does it the
way a student actually could: by sending the request, not by calling a method
they were never going to call. A rule that is only enforced by hiding a button
is not enforced.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cit_runtime import ManualClock, Runtime, SafetyPolicy
from cit_runtime.api import create_app
from cit_runtime.roles import (
    Action,
    AuthenticationError,
    Authority,
    AuthorizationError,
    Role,
    authorize,
    resolve_source,
)
from fastapi.testclient import TestClient

PASSCODE = "test-passcode"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _now() -> datetime:
    return NOW


@pytest.fixture
def api_runtime(clock: ManualClock, physical_policy: SafetyPolicy, tmp_path: Path) -> Runtime:
    return Runtime(
        clock=clock,
        policies=(physical_policy,),
        physical_enabled=True,
        data_dir=tmp_path,
        instructor_passcode=PASSCODE,
    )


@pytest.fixture
def client(api_runtime: Runtime) -> Iterator[TestClient]:
    with TestClient(create_app(api_runtime)) as started:
        yield started


def join(client: TestClient, actor_id: str, *, role: str = "student") -> str:
    body: dict[str, object] = {"actor_id": actor_id, "role": role}
    if role == "instructor":
        body["passcode"] = PASSCODE
    return str(client.post("/api/auth/join", json=body).json()["token"])


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def open_session(client: TestClient, token: str, device_id: str) -> str:
    session_id = str(
        client.post(
            "/api/sessions",
            json={"project_id": "lesson", "execution_mode": "simulation"},
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


# ------------------------------------------------------------ the rule itself


def test_every_privileged_action_requires_the_instructor_role() -> None:
    """The table is the rule. A new action defaults to instructor-only or fails."""

    student = Authority().join(actor_id="s", role=Role.STUDENT, now=_now())[1]
    for action in Action:
        with pytest.raises(AuthorizationError):
            authorize(student, action)


def test_a_token_the_runtime_did_not_issue_is_refused() -> None:
    authority = Authority()
    with pytest.raises(AuthenticationError):
        authority.principal("made-up", now=_now())


def test_a_token_expires() -> None:
    authority = Authority(token_ttl=timedelta(seconds=1))
    token, _ = authority.join(actor_id="s", role=Role.STUDENT, now=_now())
    with pytest.raises(AuthenticationError):
        authority.principal(token, now=_now() + timedelta(seconds=2))


def test_a_student_cannot_claim_the_instructor_source() -> None:
    student = Authority().join(actor_id="s", role=Role.STUDENT, now=_now())[1]
    with pytest.raises(AuthorizationError):
        resolve_source(student, "instructor")


# ----------------------------------------------------- FR-068 over the wire


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/safety/arm", {"session_id": "x", "device_id": "fake-s1-main"}),
        ("post", "/api/safety/disarm", {}),
        ("post", "/api/safety/stop", {"reason": "mine now"}),
        ("post", "/api/safety/revoke-lease", {"device_id": "fake-s1-main"}),
        ("post", "/api/safety/clear-queue", {}),
        ("post", "/api/safety/inputs", {"source": "leap", "enabled": False}),
        ("post", "/api/devices/discover", None),
        ("post", "/api/devices/disconnect", {"device_id": "fake-s1-main"}),
        ("post", "/api/retention", {"max_recordings": 1, "retention_days": 1}),
        ("get", "/api/devices/overview", None),
        ("get", "/api/classroom", None),
        ("get", "/api/audit/export", None),
    ],
)
def test_a_student_is_refused_every_instructor_route(
    client: TestClient, method: str, path: str, body: dict[str, object] | None
) -> None:
    token = join(client, "student-1")
    call = getattr(client, method)
    response = (
        call(path, headers=auth(token))
        if body is None
        else call(path, json=body, headers=auth(token))
    )
    assert response.status_code == 403, f"{path} let a student through"


def test_a_student_cannot_send_a_command_as_the_instructor(client: TestClient) -> None:
    """FR-072. Claiming `instructor` would buy stop-all priority."""

    token = join(client, "student-1")
    session_id = open_session(client, token, "fake-s1-main")
    response = client.post(
        "/api/commands",
        json={
            "session_id": session_id,
            "device_id": "fake-s1-main",
            "capability": "drive.velocity",
            "action": "set",
            "arguments": {"speed": 0.2},
            "source": "instructor",
        },
        headers=auth(token),
    )
    assert response.status_code == 403


def test_a_student_cannot_open_a_physical_session(client: TestClient) -> None:
    """FR-062 and FR-068: moving a real robot is an instructor's decision."""

    token = join(client, "student-1")
    response = client.post(
        "/api/sessions",
        json={"project_id": "lesson", "execution_mode": "physical"},
        headers=auth(token),
    )
    assert response.status_code == 403


def test_a_session_belongs_to_whoever_signed_in_not_to_the_body(client: TestClient) -> None:
    token = join(client, "student-1")
    session = client.post(
        "/api/sessions",
        json={"project_id": "lesson", "execution_mode": "simulation"},
        headers=auth(token),
    ).json()
    assert session["userId"] == "student-1"


# ------------------------------------------------------- classroom isolation


def test_a_student_cannot_command_another_students_session(client: TestClient) -> None:
    first = join(client, "student-1")
    second = join(client, "student-2")
    session_id = open_session(client, first, "fake-s1-main")

    response = client.post(
        "/api/commands",
        json={
            "session_id": session_id,
            "device_id": "fake-s1-main",
            "capability": "drive.velocity",
            "action": "set",
            "arguments": {"speed": 0.2},
        },
        headers=auth(second),
    )
    assert response.status_code == 403


def test_a_student_cannot_stop_another_students_device(client: TestClient) -> None:
    first = join(client, "student-1")
    second = join(client, "student-2")
    open_session(client, first, "fake-s1-main")

    response = client.post(
        "/api/safety/stop",
        json={"device_id": "fake-s1-main", "reason": "not mine"},
        headers=auth(second),
    )
    assert response.status_code == 403


def test_a_student_sees_their_own_devices_and_the_free_ones(client: TestClient) -> None:
    first = join(client, "student-1")
    second = join(client, "student-2")
    open_session(client, first, "fake-s1-main")
    open_session(client, second, "fake-lego-main")

    visible = {
        device["deviceId"]
        for device in client.get("/api/devices", headers=auth(second)).json()["devices"]
    }

    assert "fake-lego-main" in visible
    assert "fake-s1-main" not in visible
    # The unassigned robots stay visible: a student has to be able to ask for one.
    assert {"fake-leap-main", "fake-quest-main"} <= visible


def test_a_student_sees_only_their_own_sessions(client: TestClient) -> None:
    first = join(client, "student-1")
    second = join(client, "student-2")
    open_session(client, first, "fake-s1-main")
    open_session(client, second, "fake-lego-main")

    owners = {
        session["userId"]
        for session in client.get("/api/sessions", headers=auth(second)).json()["sessions"]
    }
    assert owners == {"student-2"}


def test_an_instructor_sees_the_whole_room(client: TestClient) -> None:
    student = join(client, "student-1")
    teacher = join(client, "teacher-1", role="instructor")
    open_session(client, student, "fake-s1-main")

    classroom = client.get("/api/classroom", headers=auth(teacher)).json()

    assert {person["actorId"] for person in classroom["people"]} == {"student-1", "teacher-1"}
    assert {session["userId"] for session in classroom["sessions"]} == {"student-1"}
    assert len(classroom["devices"]) == 4


@pytest.mark.asyncio
async def test_the_event_stream_carries_only_a_students_own_devices(
    client: TestClient, api_runtime: Runtime
) -> None:
    """FR-068 and NFR 12.6: one classroom, several browsers, no shared console.

    The other student's device reports first. If the filter were missing, that
    is the message this socket would receive.
    """

    first = join(client, "student-1")
    second = join(client, "student-2")
    open_session(client, first, "fake-s1-main")
    open_session(client, second, "fake-lego-main")

    with client.websocket_connect(f"/ws/events?token={second}") as socket:
        for device_id in ("fake-s1-main", "fake-lego-main"):
            adapter = api_runtime.registry.adapter(device_id)
            await adapter.emit_telemetry(
                "telemetry.battery", {"percent": 80}, at=api_runtime.clock.now()
            )
            api_runtime.router.publish_all(adapter.drain_events())
        message = socket.receive_json()

    assert message["event"]["deviceId"] == "fake-lego-main"


def test_the_audit_names_the_person_not_the_mechanism(client: TestClient) -> None:
    """FR-083. `student_blocks` does not tell an instructor whose block it was."""

    token = join(client, "student-1")
    session_id = open_session(client, token, "fake-s1-main")
    client.post(
        "/api/commands",
        json={
            "session_id": session_id,
            "device_id": "fake-s1-main",
            "capability": "drive.velocity",
            "action": "set",
            "arguments": {"speed": 0.2},
        },
        headers=auth(token),
    )

    accepted = [
        entry
        for entry in client.get("/api/audit", headers=auth(token)).json()["entries"]
        if entry["action"] == "command.accepted"
    ]

    assert accepted[-1]["actorId"] == "student-1"
    # The mechanism is still recorded, one field along.
    assert accepted[-1]["context"]["source"] == "student_blocks"


def test_a_student_only_reads_their_own_audit_entries(client: TestClient) -> None:
    first = join(client, "student-1")
    second = join(client, "student-2")
    open_session(client, first, "fake-s1-main")
    open_session(client, second, "fake-lego-main")

    entries = client.get("/api/audit", headers=auth(second)).json()["entries"]

    assert entries
    assert all(entry["actorId"] in {"student-2"} for entry in entries)
