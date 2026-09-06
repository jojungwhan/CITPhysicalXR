"""Strict course-pack loading with YAML as the single source of truth."""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

import yaml
from cit_protocol import (
    CoursePack,
    FabricRoleTarget,
    FlowPayloadRoleTarget,
    FlowRecipe,
    FlowRoleGroupTarget,
)

_MAX_PARALLEL_GROUP_REQUESTS = 128


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
    parallel_group_requests: dict[str, int] = {}
    for flow in course_pack.flows:
        target_roles = flow_candidate_roles(flow)
        if len(target_roles) != len(set(target_roles)):
            raise ValueError(f"Flow {flow.flowId!r} target roles must be unique")
        unknown_targets = set(target_roles) - known_roles
        if unknown_targets:
            raise ValueError(
                f"Flow {flow.flowId!r} targets undeclared roles: "
                f"{', '.join(sorted(unknown_targets))}"
            )
        input_only_targets = {
            role
            for role in target_roles
            if (io_type := requirements_by_role[role].ioType) is not None
            and io_type.value == "input"
        }
        if input_only_targets:
            raise ValueError(
                f"Flow {flow.flowId!r} cannot target input-only roles: "
                f"{', '.join(sorted(input_only_targets))}"
            )
        output_roles = tuple(role.root for role in (flow.outputRoles or []))
        if len(output_roles) != len(set(output_roles)):
            raise ValueError(f"Flow {flow.flowId!r} output roles must be unique")
        if flow.enabled and flow.parallelGroup is not None:
            group = flow.parallelGroup
            parallel_group_requests[group] = parallel_group_requests.get(group, 0) + len(
                target_roles
            )
            if parallel_group_requests[group] > _MAX_PARALLEL_GROUP_REQUESTS:
                raise ValueError(
                    f"Parallel group {group!r} exceeds the "
                    f"{_MAX_PARALLEL_GROUP_REQUESTS}-request bound"
                )
        unknown_outputs = {role for role in output_roles if role not in known_roles}
        if unknown_outputs:
            raise ValueError(
                f"Flow {flow.flowId!r} has undeclared output roles: "
                f"{', '.join(sorted(unknown_outputs))}"
            )
        input_only_outputs = {
            role
            for role in output_roles
            if (io_type := requirements_by_role[role].ioType) is not None
            and io_type.value == "input"
        }
        if input_only_outputs:
            raise ValueError(
                f"Flow {flow.flowId!r} lists input-only output roles: "
                f"{', '.join(sorted(input_only_outputs))}"
            )
        if not isinstance(flow.target, FabricRoleTarget):
            declared_outputs = set(output_roles)
            if declared_outputs != set(target_roles):
                raise ValueError(
                    f"Flow {flow.flowId!r} must list every dynamic target in outputRoles"
                )
            required_capability = flow_target_required_capability(flow)
            if required_capability is not None and required_capability != flow.command.action:
                raise ValueError(
                    f"Flow {flow.flowId!r} target capability must equal its command action"
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


def flow_candidate_roles(flow: FlowRecipe) -> tuple[str, ...]:
    """Return the statically bounded role allowlist for any flow target selector."""

    target = flow.target
    if isinstance(target, FabricRoleTarget):
        return (target.role,)
    if isinstance(target, FlowRoleGroupTarget):
        return tuple(role.root for role in target.roles)
    return tuple(role.root for role in target.allowedRoles)


def resolve_flow_target_roles(
    flow: FlowRecipe,
    payload: Mapping[str, object],
) -> tuple[str, ...]:
    """Resolve a group or allowlisted payload role without accepting arbitrary input."""

    target = flow.target
    candidates = flow_candidate_roles(flow)
    if not isinstance(target, FlowPayloadRoleTarget):
        return candidates
    selected = payload.get(target.roleFromPayload)
    return (selected,) if isinstance(selected, str) and selected in candidates else ()


def flow_target_required_capability(flow: FlowRecipe) -> str | None:
    target = flow.target
    if isinstance(target, (FlowRoleGroupTarget, FlowPayloadRoleTarget)):
        return target.requiredCapability
    return None


def glasses_agent_course_pack() -> CoursePack:
    return load_builtin_course_pack("glasses-agent-control")


def gesture_ground_robot_course_pack() -> CoursePack:
    return load_builtin_course_pack("gesture-ground-robot")


def smart_plug_course_pack() -> CoursePack:
    return load_builtin_course_pack("smart-plug-control")


def device_monitoring_course_pack() -> CoursePack:
    return load_builtin_course_pack("device-monitoring")
