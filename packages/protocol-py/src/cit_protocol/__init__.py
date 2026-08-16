"""Generated protocol models and schema validation for CIT Physical XR."""

from .generated import (
    CitEnvelope,
    CommandResult,
    DeviceCommandIntent,
    DeviceDescriptor,
    DeviceEvent,
    ProtocolError,
)
from .validation import to_wire, validate_definition

__all__ = [
    "CitEnvelope",
    "CommandResult",
    "DeviceCommandIntent",
    "DeviceDescriptor",
    "DeviceEvent",
    "ProtocolError",
    "to_wire",
    "validate_definition",
]
