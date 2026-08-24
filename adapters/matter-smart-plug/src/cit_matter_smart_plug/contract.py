"""Canonical capability declarations for standard Matter plug endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from cit_integration_sdk import capability_descriptor, capability_name
from cit_protocol import IntegrationNode, PluginManifest

PLUGIN_ID = "cit.matter-smart-plug"
PLUGIN_VERSION = "0.2.0"
RUNTIME_VERSION = "python-3.11"
MATTER_SERVER_VERSION = "1.4.0"

POWER_SET_CAPABILITY = capability_name("power_switch_set")
POWER_STATE_CAPABILITY = capability_name("power_switch_state")
ELECTRICAL_STATE_CAPABILITY = capability_name("power_electrical_state")


def _state_capability() -> dict[str, Any]:
    return capability_descriptor("power_switch_state", "publish")


def _set_capability() -> dict[str, Any]:
    return capability_descriptor("power_switch_set", "consume")


def _electrical_capability() -> dict[str, Any]:
    return capability_descriptor("power_electrical_state", "publish")


def build_manifest() -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": PLUGIN_ID,
            "pluginVersion": PLUGIN_VERSION,
            "runtimeVersion": RUNTIME_VERSION,
            "displayName": "Cloud-free Matter smart plug",
            "adapterMode": "out_of_process",
            "configurationSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["matterNodeId", "endpointId", "controllerAlias"],
                "properties": {
                    "matterNodeId": {"type": "string"},
                    "endpointId": {"type": "integer", "minimum": 1, "maximum": 65535},
                    "controllerAlias": {"const": "local-cit-matter"},
                },
            },
            "publishedCapabilities": [_state_capability(), _electrical_capability()],
            "consumedCapabilities": [_set_capability()],
            "requiredPermissions": ["local_network"],
            "safetyClassification": "electrical",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "external",
            "vendor": f"Matter through Open Home Foundation Matter Server {MATTER_SERVER_VERSION}",
            "description": (
                "Controls only the standard Matter OnOff Plug-in Unit device type over the "
                "local Matter fabric. No proprietary vendor account, key, API, or cloud is used."
            ),
        }
    )


def build_node(
    *,
    at: datetime,
    host_id: str,
    site_id: str,
    room_id: str,
    node_id: str,
    matter_node_id: int,
    endpoint_id: int,
    display_name: str,
    vendor_name: str,
    product_name: str,
    electrical_telemetry: bool = False,
) -> IntegrationNode:
    published_capabilities = [_state_capability()]
    if electrical_telemetry:
        published_capabilities.append(_electrical_capability())
    return IntegrationNode.model_validate(
        {
            "schemaVersion": "1.0",
            "nodeId": node_id,
            "pluginId": PLUGIN_ID,
            "pluginVersion": PLUGIN_VERSION,
            "runtimeVersion": RUNTIME_VERSION,
            "hostId": host_id,
            "siteId": site_id,
            "roomId": room_id,
            "displayName": display_name,
            "connectionState": "connected",
            "healthState": "healthy",
            "physical": True,
            "simulated": False,
            "publishedCapabilities": published_capabilities,
            "consumedCapabilities": [_set_capability()],
            "configurationSchema": {},
            "safetyClassification": "electrical",
            "dataClassifications": ["operational"],
            "simulatorAvailable": False,
            "requiredPermissions": ["local_network"],
            "lastSeenAt": at,
            "metadata": {
                "vendorBrand": vendor_name or "Matter",
                "model": product_name or "On/Off Plug-in Unit",
                "transport": "matter-local-ipv6",
                "controller": "local-cit-matter",
                "matterNodeId": str(matter_node_id),
                "endpointId": endpoint_id,
                "matterDeviceType": "0x010A",
                "safeState": "off",
                "cloudDependency": False,
                "vendorAccountRequired": False,
                "arbitraryClustersExposed": False,
                "electricalTelemetry": electrical_telemetry,
            },
        }
    )
