"""Canonical Tello capability and node declarations."""

from __future__ import annotations

from datetime import datetime

from cit_integration_sdk import capability_descriptor, capability_name, external_source
from cit_protocol import IntegrationNode, PluginManifest

PLUGIN_ID = "cit.tello"
PLUGIN_VERSION = "0.1.0"
RUNTIME_VERSION = "python-3.11"
BRAIN2DEVICES_REVISION = external_source("brain2devices").revision

LAND_CAPABILITY = capability_name("flight_land")
EMERGENCY_STOP_CAPABILITY = capability_name("flight_emergency_stop")
TELEMETRY_CAPABILITY = capability_name("flight_telemetry")


def build_manifest() -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": PLUGIN_ID,
            "pluginVersion": PLUGIN_VERSION,
            "runtimeVersion": RUNTIME_VERSION,
            "displayName": "DJI / Ryze Tello (Brain2Devices port)",
            "adapterMode": "out_of_process",
            "configurationSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["mode"],
                "properties": {
                    "mode": {"enum": ["simulation", "brain2devices", "brain2devices-api"]},
                    "brain2devicesRepository": {"type": "string"},
                    "brain2devicesRevision": {"const": BRAIN2DEVICES_REVISION},
                    "ipAddress": {"type": ["string", "null"]},
                    "brain2devicesOrigin": {"const": "http://127.0.0.1:8765"},
                    "brain2devicesDroneId": {"type": "string"},
                },
            },
            "publishedCapabilities": [capability_descriptor("flight_telemetry", "publish")],
            # The first safe slice intentionally excludes takeoff and movement.
            "consumedCapabilities": [
                capability_descriptor("flight_land", "consume"),
                capability_descriptor("flight_emergency_stop", "consume"),
            ],
            "requiredPermissions": ["network.local.udp"],
            "safetyClassification": "flight",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "included",
            "vendor": "CIT wrapper of local Brain2Devices",
            "description": (
                "Runs independently from MindWave and exposes telemetry plus local safe-state "
                "commands. Takeoff and movement stay unavailable until the Fabric flight "
                "policy is implemented and hardware-validated."
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
    simulated: bool,
    ip_address: str | None,
    brain2devices_drone_id: str | None = None,
) -> IntegrationNode:
    return IntegrationNode.model_validate(
        {
            "schemaVersion": "1.0",
            "nodeId": node_id,
            "pluginId": PLUGIN_ID,
            "pluginVersion": PLUGIN_VERSION,
            "runtimeVersion": RUNTIME_VERSION,
            "displayName": "Simulated Tello" if simulated else "DJI / Ryze Tello",
            "hostId": host_id,
            "siteId": site_id,
            "roomId": room_id,
            "physical": not simulated,
            "simulated": simulated,
            "connectionState": "connected",
            "healthState": "healthy",
            "publishedCapabilities": [capability_descriptor("flight_telemetry", "publish")],
            "consumedCapabilities": [
                capability_descriptor("flight_land", "consume"),
                capability_descriptor("flight_emergency_stop", "consume"),
            ],
            "configurationSchema": {},
            "safetyClassification": "flight",
            "dataClassifications": ["operational"],
            "simulatorAvailable": True,
            "requiredPermissions": ["network.local.udp"],
            "lastSeenAt": at,
            "metadata": {
                "model": "tello",
                "transport": "simulation" if simulated else "brain2devices-port",
                "ipAddress": ip_address,
                "brain2devicesRevision": BRAIN2DEVICES_REVISION,
                "brain2devicesDroneId": brain2devices_drone_id,
                "flightCommandsEnabled": [LAND_CAPABILITY, EMERGENCY_STOP_CAPABILITY],
                "takeoffEnabled": False,
            },
        }
    )
