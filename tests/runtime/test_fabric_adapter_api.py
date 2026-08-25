from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from cit_matter_smart_plug import build_manifest as build_matter_manifest
from cit_matter_smart_plug import build_node as build_matter_node
from cit_protocol import to_wire
from cit_runtime.fabric_auth import (
    ADAPTER_PERMISSIONS,
    FABRIC_PERMISSIONS,
    FabricBootstrapIdentity,
)
from cit_runtime.fabric_service import create_fabric_app
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

NOW = datetime(2026, 8, 21, 3, 0, 0, tzinfo=UTC)
ADMIN_TOKEN = "cit-admin-" + "a" * 40
ADAPTER_TOKEN = "cit-adapter-" + "b" * 40
MATTER_ADAPTER_TOKEN = "cit-adapter-" + "c" * 40
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def bootstrap_identities() -> tuple[FabricBootstrapIdentity, ...]:
    return (
        FabricBootstrapIdentity(
            identity_id="admin-a",
            token=ADMIN_TOKEN,
            actor_type="administrator",
            roles=("administrator",),
            permissions=tuple(sorted(FABRIC_PERMISSIONS)),
        ),
        FabricBootstrapIdentity(
            identity_id="agent-mesh-bridge-a",
            token=ADAPTER_TOKEN,
            actor_type="adapter",
            roles=("plugin.cit.agent-mesh-bridge",),
            permissions=tuple(sorted(ADAPTER_PERMISSIONS)),
            site_id="local-site",
            room_id="local-room",
        ),
        FabricBootstrapIdentity(
            identity_id="matter-smart-plug-a",
            token=MATTER_ADAPTER_TOKEN,
            actor_type="adapter",
            roles=("plugin.cit.matter-smart-plug",),
            permissions=tuple(sorted(ADAPTER_PERMISSIONS)),
            site_id="local-site",
            room_id="local-room",
        ),
    )


def capability(
    name: str,
    direction: str,
    *,
    data_classification: str,
    latency_class: str = "conversational",
) -> dict[str, Any]:
    return {
        "name": name,
        "version": "1.0",
        "direction": direction,
        "schemaRef": None,
        "units": None,
        "maximumRateHz": 20,
        "latencyClass": latency_class,
        "safetyClassification": "informational",
        "dataClassification": data_classification,
        "constraints": {},
    }


def registration_frame() -> dict[str, Any]:
    prompt_event = capability(
        "interaction.intent.agent_prompt",
        "publish",
        data_classification="voice_transcript",
    )
    display_command = capability(
        "display.text.render",
        "consume",
        data_classification="operational",
        latency_class="ui_feedback",
    )
    prompt_command = capability(
        "agent.prompt.submit",
        "consume",
        data_classification="source_code",
    )
    output_event = capability(
        "agent.output.completed",
        "publish",
        data_classification="source_code",
    )
    return {
        "frameType": "adapter.register",
        "frameId": str(uuid4()),
        "protocolVersion": 1,
        "manifest": {
            "schemaVersion": "1.0",
            "pluginId": "cit.agent-mesh-bridge",
            "pluginVersion": "0.1.0",
            "runtimeVersion": "1.0.0",
            "displayName": "Agent Mesh bridge",
            "adapterMode": "out_of_process",
            "configurationSchema": {},
            "publishedCapabilities": [prompt_event, output_event],
            "consumedCapabilities": [prompt_command, display_command],
            "requiredPermissions": [],
            "safetyClassification": "informational",
            "dataClassifications": [
                "operational",
                "source_code",
                "voice_transcript",
            ],
            "simulatorAvailability": "included",
            "vendor": "CIT",
            "description": "Wraps existing glasses and coding-agent sessions.",
        },
        "nodes": [
            {
                "schemaVersion": "1.0",
                "nodeId": "g2-sim-a",
                "pluginId": "cit.agent-mesh-bridge",
                "pluginVersion": "0.1.0",
                "runtimeVersion": "1.0.0",
                "hostId": "agent-mesh-host-a",
                "siteId": "local-site",
                "roomId": "local-room",
                "displayName": "Existing Even Realities G2",
                "connectionState": "connected",
                "healthState": "healthy",
                "physical": True,
                "simulated": False,
                "publishedCapabilities": [prompt_event],
                "consumedCapabilities": [display_command],
                "configurationSchema": {},
                "safetyClassification": "informational",
                "dataClassifications": ["operational", "voice_transcript"],
                "simulatorAvailable": True,
                "requiredPermissions": [],
                "lastSeenAt": NOW.isoformat(),
                "metadata": {"wrappedBy": "agent-mesh"},
            },
            {
                "schemaVersion": "1.0",
                "nodeId": "codex-session-sim-a",
                "pluginId": "cit.agent-mesh-bridge",
                "pluginVersion": "0.1.0",
                "runtimeVersion": "1.0.0",
                "hostId": "agent-mesh-host-a",
                "siteId": "local-site",
                "roomId": "local-room",
                "displayName": "Existing Codex session",
                "connectionState": "connected",
                "healthState": "healthy",
                "physical": False,
                "simulated": False,
                "publishedCapabilities": [output_event],
                "consumedCapabilities": [prompt_command],
                "configurationSchema": {},
                "safetyClassification": "informational",
                "dataClassifications": ["operational", "source_code"],
                "simulatorAvailable": True,
                "requiredPermissions": [],
                "lastSeenAt": NOW.isoformat(),
                "metadata": {"agentType": "codex"},
            },
        ],
        "sentAt": NOW.isoformat(),
    }


