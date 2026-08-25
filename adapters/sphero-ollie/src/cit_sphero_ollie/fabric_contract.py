"""Canonical Fabric manifest and node contract for Sphero Ollie."""

from __future__ import annotations

from datetime import datetime

from cit_integration_sdk import capability_descriptor, capability_name, external_source
from cit_protocol import IntegrationNode, PluginManifest

from . import ADAPTER_VERSION
from .policy import (
    OLLIE_DEADMAN_MILLISECONDS,
    OLLIE_MAX_SPEED_VALUE,
    OLLIE_MAX_TRANSLATION_METERS_PER_SECOND,
    velocity_constraints,
)

PLUGIN_ID = "cit.sphero-ollie"
PROTOCOL_SOURCE_REVISION = external_source("spherov2").revision
GROUND_VELOCITY_CAPABILITY = capability_name("ground_velocity")
GROUND_NUDGE_CAPABILITY = capability_name("ground_nudge")
GROUND_DEMONSTRATION_CAPABILITY = capability_name("ground_demonstration_start")
GROUND_STOP_CAPABILITY = capability_name("ground_stop")
SENSOR_STATE_CAPABILITY = capability_name("robot_sensor_state")
LIGHT_SET_CAPABILITY = capability_name("robot_light_set")
AIM_RESET_CAPABILITY = capability_name("sphero_aim_reset")


def _consumed_capabilities() -> list[dict[str, object]]:
    return [
        capability_descriptor("ground_velocity", "consume", constraints=velocity_constraints()),
        capability_descriptor("ground_nudge", "consume"),
        capability_descriptor("ground_demonstration_start", "consume"),
        capability_descriptor("ground_stop", "consume"),
        capability_descriptor("robot_light_set", "consume"),
        capability_descriptor("sphero_aim_reset", "consume"),
    ]


def build_manifest() -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": PLUGIN_ID,
            "pluginVersion": ADAPTER_VERSION,
            "runtimeVersion": "python-3.11",
            "displayName": "Sphero Ollie",
            "adapterMode": "out_of_process",
            "configurationSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["candidateId", "mode"],
                "properties": {
                    "candidateId": {
                        "type": "string",
                        "pattern": "^sphero-ollie-[a-f0-9]{12}$",
                    },
                    "mode": {"enum": ["simulation", "bleak"]},
                },
            },
            "publishedCapabilities": [capability_descriptor("robot_sensor_state", "publish")],
            "consumedCapabilities": _consumed_capabilities(),
            "requiredPermissions": ["bluetooth"],
            "safetyClassification": "bounded_physical",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "included",
            "vendor": "Sphero",
            "description": (
                "Independent exact-selection Ollie BLE adapter with bounded directional "
                "roll, explicit aim reset, main LED control, semantic telemetry, and a "
                "local deadman stop."
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
            "consumedCapabilities": _consumed_capabilities(),
            "configurationSchema": {},
            "safetyClassification": "bounded_physical",
            "dataClassifications": ["operational"],
            "simulatorAvailable": True,
            "requiredPermissions": [] if simulated else ["bluetooth"],
            "lastSeenAt": at,
            "metadata": {
                "model": "sphero-ollie",
                "transport": "simulation" if simulated else "bluetooth-le",
                "groundMobility": True,
                "omnidirectionalHeading": True,
                "watchdogMilliseconds": OLLIE_DEADMAN_MILLISECONDS,
                "maximumSpeedValue": OLLIE_MAX_SPEED_VALUE,
                "classroomSpeedBoundMetersPerSecond": (OLLIE_MAX_TRANSLATION_METERS_PER_SECOND),
                "speedCalibration": "conservative-unverified",
                "protocolSourceRevision": PROTOCOL_SOURCE_REVISION,
                "hardwareValidation": "pending" if not simulated else "simulator",
                "rawSensorStreamPublished": False,
            },
        }
    )
