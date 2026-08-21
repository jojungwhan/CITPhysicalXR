from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from cit_protocol import (
    AdapterRegistrationFrame,
    CoursePack,
    FabricEventEnvelope,
    IntegrationNode,
    PluginManifest,
)
from cit_protocol.generated import CitEnvelope, DeviceCommandIntent, DeviceDescriptor, DeviceEvent
from cit_protocol.validation import to_wire, validate_definition
from pydantic import ValidationError

FIXTURES = Path(__file__).parents[2] / "protocol-schema" / "fixtures"


def fixture(name: str) -> dict[str, Any]:
    value: object = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"Protocol fixture {name} is not an object")
    return value


def test_generated_models_and_json_schema_accept_shared_protocol_fixtures() -> None:
    envelope = CitEnvelope.model_validate(fixture("valid-envelope.json"))
    command = DeviceCommandIntent.model_validate(fixture("valid-command.json"))
    event = DeviceEvent.model_validate(fixture("valid-event.json"))
    device = DeviceDescriptor.model_validate(fixture("valid-device.json"))

    assert validate_definition("CitEnvelope", to_wire(envelope)) == []
    assert validate_definition("DeviceCommandIntent", to_wire(command)) == []
    assert validate_definition("DeviceEvent", to_wire(event)) == []
    assert validate_definition("DeviceDescriptor", to_wire(device)) == []
    assert "clientId" not in to_wire(envelope)
    assert command.deviceId == "fake-s1-main"


def test_transport_neutral_fabric_contracts_share_schema_and_python_models() -> None:
    manifest = PluginManifest.model_validate(fixture("valid-plugin-manifest.json"))
    node = IntegrationNode.model_validate(fixture("valid-integration-node.json"))
    event = FabricEventEnvelope.model_validate(fixture("valid-fabric-event.json"))
    course_pack = CoursePack.model_validate(fixture("valid-course-pack.json"))
    registration = AdapterRegistrationFrame.model_validate(
        fixture("valid-adapter-registration.json")
    )

    for definition, model in (
        ("PluginManifest", manifest),
        ("IntegrationNode", node),
        ("FabricEventEnvelope", event),
        ("CoursePack", course_pack),
        ("AdapterRegistrationFrame", registration),
    ):
        assert validate_definition(definition, to_wire(model)) == []
    assert registration.nodes[0].pluginId == manifest.pluginId
    assert course_pack.flows[0].target.role == "coding_agent"


def test_generated_models_reject_unknown_version_and_missing_device_identity() -> None:
    bad_envelope = {**fixture("valid-envelope.json"), "protocolVersion": 2}
    bad_command = fixture("valid-command.json")
    del bad_command["deviceId"]

    with pytest.raises(ValidationError):
        CitEnvelope.model_validate(bad_envelope)
    with pytest.raises(ValidationError):
        DeviceCommandIntent.model_validate(bad_command)
