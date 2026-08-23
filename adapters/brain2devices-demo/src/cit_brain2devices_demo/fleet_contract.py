"""Canonical contract for an instructor-armed Brain2Devices fleet sequence."""

from __future__ import annotations

from datetime import datetime

from cit_integration_sdk import capability_descriptor, capability_name, external_source
from cit_protocol import IntegrationNode, PluginManifest

PLUGIN_ID = "cit.brain2devices-fleet"
PLUGIN_VERSION = "0.1.0"
RUNTIME_VERSION = "python-3.11"
BRAIN2DEVICES_REVISION = external_source("brain2devices").revision

ARM_CAPABILITY = capability_name("flight_fleet_sequence_arm")
START_CAPABILITY = capability_name("flight_fleet_sequence_start")
STOP_CAPABILITY = capability_name("flight_fleet_sequence_stop")
STATUS_CAPABILITY = capability_name("flight_fleet_sequence_status")


def build_manifest() -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": PLUGIN_ID,
            "pluginVersion": PLUGIN_VERSION,
            "runtimeVersion": RUNTIME_VERSION,
            "displayName": "Brain2Devices bounded fleet sequence",
            "adapterMode": "out_of_process",
            "configurationSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["mode"],
                "properties": {
                    "mode": {"enum": ["simulation", "brain2devices-api"]},
                    "brain2devicesOrigin": {"const": "http://127.0.0.1:8765"},
                    "brain2devicesRevision": {"const": BRAIN2DEVICES_REVISION},
                },
            },
            "publishedCapabilities": [
                capability_descriptor("flight_fleet_sequence_status", "publish")
            ],
            "consumedCapabilities": [
                capability_descriptor("flight_fleet_sequence_arm", "consume"),
                capability_descriptor("flight_fleet_sequence_start", "consume"),
                capability_descriptor("flight_fleet_sequence_stop", "consume"),
            ],
            "requiredPermissions": ["network.local.http"],
            "safetyClassification": "flight",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "included",
            "vendor": "CIT wrapper of local Brain2Devices",
            "description": (
                "Owns one explicitly armed, ordered launch sequence. It exposes no "
                "general takeoff, movement, rotation, shell, or low-level flight command."
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
) -> IntegrationNode:
    return IntegrationNode.model_validate(
        {
            "schemaVersion": "1.0",
            "nodeId": node_id,
            "pluginId": PLUGIN_ID,
            "pluginVersion": PLUGIN_VERSION,
            "runtimeVersion": RUNTIME_VERSION,
            "displayName": (
                "Simulated sequential drone launch"
                if simulated
                else "Sequential Tello launch controller"
            ),
            "hostId": host_id,
            "siteId": site_id,
            "roomId": room_id,
            "physical": not simulated,
            "simulated": simulated,
            "connectionState": "connected",
            "healthState": "healthy",
            "publishedCapabilities": [
                capability_descriptor("flight_fleet_sequence_status", "publish")
            ],
            "consumedCapabilities": [
                capability_descriptor("flight_fleet_sequence_arm", "consume"),
                capability_descriptor("flight_fleet_sequence_start", "consume"),
                capability_descriptor("flight_fleet_sequence_stop", "consume"),
            ],
            "configurationSchema": {},
            "safetyClassification": "flight",
            "dataClassifications": ["operational"],
            "simulatorAvailable": True,
            "requiredPermissions": ["network.local.http"],
            "lastSeenAt": at,
            "metadata": {
                "brain2devicesRevision": BRAIN2DEVICES_REVISION,
                "transport": "simulation" if simulated else "brain2devices-loopback-api",
                "oneShot": True,
                "requiresInstructorArm": True,
                "maximumAircraft": 8,
                "unrestrictedFlightCommands": False,
            },
        }
    )
