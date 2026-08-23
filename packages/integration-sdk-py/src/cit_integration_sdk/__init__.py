"""Stable helpers shared by independently deployed Fabric adapters."""

from .capabilities import capability_descriptor, capability_name
from .client import AdapterSocket, FabricAdapterClient, FabricConnectionConfiguration
from .replay import CommandReplayCache
from .sources import (
    ExternalSource,
    ExternalSourceCheckoutError,
    external_source,
    verify_external_git_checkout,
)

__all__ = [
    "AdapterSocket",
    "CommandReplayCache",
    "ExternalSource",
    "ExternalSourceCheckoutError",
    "FabricAdapterClient",
    "FabricConnectionConfiguration",
    "capability_descriptor",
    "capability_name",
    "external_source",
    "verify_external_git_checkout",
]