def matter_registration_frame() -> dict[str, Any]:
    return {
        "frameType": "adapter.register",
        "frameId": str(uuid4()),
        "protocolVersion": 1,
        "manifest": to_wire(build_matter_manifest()),
        "nodes": [
            to_wire(
                build_matter_node(
                    at=NOW,
                    host_id="matter-host-a",
                    site_id="local-site",
                    room_id="local-room",
                    node_id="matter-8-ep1",
                    matter_node_id=8,
                    endpoint_id=1,
                    display_name="Classroom plug",
                    vendor_name="Matter",
                    product_name="On/Off Plug-in Unit",
                    electrical_telemetry=True,
                )
            )
        ],
        "sentAt": NOW.isoformat(),
    }


def create_started_session(client: TestClient) -> str:
    created = client.post(
        "/api/v1/fabric/sessions",
        headers=ADMIN_HEADERS,
        json={
            "coursePackId": "glasses-agent-control",
            "coursePackVersion": "1.0.0",
            "siteId": "local-site",
            "roomId": "local-room",
            "mode": "simulation",
        },
    )
    assert created.status_code == 201
    session_id = str(created.json()["sessionId"])
    for role, node_id in (
        ("primary_glasses", "g2-sim-a"),
        ("coding_agent", "codex-session-sim-a"),
    ):
        assigned = client.put(
            f"/api/v1/fabric/sessions/{session_id}/roles/{role}",
            headers=ADMIN_HEADERS,
            json={"nodeId": node_id},
        )
        assert assigned.status_code == 200
    started = client.post(
        f"/api/v1/fabric/sessions/{session_id}/start",
        headers=ADMIN_HEADERS,
    )
    assert started.status_code == 200
    return session_id


def adapter_event(
    *,
    frame_id: str,
    message_id: str,
    session_id: str,
    node_id: str,
    capability_name: str,
    sequence: int,
    data_classification: str,
    payload: dict[str, object],
    correlation_id: str,
    causation_id: str | None = None,
) -> dict[str, Any]:
    frame: dict[str, Any] = {
        "frameType": "adapter.event",
        "frameId": frame_id,
        "protocolVersion": 1,
        "event": {
            "messageId": message_id,
            "schemaVersion": "1.0",
            "messageType": "event",
            "topic": capability_name,
            "sourceNodeId": node_id,
            "sourceCapability": capability_name,
            "siteId": "local-site",
            "roomId": "local-room",
            "sessionId": session_id,
            "timestamp": NOW.isoformat(),
            "monotonicTimestamp": sequence,
            "sequence": sequence,
            "correlationId": correlation_id,
            "confidence": 0.98,
            "ttlMs": 2_000,
            "dataClassification": data_classification,
            "payload": payload,
        },
        "sentAt": NOW.isoformat(),
    }
    if causation_id is not None:
        frame["event"]["causationId"] = causation_id
    return frame


