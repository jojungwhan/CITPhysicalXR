"""Canonical smart-plug capability and node declarations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from cit_protocol import CoursePack, IntegrationNode, PluginManifest

PLUGIN_ID = "cit.tuya-smart-plug"
PLUGIN_VERSION = "0.1.0"
RUNTIME_VERSION = "python-3.11"
TINYTUYA_VERSION = "1.20.0"

POWER_SET_CAPABILITY = "power.switch.set"
POWER_STATE_CAPABILITY = "power.switch.state"


def _capability(
    name: str,
    direction: str,
    *,
    safety: str,
    rate: float,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "version": "1.0",
        "direction": direction,
        "schemaRef": None,
        "units": None,
        "maximumRateHz": rate,
        "latencyClass": "interactive",
        "safetyClassification": safety,
        "dataClassification": "operational",
        "constraints": constraints or {},
    }


def _state_capability() -> dict[str, Any]:
    return _capability(
        POWER_STATE_CAPABILITY,
        "publish",
        safety="informational",
        rate=1,
        constraints={"payload": {"on": {"type": "boolean"}}},
    )


def _set_capability() -> dict[str, Any]:
    return _capability(
        POWER_SET_CAPABILITY,
        "consume",
        safety="electrical",
        rate=1,
        constraints={"arguments": {"on": {"type": "boolean"}}},
    )


def build_manifest() -> PluginManifest:
    """Return the transport-neutral plugin manifest.

    The local key and device ID are deliberately absent. The launcher supplies
    them directly to the adapter process from a user-scoped protected secret.
    """

    return PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": PLUGIN_ID,
            "pluginVersion": PLUGIN_VERSION,
            "runtimeVersion": RUNTIME_VERSION,
            "displayName": "Tuya-compatible smart plug",
            "adapterMode": "out_of_process",
            "configurationSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "deviceAddress",
                    "connectionProfileAlias",
                    "protocolVersion",
                    "switchDps",
                ],
                "properties": {
                    "deviceAddress": {"type": "string", "format": "ipv4"},
                    "connectionProfileAlias": {"type": "string"},
                    "protocolVersion": {"enum": ["3.1", "3.2", "3.3", "3.4", "3.5"]},
                    "switchDps": {"type": "integer", "minimum": 1, "maximum": 255},
                    "vendorBrand": {"enum": ["tuya", "gosund"]},
                },
            },
            "publishedCapabilities": [_state_capability()],
            "consumedCapabilities": [_set_capability()],
            "requiredPermissions": ["local_network"],
            "safetyClassification": "electrical",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "included",
            "vendor": f"Tuya-compatible LAN through TinyTuya {TINYTUYA_VERSION}",
            "description": (
                "Exposes one exact boolean power switch and normalized state. "
                "No arbitrary Tuya datapoint or cloud command is available."
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
    vendor_brand: str,
    model: str,
    protocol_version: str,
    switch_dps: int,
    device_address: str | None,
) -> IntegrationNode:
    if vendor_brand not in {"tuya", "gosund"}:
        raise ValueError("vendor_brand must be 'tuya' or 'gosund'")
    display_brand = "Gosund" if vendor_brand == "gosund" else "Tuya"
    transport = "simulation" if simulated else "tuya-lan"
    metadata: dict[str, object] = {
        "vendorBrand": vendor_brand,
        "model": model,
        "transport": transport,
        "protocolVersion": protocol_version,
        "switchDps": switch_dps,
        "safeState": "off",
        "arbitraryDatapointsExposed": False,
    }
    if device_address is not None:
        metadata["deviceAddress"] = device_address
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
            "displayName": (
                f"Simulated {display_brand} smart plug"
                if simulated
                else f"{display_brand} {model} smart plug"
            ),
            "connectionState": "connected",
            "healthState": "healthy",
            "physical": not simulated,
            "simulated": simulated,
            "publishedCapabilities": [_state_capability()],
            "consumedCapabilities": [_set_capability()],
            "configurationSchema": {},
            "safetyClassification": "electrical",
            "dataClassifications": ["operational"],
            "simulatorAvailable": True,
            "requiredPermissions": ["local_network"] if not simulated else [],
            "lastSeenAt": at,
            "metadata": metadata,
        }
    )


def smart_plug_course_pack() -> CoursePack:
    """Manual, instructor-controlled smart-plug reference experience."""

    return CoursePack.model_validate(
        {
            "schemaVersion": "1.0",
            "coursePackId": "smart-plug-control",
            "version": "1.0.0",
            "displayName": "Tuya / Gosund smart-plug control",
            "description": (
                "Assigns an approved Tuya-LAN-compatible smart plug to the "
                "classroom_plug role for deterministic instructor on/off control."
            ),
            "roles": [
                {
                    "role": "classroom_plug",
                    "oneOfCapabilities": [POWER_SET_CAPABILITY],
                    "optional": False,
                }
            ],
            "flows": [],
            "safetyProfile": "classroom-smart-plug",
            "simulatorRequired": True,
            "assessmentEvents": [POWER_STATE_CAPABILITY],
            "fallbackBehavior": (
                "Drive the approved nonessential classroom load to off when the "
                "adapter, session, or Fabric stops."
            ),
        }
    )
