"""Canonical Fabric manifest and node contract for Sphero BOLT."""

from __future__ import annotations

from datetime import datetime

from cit_integration_sdk import capability_descriptor, capability_name, external_source
from cit_protocol import IntegrationNode, PluginManifest

from . import ADAPTER_VERSION
from .policy import SPHERO_DEADMAN_MILLISECONDS, SPHERO_MAX_SPEED_VALUE, velocity_constraints

PLUGIN_ID = "cit.sphero-bolt"
PROTOCOL_SOURCE_REVISION = external_source("spherov2").revision
GROUND_VELOCITY_CAPABILITY = capability_name("ground_velocity")
GROUND_NUDGE_CAPABILITY = capability_name("ground_nudge")
GROUND_DEMONSTRATION_CAPABILITY = capability_name("ground_demonstration_start")
GROUND_STOP_CAPABILITY = capability_name("ground_stop")
SENSOR_STATE_CAPABILITY = capability_name("robot_sensor_state")
LIGHT_SET_CAPABILITY = capability_name("robot_light_set")
AIM_RESET_CAPABILITY = capability_name("sphero_aim_reset")


def build_manifest() -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": PLUGIN_ID,
            "pluginVersion": ADAPTER_VERSION,
            "runtimeVersion": "python-3.11",
            "displayName": "Sphero BOLT",
            "adapterMode": "out_of_process",
            "configurationSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["candidateId", "mode"],
                "properties": {
                    "candidateId": {"type": "string", "pattern": "^sphero-[a-f0-9]{12}$"},
                    "mode": {"enum": ["simulation", "bleak"]},
                },
            },
            "publishedCapabilities": [capability_descriptor("robot_sensor_state", "publish")],
            "consumedCapabilities": [
                capability_descriptor(
                    "ground_velocity", "consume", constraints=velocity_constraints()
                ),
                capability_descriptor("ground_nudge", "consume"),
                capability_descriptor("ground_demonstration_start", "consume"),
                capability_descriptor("ground_stop", "consume"),
                capability_descriptor("robot_light_set", "consume"),
                capability_descriptor("sphero_aim_reset", "consume"),
            ],
            "requiredPermissions": ["bluetooth"],
            "safetyClassification": "bounded_physical",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "included",
            "vendor": "Sphero",
            "description": (
                "Independent exact-selection BLE adapter with bounded directional roll, "
                "explicit aim reset, lights, semantic sensor telemetry, and local deadman stop."
            ),
        }
    )


def build_node(
    *,
    node_id: str,
    display_name: str,
    at: datetime,
    host_id: str,
    site_id: str,
    room_id: str,
    simulated: bool,
) -> IntegrationNode:
    return IntegrationNode.model_validate(
        {
            "schemaVersion": "1.0",
            "nodeId": node_id,
            "pluginId": PLUGIN_ID,
            "pluginVersion": ADAPTER_VERSION,
            "runtimeVersion": "python-3.11",
            "displayName": display_name,
            "hostId": host_id,
            "siteId": site_id,
            "roomId": room_id,
            "physical": not simulated,
            "simulated": simulated,
            "connectionState": "connected",
            "healthState": "healthy",
            "publishedCapabilities": [capability_descriptor("robot_sensor_state", "publish")],
            "consumedCapabilities": [
                capability_descriptor(
                    "ground_velocity", "consume", constraints=velocity_constraints()
                ),
                capability_descriptor("ground_nudge", "consume"),
                capability_descriptor("ground_demonstration_start", "consume"),
                capability_descriptor("ground_stop", "consume"),
                capability_descriptor("robot_light_set", "consume"),
                capability_descriptor("sphero_aim_reset", "consume"),
            ],
            "configurationSchema": {},
            "safetyClassification": "bounded_physical",
            "dataClassifications": ["operational"],
            "simulatorAvailable": True,
            "requiredPermissions": [] if simulated else ["bluetooth"],
            "lastSeenAt": at,
            "metadata": {
                "model": "sphero-bolt",
                "transport": "simulation" if simulated else "bluetooth-le",
                "groundMobility": True,
                "omnidirectionalHeading": True,
                "watchdogMilliseconds": SPHERO_DEADMAN_MILLISECONDS,
                "maximumSpeedValue": SPHERO_MAX_SPEED_VALUE,
                "protocolSourceRevision": PROTOCOL_SOURCE_REVISION,
                "hardwareValidation": "pending" if not simulated else "simulator",
                "rawSensorStreamPublished": False,
            },
        }
    )