def lifecycle_frame(command: dict[str, Any], stage: str) -> dict[str, Any]:
    return {
        "frameType": "adapter.command_lifecycle",
        "frameId": str(uuid4()),
        "protocolVersion": 1,
        "lifecycle": {
            "messageId": str(uuid4()),
            "schemaVersion": "1.0",
            "messageType": "command.lifecycle",
            "commandId": command["commandId"],
            "requestMessageId": command["requestMessageId"],
            "sessionId": command["sessionId"],
            "targetNodeId": command["targetNodeId"],
            "stage": stage,
            "occurredAt": NOW.isoformat(),
            "correlationId": command["correlationId"],
            "details": {},
        },
        "sentAt": NOW.isoformat(),
    }


def test_agent_mesh_adapter_round_trip_and_durable_acknowledgements(
    tmp_path: Path,
) -> None:
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "runtime.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=bootstrap_identities(),
        )
    ) as client:
        with client.websocket_connect("/api/v1/adapters/connect") as websocket:
            websocket.send_json(
                {
                    "frameType": "adapter.authenticate",
                    "frameId": str(uuid4()),
                    "protocolVersion": 1,
                    "credential": ADAPTER_TOKEN,
                    "sentAt": NOW.isoformat(),
                }
            )
            assert websocket.receive_json()["frameType"] == "adapter.welcome"
            websocket.send_json(registration_frame())
            registered = websocket.receive_json()
            assert registered["frameType"] == "adapter.registered"
            assert registered["registeredNodeIds"] == [
                "g2-sim-a",
                "codex-session-sim-a",
            ]

            session_id = create_started_session(client)
            prompt_frame_id = str(uuid4())
            prompt_message_id = str(uuid4())
            correlation_id = "interaction-a"
            prompt_event = adapter_event(
                frame_id=prompt_frame_id,
                message_id=prompt_message_id,
                session_id=session_id,
                node_id="g2-sim-a",
                capability_name="interaction.intent.agent_prompt",
                sequence=1,
                data_classification="voice_transcript",
                payload={"text": "Summarize the current tests."},
                correlation_id=correlation_id,
            )
            websocket.send_json(prompt_event)
            prompt_command_frame = websocket.receive_json()
            prompt_ack = websocket.receive_json()
            assert prompt_command_frame["frameType"] == "adapter.command"
            prompt_command = prompt_command_frame["command"]
            assert prompt_command["action"] == "agent.prompt.submit"
            assert prompt_command["targetNodeId"] == "codex-session-sim-a"
            assert prompt_command["parameters"] == {"prompt": "Summarize the current tests."}
            assert prompt_command["correlationId"] == correlation_id
            assert prompt_ack["frameType"] == "adapter.ack"
            assert prompt_ack["acknowledgedFrameId"] == prompt_frame_id
            assert prompt_ack["status"] == "accepted"
            assert prompt_ack["streamSequence"] >= 1

            websocket.send_json(prompt_event)
            duplicate_ack = websocket.receive_json()
            assert duplicate_ack["frameType"] == "adapter.ack"
            assert duplicate_ack["status"] == "duplicate"

            for stage in ("ACCEPTED", "SUCCEEDED"):
                report = lifecycle_frame(prompt_command, stage)
                websocket.send_json(report)
                lifecycle_ack = websocket.receive_json()
                assert lifecycle_ack["frameType"] == "adapter.ack"
                assert lifecycle_ack["acknowledgedFrameId"] == report["frameId"]
                assert lifecycle_ack["status"] == "accepted"

            output_frame_id = str(uuid4())
            websocket.send_json(
                adapter_event(
                    frame_id=output_frame_id,
                    message_id=str(uuid4()),
                    session_id=session_id,
                    node_id="codex-session-sim-a",
                    capability_name="agent.output.completed",
                    sequence=1,
                    data_classification="source_code",
                    payload={"displayText": "All selected tests pass."},
                    correlation_id=correlation_id,
                )
            )
            display_command_frame = websocket.receive_json()
            output_ack = websocket.receive_json()
            assert display_command_frame["frameType"] == "adapter.command"
            display_command = display_command_frame["command"]
            assert display_command["action"] == "display.text.render"
            assert display_command["targetNodeId"] == "g2-sim-a"
            assert display_command["parameters"] == {"text": "All selected tests pass."}
            assert output_ack["acknowledgedFrameId"] == output_frame_id

            lifecycle = client.get(
                "/api/v1/fabric/commands/lifecycle",
                headers=ADMIN_HEADERS,
                params={"commandId": prompt_command["commandId"]},
            )
            assert lifecycle.status_code == 200
            assert [item["lifecycle"]["stage"] for item in lifecycle.json()] == [
                "PROPOSED",
                "VALIDATED",
                "AUTHORIZED",
                "DISPATCHED",
                "ACCEPTED",
                "SUCCEEDED",
            ]

        nodes = client.get("/api/v1/fabric/nodes", headers=ADMIN_HEADERS)
        states = {item["nodeId"]: item["connectionState"] for item in nodes.json()}
        assert states["g2-sim-a"] == "disconnected"
        assert states["codex-session-sim-a"] == "disconnected"


