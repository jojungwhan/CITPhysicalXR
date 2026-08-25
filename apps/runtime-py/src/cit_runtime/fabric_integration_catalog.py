"""Authoritative integration metadata and node-selection rules.

Dynamic host probes report status and candidates. Human-facing setup text and
capability-based matching come from the generated catalog so adding an adapter
does not require another branch in the Fabric core or browser UI.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Literal

from cit_protocol import IntegrationNode
from pydantic import BaseModel, ConfigDict, Field, model_validator


class IntegrationNodeSelectors(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pluginIds: list[str] = Field(default_factory=list, max_length=16)
    capabilityAny: list[str] = Field(default_factory=list, max_length=32)
    models: list[str] = Field(default_factory=list, max_length=16)


class IntegrationDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    integrationId: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=96)
    displayName: str = Field(min_length=1, max_length=160)
    category: Literal[
        "interaction",
        "sensor",
        "robot",
        "drone",
        "smart_device",
        "coding_agent",
    ]
    ioType: Literal["input", "output", "bidirectional"]
    icon: Literal[
        "brain",
        "drone",
        "glasses",
        "hand",
        "lego",
        "plug",
        "robot",
        "ring",
        "sphero",
        "terminal",
        "wonder",
    ]
    imagePath: str = Field(
        pattern=r"^\./device-images/[a-z0-9][a-z0-9._-]*\.webp$",
        max_length=160,
    )
    connectionMethod: str = Field(min_length=1, max_length=160)
    setupSteps: list[str] = Field(min_length=1, max_length=8)
    safetyNote: str = Field(min_length=1, max_length=500)
    selectors: IntegrationNodeSelectors

    def matches(self, node: IntegrationNode) -> bool:
        selectors = self.selectors
        if selectors.pluginIds and node.pluginId not in selectors.pluginIds:
            return False
        capabilities = {
            capability.name
            for capability in (*node.publishedCapabilities, *node.consumedCapabilities)
        }
        if selectors.capabilityAny and not capabilities.intersection(selectors.capabilityAny):
            return False
        metadata = node.metadata.model_dump(mode="python")
        model = str(metadata.get("model", ""))
        if selectors.models and model not in selectors.models:
            return False
        return True


class IntegrationCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["1.0"]
    integrations: list[IntegrationDescriptor] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def unique_integration_ids(self) -> IntegrationCatalog:
        identifiers = [item.integrationId for item in self.integrations]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Integration catalog IDs must be unique")
        return self

    def require(self, integration_id: str) -> IntegrationDescriptor:
        for descriptor in self.integrations:
            if descriptor.integrationId == integration_id:
                return descriptor
        raise KeyError(f"Unknown integration catalog ID {integration_id!r}")


@lru_cache(maxsize=1)
def load_integration_catalog() -> IntegrationCatalog:
    resource = files("cit_runtime").joinpath("integration-catalog.generated.json")
    value: object = json.loads(resource.read_text(encoding="utf-8"))
    return IntegrationCatalog.model_validate(value)
