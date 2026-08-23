"""Vendor-labelled MindWave capability and node declarations."""

from __future__ import annotations

from datetime import datetime

from cit_integration_sdk import capability_descriptor, capability_name, external_source
from cit_protocol import IntegrationNode, PluginManifest

PLUGIN_ID = "cit.mindwave-mobile2"
PLUGIN_VERSION = "0.1.0"
RUNTIME_VERSION = "python-3.11"
BRAIN2DEVICES_REVISION = external_source("brain2devices").revision

ATTENTION_CAPABILITY = capability_name("mindwave_attention")
MEDITATION_CAPABILITY = capability_name("mindwave_meditation")
SIGNAL_QUALITY_CAPABILITY = capability_name("mindwave_signal_quality")
BLINK_CAPABILITY = capability_name("mindwave_blink")


def _published_capabilities() -> list[dict[str, object]]:
    return [
        capability_descriptor("mindwave_attention", "publish"),
        capability_descriptor("mindwave_meditation", "publish"),
        capability_descriptor("mindwave_signal_quality", "publish"),
        capability_descriptor("mindwave_blink", "publish"),
    ]


def build_manifest() -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": PLUGIN_ID,
            "pluginVersion": PLUGIN_VERSION,
            "runtimeVersion": RUNTIME_VERSION,
            "displayName": "MindWave Mobile 2 (Brain2Devices port)",
            "adapterMode": "out_of_process",
            "configurationSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["mode"],
                "properties": {
                    "mode": {"enum": ["simulation", "brain2devices", "brain2devices-api"]},
                    "brain2devicesRepository": {"type": "string"},
                    "brain2devicesRevision": {"const": BRAIN2DEVICES_REVISION},
                    "connectionAttempts": {"type": "integer", "minimum": 1, "maximum": 5},
                    "timeoutSeconds": {"type": "integer", "minimum": 5, "maximum": 60},
                    "brain2devicesOrigin": {"const": "http://127.0.0.1:8765"},
                },
            },
            "publishedCapabilities": _published_capabilities(),
            "consumedCapabilities": [],
            "requiredPermissions": ["bluetooth", "network.loopback"],
            "safetyClassification": "informational",
            "dataClassifications": ["biosignal_derived"],
            "simulatorAvailability": "included",
            "vendor": "CIT wrapper of local Brain2Devices",
            "description": (
                "Publishes only vendor-labelled eSense values, signal quality, and blink "
                "strength. Raw EEG never enters the Fabric."
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
            "displayName": ("Simulated MindWave Mobile 2" if simulated else "MindWave Mobile 2"),
            "hostId": host_id,
            "siteId": site_id,
            "roomId": room_id,
            "physical": not simulated,
            "simulated": simulated,
            "connectionState": "connected",
            "healthState": "healthy",
            "publishedCapabilities": _published_capabilities(),
            "consumedCapabilities": [],
            "configurationSchema": {},
            "safetyClassification": "informational",
            "dataClassifications": ["biosignal_derived"],
            "simulatorAvailable": True,
            "requiredPermissions": ["bluetooth", "network.loopback"],
            "lastSeenAt": at,
            "metadata": {
                "model": "mindwave-mobile2",
                "transport": "simulation" if simulated else "brain2devices-port",
                "brain2devicesRevision": BRAIN2DEVICES_REVISION,
                "rawEegPublished": False,
                "medicalMeasurement": False,
                "vendorDerivedSignals": True,
            },
        }
    )