def test_adapter_protocol_closes_cleanly_for_unknown_session_state(tmp_path: Path) -> None:
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "runtime.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=bootstrap_identities(),
        )
    ) as client:
        with client.websocket_connect("/api/v1/adapters/connect") as websocket:
            websocket.send_json(
                {
                    "frameType": "adapter.authenticate",
                    "frameId": str(uuid4()),
                    "protocolVersion": 1,
                    "credential": ADAPTER_TOKEN,
                    "sentAt": NOW.isoformat(),
                }
            )
            assert websocket.receive_json()["frameType"] == "adapter.welcome"
            websocket.send_json(registration_frame())
            assert websocket.receive_json()["frameType"] == "adapter.registered"
            websocket.send_json(
                adapter_event(
                    frame_id=str(uuid4()),
                    message_id=str(uuid4()),
                    session_id="unknown-session",
                    node_id="g2-sim-a",
                    capability_name="interaction.intent.agent_prompt",
                    sequence=1,
                    data_classification="voice_transcript",
                    payload={"text": "This must not reach an agent."},
                    correlation_id="unknown-session-test",
                )
            )
            with pytest.raises(WebSocketDisconnect) as disconnected:
                websocket.receive_json()

    assert disconnected.value.code == 4404


def test_paused_session_discards_events_without_disconnecting_adapter(
    tmp_path: Path,
) -> None:
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "runtime.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=bootstrap_identities(),
        )
    ) as client:
        with client.websocket_connect("/api/v1/adapters/connect") as websocket:
            websocket.send_json(
                {
                    "frameType": "adapter.authenticate",
                    "frameId": str(uuid4()),
                    "protocolVersion": 1,
                    "credential": ADAPTER_TOKEN,
                    "sentAt": NOW.isoformat(),
                }
            )
            assert websocket.receive_json()["frameType"] == "adapter.welcome"
            websocket.send_json(registration_frame())
            assert websocket.receive_json()["frameType"] == "adapter.registered"

            session_id = create_started_session(client)
            paused = client.post(
                f"/api/v1/fabric/sessions/{session_id}/pause",
                headers=ADMIN_HEADERS,
            )
            assert paused.status_code == 200

            paused_frame_id = str(uuid4())
            websocket.send_json(
                adapter_event(
                    frame_id=paused_frame_id,
                    message_id=str(uuid4()),
                    session_id=session_id,
                    node_id="g2-sim-a",
                    capability_name="interaction.intent.agent_prompt",
                    sequence=1,
                    data_classification="voice_transcript",
                    payload={"text": "Discard this observation while paused."},
                    correlation_id="paused-observation",
                )
            )
            paused_ack = websocket.receive_json()
            assert paused_ack["frameType"] == "adapter.ack"
            assert paused_ack["acknowledgedFrameId"] == paused_frame_id
            assert paused_ack["status"] == "accepted"
            assert paused_ack.get("streamSequence") is None

            recorded = client.get(
                "/api/v1/fabric/events",
                headers=ADMIN_HEADERS,
                params={"sessionId": session_id},
            )
            assert recorded.status_code == 200
            assert recorded.json() == []
            nodes = client.get("/api/v1/fabric/nodes", headers=ADMIN_HEADERS)
            assert nodes.status_code == 200
            assert {item["connectionState"] for item in nodes.json()} == {"connected"}

            resumed = client.post(
                f"/api/v1/fabric/sessions/{session_id}/start",
                headers=ADMIN_HEADERS,
            )
            assert resumed.status_code == 200
            active_frame_id = str(uuid4())
            websocket.send_json(
                adapter_event(
                    frame_id=active_frame_id,
                    message_id=str(uuid4()),
                    session_id=session_id,
                    node_id="g2-sim-a",
                    capability_name="interaction.intent.agent_prompt",
                    sequence=2,
                    data_classification="voice_transcript",
                    payload={"text": "Route this observation after resume."},
                    correlation_id="resumed-observation",
                )
            )
            assert websocket.receive_json()["frameType"] == "adapter.command"
            active_ack = websocket.receive_json()
            assert active_ack["acknowledgedFrameId"] == active_frame_id
            assert active_ack["streamSequence"] >= 1


