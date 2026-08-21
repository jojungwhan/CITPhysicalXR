"""Strict course-pack loading and the first glasses/agent reference recipe."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from cit_protocol import CoursePack


def load_course_pack(path: str | Path) -> CoursePack:
    source = Path(path)
    value: object = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Course pack root must be an object")
    course_pack = CoursePack.model_validate(value)
    validate_course_pack(course_pack)
    return course_pack


def validate_course_pack(course_pack: CoursePack) -> None:
    roles = [role.role for role in course_pack.roles]
    if len(roles) != len(set(roles)):
        raise ValueError("Course pack role names must be unique")
    flow_ids = [flow.flowId for flow in course_pack.flows]
    if len(flow_ids) != len(set(flow_ids)):
        raise ValueError("Course pack flow IDs must be unique")
    known_roles = set(roles)
    for flow in course_pack.flows:
        if flow.target.role not in known_roles:
            raise ValueError(f"Flow {flow.flowId!r} targets undeclared role {flow.target.role!r}")
        unknown_outputs = {
            role.root for role in (flow.outputRoles or []) if role.root not in known_roles
        }
        if unknown_outputs:
            raise ValueError(
                f"Flow {flow.flowId!r} has undeclared output roles: "
                f"{', '.join(sorted(unknown_outputs))}"
            )
        bindings = [binding.parameter for binding in flow.command.parameterBindings]
        if len(bindings) != len(set(bindings)):
            raise ValueError(
                f"Flow {flow.flowId!r} maps more than one payload field to a parameter"
            )
        fixed = flow.command.fixedParameters.model_dump(mode="json")
        overlap = set(bindings) & set(fixed)
        if overlap:
            raise ValueError(
                f"Flow {flow.flowId!r} defines fixed and dynamic values for: "
                f"{', '.join(sorted(overlap))}"
            )


def glasses_agent_course_pack() -> CoursePack:
    value: dict[str, Any] = {
        "schemaVersion": "1.0",
        "coursePackId": "glasses-agent-control",
        "version": "1.0.0",
        "displayName": "Glasses and coding agents",
        "description": (
            "Routes one semantic G2 or Meta prompt intent to an assigned existing "
            "Agent Mesh session and returns normalized display output."
        ),
        "roles": [
            {
                "role": "primary_glasses",
                "oneOfCapabilities": ["interaction.intent.agent_prompt"],
                "optional": False,
            },
            {
                "role": "coding_agent",
                "oneOfCapabilities": ["agent.prompt.submit"],
                "optional": False,
            },
            {
                "role": "feedback_display",
                "oneOfCapabilities": ["display.text.render"],
                "optional": True,
            },
            {
                "role": "instructor_console",
                "oneOfCapabilities": ["display.text.render"],
                "optional": True,
            },
        ],
        "flows": [
            {
                "flowId": "glasses-agent-prompt",
                "version": 1,
                "trigger": {
                    "event": "interaction.intent.agent_prompt",
                    "minimumConfidence": 0.5,
                    "debounceMs": 250,
                },
                "command": {
                    "action": "agent.prompt.submit",
                    "fixedParameters": {},
                    "parameterBindings": [{"payloadField": "text", "parameter": "prompt"}],
                },
                "target": {"role": "coding_agent"},
                "guards": [
                    "session_is_active",
                    "role_is_assigned",
                    "target_is_connected",
                    "instructor_override_is_clear",
                ],
                "safetyProfile": "agent-session",
                "outputRoles": ["primary_glasses", "instructor_console"],
                "enabled": True,
            },
            {
                "flowId": "agent-output-to-glasses",
                "version": 1,
                "trigger": {"event": "agent.output.completed"},
                "command": {
                    "action": "display.text.render",
                    "fixedParameters": {},
                    "parameterBindings": [{"payloadField": "displayText", "parameter": "text"}],
                },
                "target": {"role": "primary_glasses"},
                "guards": [
                    "session_is_active",
                    "role_is_assigned",
                    "target_is_connected",
                    "instructor_override_is_clear",
                ],
                "safetyProfile": "agent-session",
                "outputRoles": ["primary_glasses", "instructor_console"],
                "enabled": True,
            },
        ],
        "safetyProfile": "agent-session",
        "simulatorRequired": True,
        "assessmentEvents": ["agent.output.completed"],
        "fallbackBehavior": "Keep the prompt pending and show a retryable bridge error.",
    }
    course_pack = CoursePack.model_validate(value)
    validate_course_pack(course_pack)
    return course_pack


def gesture_ground_robot_course_pack() -> CoursePack:
    """The canonical Leap-to-interchangeable-ground-robot recipe."""

    value: dict[str, Any] = {
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
                "oneOfCapabilities": ["interaction.gesture.velocity"],
                "optional": False,
            },
            {
                "role": "student_robot",
                "oneOfCapabilities": ["mobility.ground.set_velocity"],
                "optional": False,
            },
        ],
        "flows": [
            {
                "flowId": "gesture-to-ground-velocity",
                "version": 1,
                "trigger": {
                    "event": "interaction.gesture.velocity",
                    "minimumConfidence": 0.8,
                    "debounceMs": 50,
                },
                "command": {
                    "action": "mobility.ground.set_velocity",
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
        "assessmentEvents": [
            "interaction.gesture.velocity",
            "telemetry.motion.commanded",
        ],
        "fallbackBehavior": (
            "Stop locally within 200 ms of stale input, disconnect, process failure, "
            "or instructor emergency stop."
        ),
    }
    course_pack = CoursePack.model_validate(value)
    validate_course_pack(course_pack)
    return course_pack
