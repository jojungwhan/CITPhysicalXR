"""Canonical Fabric declarations for the two independently routable nodes."""

from __future__ import annotations

import json
from datetime import datetime
from importlib.resources import files

from cit_integration_sdk import capability_descriptor, capability_name, external_source
from cit_protocol import CoursePack, IntegrationNode, PluginManifest

PLUGIN_ID = "cit.robomaster-gesture-control"
LEAP_PLUGIN_ID = "cit.leap-motion"
ROBOMASTER_PLUGIN_ID = "cit.robomaster-s1"
PLUGIN_VERSION = "0.1.0"
RUNTIME_VERSION = "python-3.11"
UPSTREAM_REVISION = external_source("robomaster-gesture-control").revision

GESTURE_CAPABILITY = capability_name("gesture_velocity")
FLIGHT_SEQUENCE_INTENT_CAPABILITY = capability_name("flight_sequence_intent")
TRACKING_CAPABILITY = capability_name("tracking_status")
ROBOT_VELOCITY_CAPABILITY = capability_name("ground_velocity")
ROBOT_STOP_CAPABILITY = capability_name("ground_stop")
ROBOT_TELEMETRY_CAPABILITY = capability_name("ground_commanded")


def _gesture_capability() -> dict[str, object]:
    return capability_descriptor("gesture_velocity", "publish")


def _tracking_capability() -> dict[str, object]:
    return capability_descriptor("tracking_status", "publish")


def _flight_sequence_intent_capability() -> dict[str, object]:
    return capability_descriptor("flight_sequence_intent", "publish")


def _velocity_capability() -> dict[str, object]:
    return capability_descriptor("ground_velocity", "consume")


def _stop_capability() -> dict[str, object]:
    return capability_descriptor("ground_stop", "consume")


def _robot_telemetry_capability() -> dict[str, object]:
    return capability_descriptor("ground_commanded", "publish")


def build_manifest() -> PluginManifest:
    published = [
        _gesture_capability(),
        _flight_sequence_intent_capability(),
        _tracking_capability(),
        _robot_telemetry_capability(),
    ]
    consumed = [_velocity_capability(), _stop_capability()]
    return PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": PLUGIN_ID,
            "pluginVersion": PLUGIN_VERSION,
            "runtimeVersion": RUNTIME_VERSION,
            "displayName": "RoboMaster S1 and Leap Motion wrapper",
            "adapterMode": "out_of_process",
            "configurationSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["upstreamRepository", "upstreamRevision", "robotMode"],
                "properties": {
                    "upstreamRepository": {"type": "string"},
                    "upstreamRevision": {"const": UPSTREAM_REVISION},
                    "robotMode": {"enum": ["dry-run", "sdk", "s1-app"]},
                    "preferredHand": {"enum": ["left", "right", "any"]},
                },
            },
            "publishedCapabilities": published,
            "consumedCapabilities": consumed,
            "requiredPermissions": [],
            "safetyClassification": "bounded_physical",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "included",
            "vendor": "CIT wrapper of jojungwhan/robomaster-gesture-control",
            "description": (
                "Wraps the owner-designated upstream checkout without importing DJI or "
                "LeapC into the orchestration runtime."
            ),
        }
    )


def build_leap_manifest() -> PluginManifest:
    """Manifest for the independently supervised Leap input process."""

    return PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": LEAP_PLUGIN_ID,
            "pluginVersion": PLUGIN_VERSION,
            "runtimeVersion": RUNTIME_VERSION,
            "displayName": "Leap Motion semantic gesture input",
            "adapterMode": "out_of_process",
            "configurationSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["upstreamRepository", "upstreamRevision", "inputMode"],
                "properties": {
                    "upstreamRepository": {"type": "string"},
                    "upstreamRevision": {"const": UPSTREAM_REVISION},
                    "inputMode": {"enum": ["demo", "leap"]},
                    "preferredHand": {"enum": ["left", "right", "any"]},
                },
            },
            "publishedCapabilities": [
                _gesture_capability(),
                _flight_sequence_intent_capability(),
                _tracking_capability(),
            ],
            "consumedCapabilities": [],
            "requiredPermissions": ["usb.hid"],
            "safetyClassification": "informational",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "included",
            "vendor": "CIT wrapper of jojungwhan/robomaster-gesture-control",
            "description": "Publishes semantic gestures and imports no robot module.",
        }
    )