def test_safe_off_result_does_not_disconnect_matter_adapter(tmp_path: Path) -> None:
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "runtime.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=bootstrap_identities(),
            allow_physical_fabric=True,
        )
    ) as client:
        with client.websocket_connect("/api/v1/adapters/connect") as websocket:
            websocket.send_json(
                {
                    "frameType": "adapter.authenticate",
                    "frameId": str(uuid4()),
                    "protocolVersion": 1,
                    "credential": MATTER_ADAPTER_TOKEN,
                    "sentAt": NOW.isoformat(),
                }
            )
            assert websocket.receive_json()["frameType"] == "adapter.welcome"
            websocket.send_json(matter_registration_frame())
            assert websocket.receive_json()["frameType"] == "adapter.registered"

            created = client.post(
                "/api/v1/fabric/sessions",
                headers=ADMIN_HEADERS,
                json={
                    "coursePackId": "smart-plug-control",
                    "coursePackVersion": "1.0.0",
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "mode": "physical",
                },
            )
            assert created.status_code == 201
            session_id = str(created.json()["sessionId"])
            assigned = client.put(
                f"/api/v1/fabric/sessions/{session_id}/roles/classroom_plug",
                headers=ADMIN_HEADERS,
                json={"nodeId": "matter-8-ep1"},
            )
            assert assigned.status_code == 200
            assert assigned.json()["state"] == "ready"

            correlation_id = str(uuid4())
            requested = client.post(
                "/api/v1/fabric/commands",
                headers=ADMIN_HEADERS,
                json={
                    "messageId": str(uuid4()),
                    "schemaVersion": "1.0",
                    "messageType": "command.requested",
                    "action": "power.switch.set",
                    "target": {"role": "classroom_plug"},
                    "sessionId": session_id,
                    "parameters": {"on": False},
                    "priority": "instructor_override",
                    "idempotencyKey": str(uuid4()),
                    "requestedAt": NOW.isoformat(),
                    "ttlMs": 2_000,
                    "safetyProfile": "classroom-smart-plug",
                    "correlationId": correlation_id,
                },
            )
            assert requested.status_code == 202
            command_frame = websocket.receive_json()
            assert command_frame["frameType"] == "adapter.command"
            command = command_frame["command"]

            for stage in ("ACCEPTED", "RUNNING", "SUCCEEDED"):
                reported = lifecycle_frame(command, stage)
                websocket.send_json(reported)
                assert websocket.receive_json()["acknowledgedFrameId"] == reported["frameId"]

            state_frame_id = str(uuid4())
            websocket.send_json(
                adapter_event(
                    frame_id=state_frame_id,
                    message_id=str(uuid4()),
                    session_id=session_id,
                    node_id="matter-8-ep1",
                    capability_name="power.switch.state",
                    sequence=1,
                    data_classification="operational",
                    payload={"on": False, "source": "command"},
                    correlation_id=correlation_id,
                    causation_id=command["commandId"],
                )
            )
            state_ack = websocket.receive_json()
            assert state_ack["frameType"] == "adapter.ack"
            assert state_ack["acknowledgedFrameId"] == state_frame_id
            assert state_ack["status"] == "accepted"

            electrical_frame_id = str(uuid4())
            websocket.send_json(
                adapter_event(
                    frame_id=electrical_frame_id,
                    message_id=str(uuid4()),
                    session_id=session_id,
                    node_id="matter-8-ep1",
                    capability_name="telemetry.power.electrical",
                    sequence=2,
                    data_classification="operational",
                    payload={
                        "activePowerWatts": 0.0,
                        "source": "command",
                        "standard": "Matter 1.3",
                    },
                    correlation_id=correlation_id,
                    causation_id=command["commandId"],
                )
            )
            electrical_ack = websocket.receive_json()
            assert electrical_ack["frameType"] == "adapter.ack"
            assert electrical_ack["acknowledgedFrameId"] == electrical_frame_id
            assert electrical_ack["status"] == "accepted"

            nodes = client.get("/api/v1/fabric/nodes", headers=ADMIN_HEADERS)
            assert nodes.status_code == 200
            [plug] = [item for item in nodes.json() if item["nodeId"] == "matter-8-ep1"]
            assert plug["connectionState"] == "connected"
            recorded = client.get(
                "/api/v1/fabric/events",
                headers=ADMIN_HEADERS,
                params={"sessionId": session_id},
            )
            assert recorded.status_code == 200
            assert [item["event"]["payload"] for item in recorded.json()] == [
                {"on": False, "source": "command"},
                {
                    "activePowerWatts": 0.0,
                    "source": "command",
                    "standard": "Matter 1.3",
                },
            ]


