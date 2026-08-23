"""Strict course-pack loading with YAML as the single source of truth."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

import yaml
from cit_protocol import CoursePack


def load_course_pack(path: str | Path) -> CoursePack:
    source = Path(path)
    value: object = yaml.safe_load(source.read_text(encoding="utf-8"))
    return _validate_loaded_course_pack(value)


def load_builtin_course_pack(course_pack_id: str) -> CoursePack:
    """Load a generated wheel resource sourced from ``course-packs/*/course-pack.yaml``."""

    if course_pack_id not in builtin_course_pack_ids():
        raise KeyError(f"Unknown built-in course pack {course_pack_id!r}")
    resource = files("cit_runtime").joinpath("course-packs", f"{course_pack_id}.generated.json")
    value: object = json.loads(resource.read_text(encoding="utf-8"))
    return _validate_loaded_course_pack(value)


@lru_cache(maxsize=1)
def builtin_course_pack_ids() -> tuple[str, ...]:
    resource = files("cit_runtime").joinpath("course-packs", "index.generated.json")
    value: object = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schemaVersion") != "1.0":
        raise ValueError("Built-in course-pack index is invalid")
    identifiers = value.get("coursePackIds")
    if (
        not isinstance(identifiers, list)
        or not identifiers
        or any(not isinstance(identifier, str) or not identifier for identifier in identifiers)
        or len(identifiers) != len(set(identifiers))
    ):
        raise ValueError("Built-in course-pack index has invalid identifiers")
    return tuple(identifiers)


def load_builtin_course_packs() -> tuple[CoursePack, ...]:
    return tuple(load_builtin_course_pack(identifier) for identifier in builtin_course_pack_ids())


def _validate_loaded_course_pack(value: object) -> CoursePack:
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
    requirements_by_role = {requirement.role: requirement for requirement in course_pack.roles}
    for flow in course_pack.flows:
        if flow.target.role not in known_roles:
            raise ValueError(f"Flow {flow.flowId!r} targets undeclared role {flow.target.role!r}")
        target_requirement = requirements_by_role[flow.target.role]
        if target_requirement.ioType is not None and target_requirement.ioType.value == "input":
            raise ValueError(
                f"Flow {flow.flowId!r} cannot target input-only role {flow.target.role!r}"
            )
        unknown_outputs = {
            role.root for role in (flow.outputRoles or []) if role.root not in known_roles
        }
        if unknown_outputs:
            raise ValueError(
                f"Flow {flow.flowId!r} has undeclared output roles: "
                f"{', '.join(sorted(unknown_outputs))}"
            )
        input_only_outputs = {
            role.root
            for role in (flow.outputRoles or [])
            if (io_type := requirements_by_role[role.root].ioType) is not None
            and io_type.value == "input"
        }
        if input_only_outputs:
            raise ValueError(
                f"Flow {flow.flowId!r} lists input-only output roles: "
                f"{', '.join(sorted(input_only_outputs))}"
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
    return load_builtin_course_pack("glasses-agent-control")


def gesture_ground_robot_course_pack() -> CoursePack:
    return load_builtin_course_pack("gesture-ground-robot")


def smart_plug_course_pack() -> CoursePack:
    return load_builtin_course_pack("smart-plug-control")


def device_monitoring_course_pack() -> CoursePack:
    return load_builtin_course_pack("device-monitoring")
