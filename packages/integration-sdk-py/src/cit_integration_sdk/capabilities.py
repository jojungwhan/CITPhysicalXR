"""Read capability profiles generated from the language-neutral catalog."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any, Literal

CapabilityDirection = Literal["publish", "consume"]


@lru_cache(maxsize=1)
def _catalog() -> dict[str, dict[str, Any]]:
    resource = files("cit_integration_sdk").joinpath("capability-catalog.generated.json")
    value: object = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schemaVersion") != "1.0":
        raise RuntimeError("Packaged CIT capability catalog is invalid")
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, dict):
        raise RuntimeError("Packaged CIT capability catalog has no capabilities")
    result: dict[str, dict[str, Any]] = {}
    for key, descriptor in capabilities.items():
        if not isinstance(key, str) or not isinstance(descriptor, dict):
            raise RuntimeError("Packaged CIT capability catalog contains an invalid entry")
        result[key] = descriptor
    return result


def capability_name(key: str) -> str:
    """Return the canonical capability name for a stable catalog key."""

    value = _catalog().get(key)
    if value is None:
        raise KeyError(f"Unknown CIT capability profile {key!r}")
    name = value.get("name")
    if not isinstance(name, str) or not name:
        raise RuntimeError(f"CIT capability profile {key!r} has no valid name")
    return name


def capability_descriptor(
    key: str,
    direction: CapabilityDirection,
    *,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Materialize one protocol descriptor without mutating the catalog."""

    value = _catalog().get(key)
    if value is None:
        raise KeyError(f"Unknown CIT capability profile {key!r}")
    descriptor = {
        **value,
        "direction": direction,
        "schemaRef": None,
        "units": None,
    }
    if constraints is not None:
        descriptor["constraints"] = constraints
    descriptor.setdefault("constraints", {})
    return descriptor
