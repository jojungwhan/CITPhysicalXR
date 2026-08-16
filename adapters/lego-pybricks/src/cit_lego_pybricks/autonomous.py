"""Autonomous mode: a program that runs on the hub itself (FR-048).

Host-controlled mode is the classroom default, because it is the mode where a
person is holding the computer that is holding the robot. Autonomous mode is for
the lessons the PRD names -- line following, embedded sensor loops, competition
programs, a robot working with the laptop closed -- and it is a genuinely
different safety posture: once a program is installed, the runtime is not in the
loop, so the hub's own stop behavior is the only stop behavior left.

Two consequences, both enforced rather than described:

- The program is built from a **closed set of steps**, not from arbitrary
  Python. A student's blocks become a step list; the step list becomes source.
  There is no path from student text to hub source.
- The program **stops what it started**. Every generated program ends in a
  ``finally`` that stops the drive base and every motor, so an exception in the
  middle of a lesson leaves a still robot rather than a running one.

Installing the program is a separate, instructor-gated act
(:meth:`~cit_lego_pybricks.adapter.PybricksHubAdapter.install_program`).
Generating source here neither connects to a hub nor sends anything.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .capabilities import motor_ports
from .hubs import HubModel, PortKind

#: Pybricks speaks degrees per second. A normalized speed of 1.0 means this,
#: before the class ceiling is applied.
MAX_MOTOR_DEGREES_PER_SECOND = 1000

#: Pybricks drive bases are told real millimetres. These are the standard SPIKE
#: driving-base dimensions; a different build overrides them per device.
DEFAULT_WHEEL_DIAMETER_MM = 56
DEFAULT_AXLE_TRACK_MM = 114


@dataclass(frozen=True, slots=True)
class DriveGeometry:
    wheel_diameter_mm: int = DEFAULT_WHEEL_DIAMETER_MM
    axle_track_mm: int = DEFAULT_AXLE_TRACK_MM


@dataclass(frozen=True, slots=True)
class MotorRun:
    port: str
    speed: float
    seconds: float


@dataclass(frozen=True, slots=True)
class MotorAngle:
    port: str
    angle: int
    speed: float


@dataclass(frozen=True, slots=True)
class DriveStraight:
    millimetres: int
    speed: float


@dataclass(frozen=True, slots=True)
class DriveTurn:
    angle: int
    speed: float


@dataclass(frozen=True, slots=True)
class Wait:
    seconds: float


@dataclass(frozen=True, slots=True)
class Display:
    text: str


Step = MotorRun | MotorAngle | DriveStraight | DriveTurn | Wait | Display


class ProgramError(ValueError):
    """A step that cannot be turned into a program for this hub."""


def _motor_name(port: str) -> str:
    return f"motor_{port.lower()}"


def _degrees_per_second(speed: float, *, max_percent: int) -> int:
    bounded = max(-1.0, min(1.0, float(speed)))
    ceiling = MAX_MOTOR_DEGREES_PER_SECOND * max_percent / 100
    return round(max(-ceiling, min(ceiling, bounded * MAX_MOTOR_DEGREES_PER_SECOND)))


def _milliseconds(seconds: float, *, maximum: int) -> int:
    return max(1, min(maximum, round(abs(float(seconds)) * 1000)))


def build_program(
    model: HubModel,
    ports: Mapping[str, PortKind],
    steps: Sequence[Step],
    *,
    max_motor_percent: int = 75,
    max_command_milliseconds: int = 2000,
    geometry: DriveGeometry | None = None,
) -> str:
    """Render deterministic Pybricks MicroPython for one step list."""

    if not steps:
        raise ProgramError("An autonomous program needs at least one step")

    drive_geometry = geometry or DriveGeometry()
    motors = motor_ports(ports)
    if not motors:
        raise ProgramError(
            f"{model.display_name} has no motor in any port, so it has nothing to run"
        )

    body: list[str] = []
    uses_drive_base = False
    for step in steps:
        match step:
            case MotorRun(port=port, speed=speed, seconds=seconds):
                _require_motor(model, ports, port)
                body.append(
                    f"    {_motor_name(port)}.run_time("
                    f"{_degrees_per_second(speed, max_percent=max_motor_percent)}, "
                    f"{_milliseconds(seconds, maximum=max_command_milliseconds)})"
                )
            case MotorAngle(port=port, angle=angle, speed=speed):
                _require_motor(model, ports, port)
                body.append(
                    f"    {_motor_name(port)}.run_angle("
                    f"{_degrees_per_second(speed, max_percent=max_motor_percent)}, "
                    f"{int(angle)})"
                )
            case DriveStraight(millimetres=millimetres, speed=_):
                _require_drive_base(motors)
                uses_drive_base = True
                body.append(f"    drive_base.straight({int(millimetres)})")
            case DriveTurn(angle=angle, speed=_):
                _require_drive_base(motors)
                uses_drive_base = True
                body.append(f"    drive_base.turn({int(angle)})")
            case Wait(seconds=seconds):
                body.append(f"    wait({_milliseconds(seconds, maximum=max_command_milliseconds)})")
            case Display(text=text):
                body.append(f"    hub.display.text({_literal(text)})")
            case _:  # pragma: no cover - the union is closed
                raise ProgramError(f"{step!r} is not a program step")

    header = [
        f"# Generated by CIT Physical XR for a {model.display_name}.",
        "# Autonomous mode (FR-048): this program runs on the hub with no computer",
        f"# attached. Motor power is capped at {max_motor_percent} percent, and the",
        "# program stops every motor even when a step fails.",
        f"from pybricks.hubs import {model.pybricks_hub_class}",
        "from pybricks.parameters import Port",
        "from pybricks.pupdevices import Motor",
    ]
    if uses_drive_base:
        header.append("from pybricks.robotics import DriveBase")
    header.append("from pybricks.tools import wait")
    header.append("")
    header.append(f"hub = {model.pybricks_hub_class}()")
    for port in motors:
        header.append(f"{_motor_name(port)} = Motor(Port.{port})")
    if uses_drive_base:
        header.append(
            "drive_base = DriveBase("
            f"{_motor_name(motors[0])}, {_motor_name(motors[1])}, "
            f"wheel_diameter={drive_geometry.wheel_diameter_mm}, "
            f"axle_track={drive_geometry.axle_track_mm})"
        )

    footer = ["", "", "try:", "    main()", "finally:"]
    if uses_drive_base:
        footer.append("    drive_base.stop()")
    footer.extend(f"    {_motor_name(port)}.stop()" for port in motors)

    lines = [*header, "", "", "def main():", *body, *footer]
    return "\n".join(lines) + "\n"


def _require_motor(model: HubModel, ports: Mapping[str, PortKind], port: str) -> None:
    letter = port.upper()
    if not model.has_port(letter):
        raise ProgramError(
            f"{model.display_name} has no port {letter}. Ports: {', '.join(model.ports)}."
        )
    if ports.get(letter) is not PortKind.MOTOR:
        raise ProgramError(f"Port {letter} has no motor in it, so it cannot be told to run")


def _require_drive_base(motors: Sequence[str]) -> None:
    if len(motors) < 2:
        raise ProgramError(
            f"Driving straight or turning needs two motors; this hub has {len(motors)}"
        )


def _literal(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{escaped[:32]}"'
