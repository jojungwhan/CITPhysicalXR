"""Cloud-independent Matter smart-plug integration."""

from .backend import MatterSmartPlug, MatterSmartPlugConfiguration, SmartPlugError
from .contract import (
    ELECTRICAL_STATE_CAPABILITY,
    PLUGIN_ID,
    POWER_SET_CAPABILITY,
    POWER_STATE_CAPABILITY,
    build_manifest,
    build_node,
)
from .matter_client import (
    ElectricalMeasurements,
    MatterCommissionableDevice,
    MatterEndpoint,
    MatterServerClient,
    discover_plug_endpoints,
    extract_electrical_measurements,
)

__all__ = [
    "ELECTRICAL_STATE_CAPABILITY",
    "PLUGIN_ID",
    "POWER_SET_CAPABILITY",
    "POWER_STATE_CAPABILITY",
    "ElectricalMeasurements",
    "MatterCommissionableDevice",
    "MatterEndpoint",
    "MatterServerClient",
    "MatterSmartPlug",
    "MatterSmartPlugConfiguration",
    "SmartPlugError",
    "build_manifest",
    "build_node",
    "discover_plug_endpoints",
    "extract_electrical_measurements",
]
