"""Fail-closed authorization checks that do not perform device dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cit_protocol import DeviceCommandIntent

_MOVEMENT_CAPABILITY_PREFIXES = (
    "actuator.",
    "chassis.",
    "drive.",
    "gimbal.",
    "motion.",
    "motor.",
)


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    allowed: bool
    code: str | None = None
    reason: str | None = None


class FoundationSafetyGate:
    """Evaluates only the safety invariants established in Milestone 0."""

    def evaluate(self, command: DeviceCommandIntent, *, now: datetime) -> SafetyDecision:
        del now  # Expiry is claimed separately by the command ledger contract.
        if self._is_stop(command):
            return SafetyDecision(allowed=True)
        if self._is_movement(command) and command.source == "agent_mesh":
            return SafetyDecision(
                allowed=False,
                code="SAFETY_POLICY_DENIED",
                reason="Agent Mesh may propose but may not initiate physical movement",
            )
        if self._is_movement(command) and not command.safetyContext.armed:
            return SafetyDecision(
                allowed=False,
                code="DEVICE_NOT_ARMED",
                reason="Physical movement requires an armed safety context",
            )
        return SafetyDecision(allowed=True)

    @staticmethod
    def _is_movement(command: DeviceCommandIntent) -> bool:
        return command.capability.startswith(_MOVEMENT_CAPABILITY_PREFIXES)

    @staticmethod
    def _is_stop(command: DeviceCommandIntent) -> bool:
        stop_names = {"emergency_stop", "halt", "stop", "stop_all"}
        capability_name = command.capability.rsplit(".", maxsplit=1)[-1]
        return command.action in stop_names or capability_name in stop_names
