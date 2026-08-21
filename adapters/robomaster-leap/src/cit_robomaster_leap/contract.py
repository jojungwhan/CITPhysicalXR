"""Canonical Fabric declarations for the two independently routable nodes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from cit_protocol import CoursePack, IntegrationNode, PluginManifest

PLUGIN_ID = "cit.robomaster-gesture-control"
PLUGIN_VERSION = "0.1.0"
RUNTIME_VERSION = "python-3.11"
UPSTREAM_REVISION = "3c213c110b0cdf2912985bfcde442d67092b98f0"

GESTURE_CAPABILITY = "interaction.gesture.velocity"
TRACKING_CAPABILITY = "telemetry.tracking.status"
ROBOT_VELOCITY_CAPABILITY = "mobility.ground.set_velocity"
ROBOT_STOP_CAPABILITY = "mobility.ground.stop"
ROBOT_TELEMETRY_CAPABILITY = "telemetry.motion.commanded"


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


def _gesture_capability() -> dict[str, Any]:
    return _capability(
        GESTURE_CAPABILITY,
        "publish",
        safety="informational",
        rate=15,
        constraints={
            "payload": {
                "forwardMetersPerSecond": {"minimum": -0.35, "maximum": 0.35},
                "rightMetersPerSecond": {"minimum": -0.35, "maximum": 0.35},
                "clockwiseRadiansPerSecond": {
                    "minimum": -0.6108652382,
                    "maximum": 0.6108652382,
                },
            }
        },
    )


def _tracking_capability() -> dict[str, Any]:
    return _capability(
        TRACKING_CAPABILITY,
        "publish",
        safety="informational",
        rate=2,
    )


def _velocity_capability() -> dict[str, Any]:
    return _capability(
        ROBOT_VELOCITY_CAPABILITY,
        "consume",
        safety="bounded_physical",
        rate=15,
        constraints={
            "arguments": {
                "forwardMetersPerSecond": {"minimum": -0.35, "maximum": 0.35},
                "rightMetersPerSecond": {"minimum": -0.35, "maximum": 0.35},
                "clockwiseRadiansPerSecond": {
                    "minimum": -0.6108652382,
                    "maximum": 0.6108652382,
                },
            }
        },
    )


def _stop_capability() -> dict[str, Any]:
    return _capability(
        ROBOT_STOP_CAPABILITY,
        "consume",
        safety="bounded_physical",
        rate=20,
    )


def _robot_telemetry_capability() -> dict[str, Any]:
    return _capability(
        ROBOT_TELEMETRY_CAPABILITY,
        "publish",
        safety="informational",
        rate=15,
    )


def build_manifest() -> PluginManifest:
    published = [
        _gesture_capability(),
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
            "publishedCapabilities": [gesture, tracking],
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


def gesture_ground_robot_course_pack() -> CoursePack:
    return CoursePack.model_validate(
        {
            "schemaVersion": "1.0",
            "coursePackId": "gesture-ground-robot",
            "version": "1.0.0",
            "displayName": "Leap gesture ground-robot control",
            "description": (
                "Routes normalized Leap virtual-joystick gestures to an assigned "
                "ground-mobility node through deterministic Fabric safety."
            ),
            "roles": [
                {
                    "role": "gesture_input",
                    "oneOfCapabilities": [GESTURE_CAPABILITY],
                    "optional": False,
                },
                {
                    "role": "student_robot",
                    "oneOfCapabilities": [ROBOT_VELOCITY_CAPABILITY],
                    "optional": False,
                },
            ],
            "flows": [
                {
                    "flowId": "gesture-to-ground-velocity",
                    "version": 1,
                    "trigger": {
                        "event": GESTURE_CAPABILITY,
                        "minimumConfidence": 0.8,
                        "debounceMs": 50,
                    },
                    "command": {
                        "action": ROBOT_VELOCITY_CAPABILITY,
                        "fixedParameters": {},
                        "parameterBindings": [
                            {
                                "payloadField": "forwardMetersPerSecond",
                                "parameter": "forwardMetersPerSecond",
                            },
                            {
                                "payloadField": "rightMetersPerSecond",
                                "parameter": "rightMetersPerSecond",
                            },
                            {
                                "payloadField": "clockwiseRadiansPerSecond",
                                "parameter": "clockwiseRadiansPerSecond",
                            },
                        ],
                    },
                    "target": {"role": "student_robot"},
                    "guards": [
                        "session_is_active",
                        "role_is_assigned",
                        "target_is_connected",
                        "target_is_armed",
                        "instructor_override_is_clear",
                    ],
                    "safetyProfile": "classroom-ground-robot",
                    "outputRoles": [],
                    "enabled": True,
                }
            ],
            "safetyProfile": "classroom-ground-robot",
            "simulatorRequired": True,
            "assessmentEvents": [GESTURE_CAPABILITY, ROBOT_TELEMETRY_CAPABILITY],
            "fallbackBehavior": (
                "Stop locally within 200 ms of stale input, disconnect, process failure, "
                "or instructor emergency stop."
            ),
        }
    )
