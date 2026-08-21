"""Hand-authored validation layered over generated Fabric protocol models."""

from __future__ import annotations

from pydantic import field_validator

from .generated import CreateInteractionSessionRequest as GeneratedCreateInteractionSessionRequest
from .generated import Identifier


class CreateInteractionSessionRequest(GeneratedCreateInteractionSessionRequest):
    """Fabric session request with JSON Schema uniqueness enforced at runtime."""

    @field_validator("participantIds")
    @classmethod
    def unique_participant_ids(
        cls,
        values: list[Identifier] | None,
    ) -> list[Identifier] | None:
        if values is None:
            return None
        identifiers = [value.root for value in values]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("participantIds must contain unique IDs")
        return values
