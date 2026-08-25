"""Canonical Fabric manifest and per-model node contract."""

from __future__ import annotations

from datetime import datetime

from cit_integration_sdk import capability_descriptor, capability_name, external_source
from cit_protocol import IntegrationNode, PluginManifest

from . import ADAPTER_VERSION
from .models import WonderRobotModel
from .policy import DASH_DEADMAN_MILLISECONDS, dash_velocity_constraints

PLUGIN_ID = "cit.wonder-workshop"
PROTOCOL_SOURCE_REVISION = external_source("bleak-dash").revision
GROUND_VELOCITY_CAPABILITY = capability_name("ground_velocity")
GROUND_NUDGE_CAPABILITY = capability_name("ground_nudge")
GROUND_DEMONSTRATION_CAPABILITY = capability_name("ground_demonstration_start")
GROUND_STOP_CAPABILITY = capability_name("ground_stop")
SENSOR_STATE_CAPABILITY = capability_name("robot_sensor_state")
LIGHT_SET_CAPABILITY = capability_name("robot_light_set")
SOUND_CUE_CAPABILITY = capability_name("robot_sound_cue")
HEAD_POSE_CAPABILITY = capability_name("robot_head_pose")


def build_manifest() -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": PLUGIN_ID,
            "pluginVersion": ADAPTER_VERSION,
            "runtimeVersion": "python-3.11",
            "displayName": "Wonder Workshop Dash and Dot",
            "adapterMode": "out_of_process",
            "configurationSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["candidateId", "model", "mode"],
                "properties": {
                    "candidateId": {"type": "string"},
                    "model": {"enum": ["dash", "dot"]},
                    "mode": {"enum": ["simulation", "bleak"]},
                },
            },
            "publishedCapabilities": [capability_descriptor("robot_sensor_state", "publish")],
            "consumedCapabilities": [
                capability_descriptor("ground_velocity", "consume"),
                capability_descriptor("ground_nudge", "consume"),
                capability_descriptor("ground_demonstration_start", "consume"),
                capability_descriptor("ground_stop", "consume"),
                capability_descriptor("robot_light_set", "consume"),
                capability_descriptor("robot_sound_cue", "consume"),
                capability_descriptor("robot_head_pose", "consume"),
            ],
            "requiredPermissions": ["bluetooth"],
            "safetyClassification": "bounded_physical",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "included",
            "vendor": "Wonder Workshop",
            "description": (
                "Independent BLE adapter. Dot exposes sensors, fixed sound cues, and lights; "
                "Dash additionally exposes bounded drive and head controls."
            ),
        }
    )


def build_node(
    *,
    node_id: str,
    display_name: str,
    model: WonderRobotModel,
    at: datetime,
    host_id: str,
    site_id: str,
    room_id: str,
    simulated: bool,
) -> IntegrationNode:
    consumed = [
        capability_descriptor("robot_light_set", "consume"),
        capability_descriptor("robot_sound_cue", "consume"),
    ]
    if model is WonderRobotModel.DASH:
        consumed.extend(
            [
                capability_descriptor(
                    "ground_velocity", "consume", constraints=dash_velocity_constraints()
                ),
                capability_descriptor("ground_nudge", "consume"),
                capability_descriptor("ground_demonstration_start", "consume"),
                capability_descriptor("ground_stop", "consume"),
                capability_descriptor("robot_head_pose", "consume"),
            ]
        )
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
            "consumedCapabilities": consumed,
            "configurationSchema": {},
            "safetyClassification": "bounded_physical",
            "dataClassifications": ["operational"],
            "simulatorAvailable": True,
            "requiredPermissions": [] if simulated else ["bluetooth"],
            "lastSeenAt": at,
            "metadata": {
                "model": model.value,
                "transport": "simulation" if simulated else "bluetooth-le",
                "groundMobility": model is WonderRobotModel.DASH,
                "movableHead": model is WonderRobotModel.DASH,
                "watchdogMilliseconds": DASH_DEADMAN_MILLISECONDS,
                "protocolSourceRevision": PROTOCOL_SOURCE_REVISION,
                "rawMicrophonePublished": False,
            },
        }
    )
