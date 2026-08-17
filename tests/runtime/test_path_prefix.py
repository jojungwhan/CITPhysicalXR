"""Serving the runtime under a path, for a proxy that cannot rewrite one.

A Cloudflare Tunnel forwards the path it matched: a rule for ``/citxr`` delivers
``/citxr/api/health``. These tests fix both halves of that -- what the prefix
accepts, and what it refuses -- because a prefix that quietly served everything
would turn one routed path into a whole open runtime.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cit_runtime import ManualClock, Runtime, SafetyPolicy
from cit_runtime.api import PathPrefix, create_app
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

PASSCODE = "test-passcode"


@pytest.fixture
def hosted_runtime(clock: ManualClock, physical_policy: SafetyPolicy, tmp_path: Path) -> Runtime:
    del clock
    return Runtime(
        clock=ManualClock(start=datetime(2026, 1, 1, tzinfo=UTC)),
        policies=(physical_policy,),
        data_dir=tmp_path,
        instructor_passcode=PASSCODE,
    )


@pytest.fixture
def client(hosted_runtime: Runtime) -> Iterator[TestClient]:
    with TestClient(PathPrefix(create_app(hosted_runtime), "/citxr")) as started:
        yield started


def test_a_route_is_reachable_under_the_prefix(client: TestClient) -> None:
    response = client.get("/citxr/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_the_unprefixed_route_is_not_reachable(client: TestClient) -> None:
    # The proxy sends only what it was given. Anything else arriving here is a
    # misrouted request, and answering it would be a second way in.
    response = client.get("/api/health")

    assert response.status_code == 404
    assert "citxr" in response.json()["detail"]


def test_signing_in_and_being_refused_both_work_under_the_prefix(
    client: TestClient,
) -> None:
    joined = client.post(
        "/citxr/api/auth/join",
        json={"actor_id": "student-one", "role": "student"},
    )
    assert joined.status_code == 200
    token = joined.json()["token"]

    # ADR-027 still decides this, one path segment further along.
    refused = client.post(
        "/citxr/api/safety/arm",
        json={"session_id": "s", "device_id": "fake-s1-main"},
        headers={"authorization": f"Bearer {token}"},
    )
    assert refused.status_code == 403

    unauthenticated = client.get("/citxr/api/devices")
    assert unauthenticated.status_code == 401


def test_a_websocket_outside_the_prefix_is_closed(client: TestClient) -> None:
    # 1008, policy violation: the socket is refused at the prefix, before any
    # token is looked at.
    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect("/ws/events?token=nope") as socket:
            socket.receive_text()

    assert refused.value.code == 1008


def test_a_prefix_of_root_is_refused(hosted_runtime: Runtime) -> None:
    # "/" is not a prefix, it is the absence of one, and accepting it would make
    # the refusal branch above unreachable while looking configured.
    with pytest.raises(ValueError):
        PathPrefix(create_app(hosted_runtime), "/")


def test_a_prefix_is_normalized(hosted_runtime: Runtime) -> None:
    assert PathPrefix(create_app(hosted_runtime), "citxr/").prefix == "/citxr"
