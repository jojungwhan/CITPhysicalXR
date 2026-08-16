"""Validate wire values against named definitions in the committed protocol schema."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel


def _load_schema() -> dict[str, Any]:
    resource = files("cit_protocol").joinpath("cit-protocol.schema.json")
    value: object = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Protocol schema root must be an object")
    return value


_SCHEMA = _load_schema()
_definitions_value: object = _SCHEMA.get("$defs")
if not isinstance(_definitions_value, dict):
    raise RuntimeError("Protocol schema is missing $defs")
_DEFINITIONS: dict[str, Any] = _definitions_value


def to_wire(model: BaseModel) -> dict[str, Any]:
    """Serialize a generated model using the JSON wire contract.

    Optional fields are omitted rather than emitted as explicit nulls because the
    protocol distinguishes absence from a nullable value.
    """

    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def validate_definition(name: str, value: object) -> list[str]:
    """Return stable, human-readable validation errors for one public definition."""

    if name not in _DEFINITIONS:
        raise ValueError(f"Unknown protocol definition: {name}")
    wrapper = {
        "$schema": _SCHEMA["$schema"],
        "$defs": _DEFINITIONS,
        "$ref": f"#/$defs/{name}",
    }
    validator = Draft202012Validator(wrapper, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(value), key=lambda error: tuple(str(p) for p in error.path)
    )
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in errors
    ]
