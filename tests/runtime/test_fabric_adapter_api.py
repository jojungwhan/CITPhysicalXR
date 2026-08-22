from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
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
) -> dict[str, Any]:
    return {
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
