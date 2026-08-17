"""ADR-033. A published runtime closes the join itself.

On loopback, reaching the runtime means being at the machine, so a student
joins by saying who they are. Behind a proxy that publishes it, reaching the
runtime means having the URL, and the same open join would hand a token to
anybody who found it.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cit_runtime import ManualClock, Runtime, SafetyPolicy
from cit_runtime.api import create_app
from cit_runtime.roles import AuthorizationError, Role
from fastapi.testclient import TestClient

INSTRUCTOR = "instructor-passcode"
CLASSROOM = "classroom-passcode"


@pytest.fixture
def published_runtime(physical_policy: SafetyPolicy, tmp_path: Path) -> Runtime:
    return Runtime(
        clock=ManualClock(start=datetime(2026, 1, 1, tzinfo=UTC)),
        policies=(physical_policy,),
        data_dir=tmp_path,
        instructor_passcode=INSTRUCTOR,
        join_passcode=CLASSROOM,
    )


@pytest.fixture
def client(published_runtime: Runtime) -> Iterator[TestClient]:
    with TestClient(create_app(published_runtime)) as started:
        yield started


def _join(client: TestClient, **body: object) -> int:
    return client.post("/api/auth/join", json={"actor_id": "someone", **body}).status_code


def test_a_student_without_the_classroom_passcode_gets_no_token(client: TestClient) -> None:
    assert _join(client, role="student") == 403
    assert _join(client, role="student", passcode="guess") == 403


def test_a_student_with_the_classroom_passcode_joins(client: TestClient) -> None:
    assert _join(client, role="student", passcode=CLASSROOM) == 200


def test_the_classroom_passcode_does_not_buy_the_instructor_role(client: TestClient) -> None:
    # Otherwise the weaker secret would be a route to arming a robot.
    assert _join(client, role="instructor", passcode=CLASSROOM) == 403
    assert _join(client, role="instructor", passcode=INSTRUCTOR) == 200


def test_the_sign_in_page_can_tell_before_it_asks(client: TestClient) -> None:
    # UI 11.6: the Studio shows the field because the runtime said it needs one,
    # not because somebody was refused first.
    assert client.get("/api/health").json()["joinRequiresPasscode"] is True


def test_a_loopback_runtime_still_lets_a_student_join(
    physical_policy: SafetyPolicy, tmp_path: Path
) -> None:
    # The default is unchanged. A classroom runtime on a teacher's machine does
    # not ask a nine-year-old for a password to open their own lesson.
    local = Runtime(
        clock=ManualClock(start=datetime(2026, 1, 1, tzinfo=UTC)),
        policies=(physical_policy,),
        data_dir=tmp_path,
        instructor_passcode=INSTRUCTOR,
    )
    with TestClient(create_app(local)) as client:
        assert _join(client, role="student") == 200
        assert client.get("/api/health").json()["joinRequiresPasscode"] is False


def test_the_authority_refuses_directly_too(published_runtime: Runtime) -> None:
    # The rule lives in cit_runtime.roles, not in the HTTP layer (ADR-027).
    with pytest.raises(AuthorizationError):
        published_runtime.authority.join(
            actor_id="someone",
            role=Role.STUDENT,
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
