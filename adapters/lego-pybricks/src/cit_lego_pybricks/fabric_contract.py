"""Canonical Fabric contract for the existing Pybricks hub adapter."""

from __future__ import annotations

from datetime import datetime

from cit_integration_sdk import capability_descriptor, capability_name
from cit_protocol import IntegrationNode, PluginManifest

from .adapter import ADAPTER_VERSION, PybricksHubAdapter

PLUGIN_ID = "cit.lego-pybricks"
GROUND_VELOCITY_CAPABILITY = capability_name("ground_velocity")
GROUND_STOP_CAPABILITY = capability_name("ground_stop")
SENSOR_STATE_CAPABILITY = capability_name("robot_sensor_state")
BATTERY_STATE_CAPABILITY = capability_name("robot_battery_state")


def build_manifest() -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": PLUGIN_ID,
            "pluginVersion": ADAPTER_VERSION,
            "runtimeVersion": "python-3.11",
            "displayName": "LEGO SPIKE / MINDSTORMS through Pybricks",
            "adapterMode": "out_of_process",
            "configurationSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["hubName", "hubModel", "ports", "mode"],
                "properties": {
                    "hubName": {"type": "string"},
                    "hubModel": {"type": "string"},
                    "ports": {"type": "object"},
                    "mode": {"enum": ["simulation", "pybricks-ble"]},
                },
            },
            "publishedCapabilities": [
                capability_descriptor("robot_sensor_state", "publish"),
                capability_descriptor("robot_battery_state", "publish"),
            ],
            "consumedCapabilities": [
                capability_descriptor("ground_velocity", "consume"),
                capability_descriptor("ground_stop", "consume"),
            ],
            "requiredPermissions": ["bluetooth"],
            "safetyClassification": "bounded_physical",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "included",
            "vendor": "Pybricks",
            "description": (
                "Wraps the existing framed hub adapter. The node advertises ground "
                "mobility only when the configured hub reports at least two motors."
            ),
        }
    )


def build_node(
    adapter: PybricksHubAdapter,
    *,
    at: datetime,
    host_id: str,
    site_id: str,
    room_id: str,
    simulated: bool,
) -> IntegrationNode:
    mobile = "drive.velocity" in adapter.capabilities
    published = [
        capability_descriptor("robot_sensor_state", "publish"),
        capability_descriptor("robot_battery_state", "publish"),
    ]
    consumed = (
        [
            capability_descriptor("ground_velocity", "consume"),
            capability_descriptor("ground_stop", "consume"),
        ]
        if mobile
        else []
    )
    return IntegrationNode.model_validate(
        {
            "schemaVersion": "1.0",
            "nodeId": adapter.device_id,
            "pluginId": PLUGIN_ID,
            "pluginVersion": ADAPTER_VERSION,
            "runtimeVersion": "python-3.11",
            "displayName": adapter.display_name,
            "hostId": host_id,
            "siteId": site_id,
            "roomId": room_id,
            "physical": not simulated,
            "simulated": simulated,
            "connectionState": "connected",
            "healthState": "healthy",
            "publishedCapabilities": published,
            "consumedCapabilities": consumed,
            "configurationSchema": {},
            "safetyClassification": "bounded_physical",
            "dataClassifications": ["operational"],
            "simulatorAvailable": True,
            "requiredPermissions": [] if simulated else ["bluetooth"],
            "lastSeenAt": at,
            "metadata": {
                "model": adapter.model.model_id,
                "transport": "simulation" if simulated else "pybricks-ble",
                "ports": {port: kind.value for port, kind in adapter.ports.items()},
                "legacyCapabilities": list(adapter.capabilities),
                "groundMobility": mobile,
                "watchdogMilliseconds": 500,
            },
        }
    )
