from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cit_protocol import (
    CoursePack,
    CreateInteractionSessionRequest,
    IntegrationNode,
    PluginManifest,
)
from cit_runtime.fabric import FabricConflictError, FabricPolicyError, InteractionFabric
from cit_runtime.fabric_repository import SQLiteFabricRepository

NOW = datetime(2026, 8, 21, 3, 0, 0, tzinfo=UTC)


def physical_ground_plugin() -> tuple[PluginManifest, IntegrationNode]:
    telemetry = {
        "name": "telemetry.pose",
        "version": "1.0",
        "direction": "publish",
        "maximumRateHz": 20,
        "latencyClass": "interactive",
        "safetyClassification": "informational",
        "dataClassification": "operational",
        "constraints": {},
    }
    drive = {
        "name": "mobility.ground.set_velocity",
        "version": "1.0",
        "direction": "consume",
        "maximumRateHz": 20,
        "latencyClass": "interactive",
        "safetyClassification": "bounded_physical",
        "dataClassification": "operational",
        "constraints": {
            "arguments": {
                "linearMetersPerSecond": {"minimum": -0.4, "maximum": 0.4},
                "angularRadiansPerSecond": {"minimum": -0.8, "maximum": 0.8},
            }
        },
    }
    manifest = PluginManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "pluginId": "cit.test-ground-robot",
            "pluginVersion": "1.0.0",
            "runtimeVersion": "1.0.0",
            "displayName": "Physical test ground robot",
            "adapterMode": "out_of_process",
            "configurationSchema": {},
            "publishedCapabilities": [telemetry],
            "consumedCapabilities": [drive],
            "requiredPermissions": [],
            "safetyClassification": "bounded_physical",
            "dataClassifications": ["operational"],
            "simulatorAvailability": "included",
        }
    )
    node = IntegrationNode.model_validate(
        {
            "schemaVersion": "1.0",
            "nodeId": "physical-ground-a",
            "pluginId": manifest.pluginId,
            "pluginVersion": manifest.pluginVersion,
            "runtimeVersion": manifest.runtimeVersion,
            "hostId": "edge-host-a",
            "siteId": "local-site",
            "roomId": "local-room",
            "displayName": "Physical ground robot A",
            "connectionState": "connected",
            "healthState": "healthy",
            "physical": True,
            "simulated": False,
            "publishedCapabilities": [telemetry],
            "consumedCapabilities": [drive],
            "configurationSchema": {},
            "safetyClassification": "bounded_physical",
            "dataClassifications": ["operational"],
            "simulatorAvailable": True,
            "requiredPermissions": [],
            "lastSeenAt": NOW,
            "metadata": {},
        }
    )
    return manifest, node


def physical_course() -> CoursePack:
    return CoursePack.model_validate(
        {
            "schemaVersion": "1.0",
            "coursePackId": "physical-ground-test",
            "version": "1.0.0",
            "displayName": "Physical ground safety test",
            "roles": [
                {
                    "role": "student_robot",
                    "oneOfCapabilities": ["mobility.ground.set_velocity"],
                    "optional": False,
                }
            ],
            "flows": [],
            "safetyProfile": "classroom-ground-robot",
            "simulatorRequired": False,
            "assessmentEvents": ["telemetry.pose"],
            "fallbackBehavior": "Remain stopped.",
        }
    )


def physical_monitoring_course() -> CoursePack:
    return CoursePack.model_validate(
        {
            "schemaVersion": "1.0",
            "coursePackId": "physical-monitoring-test",
            "version": "1.0.0",
            "displayName": "Physical monitoring safety test",
            "roles": [
                {
                    "role": "telemetry_source",
                    "oneOfCapabilities": ["telemetry.pose"],
                    "optional": False,
                },
                {
                    "role": "telemetry_source_2",
                    "oneOfCapabilities": ["telemetry.pose"],
                    "optional": True,
                },
            ],
            "flows": [],
            "safetyProfile": "classroom-monitoring",
            "simulatorRequired": False,
            "assessmentEvents": ["telemetry.pose"],
            "fallbackBehavior": "Stop observing.",
        }
    )


def prepare_physical_session(
    fabric: InteractionFabric,
    *,
    manifest: PluginManifest,
    node: IntegrationNode,
) -> str:
    fabric.register_plugin_and_nodes(manifest, (node,))
    fabric.install_course_pack(physical_course(), actor_id="instructor-a")
    session = fabric.create_session(
        CreateInteractionSessionRequest.model_validate(
            {
                "coursePackId": "physical-ground-test",
                "coursePackVersion": "1.0.0",
                "siteId": "local-site",
                "roomId": "local-room",
                "mode": "physical",
            }
        ),
        actor_id="instructor-a",
    )
    session = fabric.assign_role(
        session.sessionId,
        "student_robot",
        node.nodeId,
        actor_id="instructor-a",
    )
    assert session.state.value == "ready"
    return session.sessionId