def build_robot_manifest() -> PluginManifest:
    """Manifest for the independently supervised RoboMaster output process."""

    return PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": ROBOMASTER_PLUGIN_ID,
            "pluginVersion": PLUGIN_VERSION,
            "runtimeVersion": RUNTIME_VERSION,
            "displayName": "DJI RoboMaster S1 ground-mobility output",
            "adapterMode": "out_of_process",
            "configurationSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["upstreamRepository", "upstreamRevision", "robotMode"],
                "properties": {
                    "upstreamRepository": {"type": "string"},
                    "upstreamRevision": {"const": UPSTREAM_REVISION},
                    "robotMode": {"enum": ["dry-run", "sdk", "s1-app"]},
                },
            },
            "publishedCapabilities": [_robot_telemetry_capability()],
            "consumedCapabilities": [_velocity_capability(), _stop_capability()],
            "requiredPermissions": ["network.local"],
            "safetyClassification": "bounded_physical",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "included",
            "vendor": "CIT wrapper of jojungwhan/robomaster-gesture-control",
            "description": "Consumes bounded ground commands and imports no Leap module.",
        }
    )


def build_nodes(
    *,
    at: datetime,
    host_id: str,
    site_id: str,
    room_id: str,
    leap_node_id: str,
    robot_node_id: str,
    leap_simulated: bool,
    robot_simulated: bool,
    robot_mode: str,
    preferred_hand: str,
) -> tuple[IntegrationNode, IntegrationNode]:
    gesture = _gesture_capability()
    flight_sequence_intent = _flight_sequence_intent_capability()
    tracking = _tracking_capability()
    velocity = _velocity_capability()
    stop = _stop_capability()
    robot_telemetry = _robot_telemetry_capability()
    common = {
        "schemaVersion": "1.0",
        "pluginId": PLUGIN_ID,
        "pluginVersion": PLUGIN_VERSION,
        "runtimeVersion": RUNTIME_VERSION,
        "hostId": host_id,
        "siteId": site_id,
        "roomId": room_id,
        "connectionState": "connected",
        "healthState": "healthy",
        "configurationSchema": {},
        "dataClassifications": ["operational"],
        "simulatorAvailable": True,
        "requiredPermissions": [],
        "lastSeenAt": at,
    }
    leap = IntegrationNode.model_validate(
        {
            **common,
            "nodeId": leap_node_id,
            "displayName": "Leap Motion gesture input",
            "physical": not leap_simulated,
            "simulated": leap_simulated,
            "publishedCapabilities": [gesture, flight_sequence_intent, tracking],
            "consumedCapabilities": [],
            "safetyClassification": "informational",
            "metadata": {
                "model": "ultraleap-leap-motion",
                "preferredHand": preferred_hand,
                "upstreamRevision": UPSTREAM_REVISION,
                "semanticEventsOnly": True,
            },
        }
    )
    robot = IntegrationNode.model_validate(
        {
            **common,
            "nodeId": robot_node_id,
            "displayName": (
                "Simulated RoboMaster S1" if robot_simulated else "Physical RoboMaster S1"
            ),
            "physical": not robot_simulated,
            "simulated": robot_simulated,
            "publishedCapabilities": [robot_telemetry],
            "consumedCapabilities": [velocity, stop],
            "safetyClassification": "bounded_physical",
            "metadata": {
                "model": "robomaster-s1",
                "transport": robot_mode,
                "upstreamRevision": UPSTREAM_REVISION,
                "maxTranslationMetersPerSecond": 0.35,
                "maxYawDegreesPerSecond": 35.0,
                "staleWatchdogMilliseconds": 200,
            },
        }
    )
    return leap, robot


def build_leap_node(
    *,
    at: datetime,
    host_id: str,
    site_id: str,
    room_id: str,
    node_id: str,
    simulated: bool,
    preferred_hand: str,
) -> IntegrationNode:
    """Build only the Leap node under its independent plugin identity."""

    leap, _ = build_nodes(
        at=at,
        host_id=host_id,
        site_id=site_id,
        room_id=room_id,
        leap_node_id=node_id,
        robot_node_id="unused-robomaster-node",
        leap_simulated=simulated,
        robot_simulated=True,
        robot_mode="dry-run",
        preferred_hand=preferred_hand,
    )
    return leap.model_copy(update={"pluginId": LEAP_PLUGIN_ID})


def build_robot_node(
    *,
    at: datetime,
    host_id: str,
    site_id: str,
    room_id: str,
    node_id: str,
    simulated: bool,
    robot_mode: str,
) -> IntegrationNode:
    """Build only the RoboMaster node under its independent plugin identity."""

    _, robot = build_nodes(
        at=at,
        host_id=host_id,
        site_id=site_id,
        room_id=room_id,
        leap_node_id="unused-leap-node",
        robot_node_id=node_id,
        leap_simulated=True,
        robot_simulated=simulated,
        robot_mode=robot_mode,
        preferred_hand="any",
    )
    return robot.model_copy(update={"pluginId": ROBOMASTER_PLUGIN_ID})


def gesture_ground_robot_course_pack() -> CoursePack:
    """Compatibility API loading the generated canonical YAML course pack."""

    resource = files("cit_robomaster_leap").joinpath("course-pack.generated.json")
    return CoursePack.model_validate(json.loads(resource.read_text(encoding="utf-8")))
