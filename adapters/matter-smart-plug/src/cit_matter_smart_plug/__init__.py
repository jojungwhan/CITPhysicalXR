"""Cloud-independent Matter smart-plug integration."""

from .backend import MatterSmartPlug, MatterSmartPlugConfiguration, SmartPlugError
from .contract import (
    PLUGIN_ID,
    POWER_SET_CAPABILITY,
    POWER_STATE_CAPABILITY,
    build_manifest,
    build_node,
)
from .matter_client import MatterEndpoint, MatterServerClient, discover_plug_endpoints

__all__ = [
    "PLUGIN_ID",
    "POWER_SET_CAPABILITY",
    "POWER_STATE_CAPABILITY",
    "MatterEndpoint",
    "MatterServerClient",
    "MatterSmartPlug",
    "MatterSmartPlugConfiguration",
    "SmartPlugError",
    "build_manifest",
    "build_node",
    "discover_plug_endpoints",
]
