"""Capabilities derived from what is actually plugged in (FR-051).

The PRD's rule is short: "Capabilities must reflect actual connected ports and
hub support." So this module never returns a fixed LEGO capability list. Two
motors produce drive capabilities; one motor does not. No distance sensor, no
``sensor.distance``. The Blockly toolbox is a pure function of this list
(FR-010), so a block for a sensor nobody plugged in cannot appear.
"""

from __future__ import annotations

from collections.abc import Mapping

from .hubs import HubModel, PortKind

MOTOR_CAPABILITIES: tuple[str, ...] = (
    "motor.run",
    "motor.run_time",
    "motor.run_angle",
    "motor.run_target",
    "motor.stop",
)

DRIVE_CAPABILITIES: tuple[str, ...] = (
    "drive.straight",
    "drive.turn",
    "drive.velocity",
    "drive.stop",
)

SENSOR_CAPABILITIES: Mapping[PortKind, tuple[str, ...]] = {
    PortKind.DISTANCE: ("sensor.distance",),
    PortKind.COLOR: ("sensor.color", "sensor.reflection"),
    PortKind.FORCE: ("sensor.force",),
}

IMU_CAPABILITIES: tuple[str, ...] = ("sensor.gyro", "sensor.imu")

HUB_CAPABILITIES: tuple[str, ...] = (
    "hub.display",
    "hub.sound",
    "hub.button",
    "hub.battery",
)


def capabilities_for(model: HubModel, ports: Mapping[str, PortKind]) -> tuple[str, ...]:
    """The exact capability set for one hub with one set of attachments."""

    found: set[str] = set(HUB_CAPABILITIES)
    if model.has_imu:
        found.update(IMU_CAPABILITIES)

    motors = [port for port, kind in ports.items() if kind is PortKind.MOTOR]
    if motors:
        found.update(MOTOR_CAPABILITIES)
    if len(motors) >= 2:
        # A drive base is two motors. One motor is a mechanism, not a robot that
        # can be told to go straight.
        found.update(DRIVE_CAPABILITIES)

    for kind in ports.values():
        found.update(SENSOR_CAPABILITIES.get(kind, ()))

    return tuple(sorted(found))


def motor_ports(ports: Mapping[str, PortKind]) -> tuple[str, ...]:
    return tuple(sorted(port for port, kind in ports.items() if kind is PortKind.MOTOR))


def sensor_port_for(ports: Mapping[str, PortKind], capability: str) -> str | None:
    """Which port answers a sensor capability, or ``None`` if none does."""

    for kind, capabilities in SENSOR_CAPABILITIES.items():
        if capability in capabilities:
            for port in sorted(ports):
                if ports[port] is kind:
                    return port
    return None