def test_physical_session_requires_explicit_arm_and_disconnect_forces_safe_state() -> None:
    manifest, node = physical_ground_plugin()
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW, allow_physical=True)
        session_id = prepare_physical_session(fabric, manifest=manifest, node=node)

        with pytest.raises(FabricPolicyError, match="explicitly armed"):
            fabric.transition_session(session_id, "start", actor_id="instructor-a")

        armed = fabric.transition_session(session_id, "arm", actor_id="instructor-a")
        assert armed.armed is True
        assert armed.armedBy == "instructor-a"
        active = fabric.transition_session(session_id, "start", actor_id="instructor-a")
        assert active.state.value == "active"

        assert fabric.disconnect_nodes((node.nodeId,)) == (node.nodeId,)
        stopped = fabric.get_session(session_id)

    assert stopped.armed is False
    assert stopped.state.value == "emergency_stopped"
    assert stopped.disarmReason == "adapter_disconnected"


def test_physical_monitoring_may_run_unarmed_without_authorizing_actuation() -> None:
    manifest, node = physical_ground_plugin()
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW, allow_physical=True)
        fabric.register_plugin_and_nodes(manifest, (node,))
        fabric.install_course_pack(physical_monitoring_course(), actor_id="instructor-a")
        session = fabric.create_session(
            CreateInteractionSessionRequest.model_validate(
                {
                    "coursePackId": "physical-monitoring-test",
                    "coursePackVersion": "1.0.0",
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "mode": "physical",
                }
            ),
            actor_id="instructor-a",
        )
        ready = fabric.assign_role(
            session.sessionId,
            "telemetry_source",
            node.nodeId,
            actor_id="instructor-a",
        )
        assert fabric.can_start_unarmed(ready.sessionId) is True

        active = fabric.transition_session(
            ready.sessionId,
            "start",
            actor_id="instructor-a",
        )

    assert active.state.value == "active"
    assert active.armed is False


def test_active_unarmed_monitoring_accepts_only_optional_informational_roles() -> None:
    manifest, node = physical_ground_plugin()
    second_node = node.model_copy(update={"nodeId": "physical-ground-b"})
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW, allow_physical=True)
        fabric.register_plugin_and_nodes(manifest, (node, second_node))
        fabric.install_course_pack(physical_monitoring_course(), actor_id="instructor-a")
        session = fabric.create_session(
            CreateInteractionSessionRequest.model_validate(
                {
                    "coursePackId": "physical-monitoring-test",
                    "coursePackVersion": "1.0.0",
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "mode": "physical",
                }
            ),
            actor_id="instructor-a",
        )
        ready = fabric.assign_role(
            session.sessionId,
            "telemetry_source",
            node.nodeId,
            actor_id="instructor-a",
        )
        fabric.transition_session(ready.sessionId, "start", actor_id="instructor-a")

        extended = fabric.assign_role(
            ready.sessionId,
            "telemetry_source_2",
            second_node.nodeId,
            actor_id="instructor-a",
        )

    assert extended.state.value == "active"
    assert extended.armed is False
    assert {binding.nodeId for binding in extended.roleBindings} == {
        node.nodeId,
        second_node.nodeId,
    }


def test_active_control_session_still_rejects_role_changes() -> None:
    manifest, node = physical_ground_plugin()
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW, allow_physical=True)
        session_id = prepare_physical_session(fabric, manifest=manifest, node=node)
        assert fabric.can_start_unarmed(session_id) is False
        fabric.transition_session(session_id, "arm", actor_id="instructor-a")
        fabric.transition_session(session_id, "start", actor_id="instructor-a")

        with pytest.raises(FabricConflictError, match="optional informational"):
            fabric.assign_role(
                session_id,
                "student_robot",
                node.nodeId,
                actor_id="instructor-a",
            )


def test_armed_physical_session_automatically_disarms_after_inactivity() -> None:
    manifest, node = physical_ground_plugin()
    current = NOW
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(
            repository,
            clock=lambda: current,
            allow_physical=True,
        )
        session_id = prepare_physical_session(fabric, manifest=manifest, node=node)
        fabric.transition_session(session_id, "arm", actor_id="instructor-a")

        current = NOW + timedelta(minutes=3)
        assert fabric.expire_armed_sessions() == (session_id,)
        disarmed = fabric.get_session(session_id)

    assert disarmed.armed is False
    assert disarmed.disarmReason == "inactivity_timeout"
    assert disarmed.state.value == "ready"


def test_simulation_session_rejects_real_physical_actuation_capability() -> None:
    manifest, node = physical_ground_plugin()
    with SQLiteFabricRepository(":memory:") as repository:
        fabric = InteractionFabric(repository, clock=lambda: NOW)
        fabric.register_plugin_and_nodes(manifest, (node,))
        fabric.install_course_pack(physical_course(), actor_id="instructor-a")
        session = fabric.create_session(
            CreateInteractionSessionRequest.model_validate(
                {
                    "coursePackId": "physical-ground-test",
                    "coursePackVersion": "1.0.0",
                    "siteId": "local-site",
                    "roomId": "local-room",
                    "mode": "simulation",
                }
            ),
            actor_id="instructor-a",
        )

        with pytest.raises(FabricPolicyError, match="physical-actuation"):
            fabric.assign_role(
                session.sessionId,
                "student_robot",
                node.nodeId,
                actor_id="instructor-a",
            )
