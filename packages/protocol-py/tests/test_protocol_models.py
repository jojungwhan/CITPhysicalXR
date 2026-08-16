from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
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


def test_generated_models_reject_unknown_version_and_missing_device_identity() -> None:
    bad_envelope = {**fixture("valid-envelope.json"), "protocolVersion": 2}
    bad_command = fixture("valid-command.json")
    del bad_command["deviceId"]

    with pytest.raises(ValidationError):
        CitEnvelope.model_validate(bad_envelope)
    with pytest.raises(ValidationError):
        DeviceCommandIntent.model_validate(bad_command)
