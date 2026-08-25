"""Single source for Sphero Ollie classroom command bounds and conversion."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# Ollie's speed-value-to-distance relationship varies with surface, battery,
# tires, and firmware. Until the physical classroom calibration is recorded,
# expose a conservative semantic bound and a separate raw motor target ceiling.
OLLIE_MAX_TRANSLATION_METERS_PER_SECOND = 0.10
OLLIE_MAX_SPEED_VALUE = 20
OLLIE_NUDGE_METERS_PER_SECOND = 0.08
OLLIE_DEADMAN_MILLISECONDS = 750
OLLIE_DEADMAN_SECONDS = OLLIE_DEADMAN_MILLISECONDS / 1_000


@dataclass(frozen=True, slots=True)
class OllieRoll:
    heading_degrees: int
    speed_value: int


def vector_to_roll(forward: float, right: float, clockwise: float) -> OllieRoll:
    if not all(math.isfinite(value) for value in (forward, right, clockwise)):
        raise ValueError("Sphero Ollie velocity values must be finite")
    if abs(clockwise) > 1e-9:
        raise ValueError(
            "Ollie uses travel heading rather than angular velocity; "
            "clockwise velocity must be zero"
        )
    magnitude = math.hypot(forward, right)
    if magnitude > OLLIE_MAX_TRANSLATION_METERS_PER_SECOND + 1e-9:
        raise ValueError("Sphero Ollie translation exceeds the 0.10 m/s classroom bound")
    if magnitude <= 1e-9:
        return OllieRoll(heading_degrees=0, speed_value=0)
    heading = round(math.degrees(math.atan2(right, forward))) % 360
    speed = round(OLLIE_MAX_SPEED_VALUE * magnitude / OLLIE_MAX_TRANSLATION_METERS_PER_SECOND)
    return OllieRoll(
        heading_degrees=heading,
        speed_value=max(1, min(OLLIE_MAX_SPEED_VALUE, speed)),
    )


def velocity_constraints() -> dict[str, Any]:
    return {
        "arguments": {
            "forwardMetersPerSecond": {
                "minimum": -OLLIE_MAX_TRANSLATION_METERS_PER_SECOND,
                "maximum": OLLIE_MAX_TRANSLATION_METERS_PER_SECOND,
            },
            "rightMetersPerSecond": {
                "minimum": -OLLIE_MAX_TRANSLATION_METERS_PER_SECOND,
                "maximum": OLLIE_MAX_TRANSLATION_METERS_PER_SECOND,
            },
            "clockwiseRadiansPerSecond": {"minimum": 0, "maximum": 0},
        },
        "maximumVectorMagnitudeMetersPerSecond": OLLIE_MAX_TRANSLATION_METERS_PER_SECOND,
        "simultaneousLinearAngular": False,
    }
