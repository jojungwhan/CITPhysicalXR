"""Canonical contract for the optional combined Brain2Devices demo boundary."""

from __future__ import annotations

from datetime import datetime

from cit_integration_sdk import capability_descriptor, capability_name, external_source
from cit_protocol import IntegrationNode, PluginManifest

PLUGIN_ID = "cit.brain2devices-demo"
PLUGIN_VERSION = "0.1.0"
RUNTIME_VERSION = "python-3.11"
BRAIN2DEVICES_REVISION = external_source("brain2devices").revision

ARM_CAPABILITY = capability_name("flight_brain_demo_arm")
STOP_CAPABILITY = capability_name("flight_brain_demo_stop")
STATUS_CAPABILITY = capability_name("flight_brain_demo_status")


def build_manifest() -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": PLUGIN_ID,
            "pluginVersion": PLUGIN_VERSION,
            "runtimeVersion": RUNTIME_VERSION,
            "displayName": "Brain2Devices bounded MindWave flight demo",
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
            "publishedCapabilities": [capability_descriptor("flight_brain_demo_status", "publish")],
            "consumedCapabilities": [
                capability_descriptor("flight_brain_demo_arm", "consume"),
                capability_descriptor("flight_brain_demo_stop", "consume"),
            ],
            "requiredPermissions": ["network.local.http"],
            "safetyClassification": "flight",
            "dataClassifications": ["biosignal_derived", "operational"],
            "simulatorAvailability": "included",
            "vendor": "CIT wrapper of local Brain2Devices",
            "description": (
                "Separately wraps Brain2Devices' one-shot, quality-gated MindWave trigger. "
                "It does not replace the independent MindWave or Tello adapters and exposes "
                "no general takeoff, movement, shell, or low-level flight capability."
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
                "Simulated MindWave flight demo" if simulated else "MindWave one-shot Tello demo"
            ),
            "hostId": host_id,
            "siteId": site_id,
            "roomId": room_id,
            "physical": not simulated,
            "simulated": simulated,
            "connectionState": "connected",
            "healthState": "healthy",
            "publishedCapabilities": [capability_descriptor("flight_brain_demo_status", "publish")],
            "consumedCapabilities": [
                capability_descriptor("flight_brain_demo_arm", "consume"),
                capability_descriptor("flight_brain_demo_stop", "consume"),
            ],
            "configurationSchema": {},
            "safetyClassification": "flight",
            "dataClassifications": ["biosignal_derived", "operational"],
            "simulatorAvailable": True,
            "requiredPermissions": ["network.local.http"],
            "lastSeenAt": at,
            "metadata": {
                "brain2devicesRevision": BRAIN2DEVICES_REVISION,
                "transport": "simulation" if simulated else "brain2devices-loopback-api",
                "oneShot": True,
                "requiresInstructor": True,
                "rawEegPublished": False,
                "unrestrictedFlightCommands": False,
            },
        }
    )