def test_adapter_conflict_logs_safe_frame_context_and_exact_code(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="cit_runtime.fabric_adapters")
    with TestClient(
        create_fabric_app(
            database_path=tmp_path / "runtime.sqlite3",
            clock=lambda: NOW,
            fabric_bootstrap_identities=bootstrap_identities(),
        )
    ) as client:
        with client.websocket_connect("/api/v1/adapters/connect") as websocket:
            websocket.send_json(
                {
                    "frameType": "adapter.authenticate",
                    "frameId": str(uuid4()),
                    "protocolVersion": 1,
                    "credential": ADAPTER_TOKEN,
                    "sentAt": NOW.isoformat(),
                }
            )
            assert websocket.receive_json()["frameType"] == "adapter.welcome"
            websocket.send_json(registration_frame())
            assert websocket.receive_json()["frameType"] == "adapter.registered"

            created = client.post(
                "/api/v1/fabric/sessions",
                headers=ADMIN_HEADERS,
                json={
                    "coursePackId": "glasses-agent-control",
                    "coursePackVersion": "1.0.0",
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "mode": "simulation",
                },
            )
            assert created.status_code == 201
            session_id = str(created.json()["sessionId"])
            for role, node_id in (
                ("primary_glasses", "g2-sim-a"),
                ("coding_agent", "codex-session-sim-a"),
            ):
                assigned = client.put(
                    f"/api/v1/fabric/sessions/{session_id}/roles/{role}",
                    headers=ADMIN_HEADERS,
                    json={"nodeId": node_id},
                )
                assert assigned.status_code == 200

            websocket.send_json(
                adapter_event(
                    frame_id=str(uuid4()),
                    message_id=str(uuid4()),
                    session_id=session_id,
                    node_id="g2-sim-a",
                    capability_name="interaction.intent.agent_prompt",
                    sequence=1,
                    data_classification="voice_transcript",
                    payload={"text": "do-not-log-this-prompt"},
                    correlation_id="inactive-session-observation",
                )
            )
            with pytest.raises(WebSocketDisconnect) as disconnected:
                websocket.receive_json()

    assert disconnected.value.code == 4409
    assert "SESSION_NOT_ACTIVE" in disconnected.value.reason
    diagnostic = "\n".join(record.getMessage() for record in caplog.records)
    assert "code=SESSION_NOT_ACTIVE" in diagnostic
    assert "frame_type=adapter.event" in diagnostic
    assert f"session_id={session_id}" in diagnostic
    assert "node_id=g2-sim-a" in diagnostic
    assert "do-not-log-this-prompt" not in diagnostic
    assert ADAPTER_TOKEN not in diagnostic
