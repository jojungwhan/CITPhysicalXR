"""Single source for Sphero BOLT classroom command bounds and conversion."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

SPHERO_MAX_TRANSLATION_METERS_PER_SECOND = 0.20
SPHERO_REPORTED_TOP_METERS_PER_SECOND = 2.0
SPHERO_MAX_SPEED_VALUE = round(
    255 * SPHERO_MAX_TRANSLATION_METERS_PER_SECOND / SPHERO_REPORTED_TOP_METERS_PER_SECOND
)
# A 350 ms pulse at the classroom speed bound was absorbed by BOLT's motor
# start-up on real hardware. 750 ms remains a short, locally bounded nudge
# while giving the closed-loop drive enough time to produce visible motion.
SPHERO_DEADMAN_MILLISECONDS = 750
SPHERO_DEADMAN_SECONDS = SPHERO_DEADMAN_MILLISECONDS / 1_000


@dataclass(frozen=True, slots=True)
class SpheroRoll:
    heading_degrees: int
    speed_value: int


def vector_to_roll(forward: float, right: float, clockwise: float) -> SpheroRoll:
    if not all(math.isfinite(value) for value in (forward, right, clockwise)):
        raise ValueError("Sphero velocity values must be finite")
    if abs(clockwise) > 1e-9:
        raise ValueError(
            "BOLT uses travel heading rather than angular velocity; clockwise velocity must be zero"
        )
    magnitude = math.hypot(forward, right)
    if magnitude > SPHERO_MAX_TRANSLATION_METERS_PER_SECOND + 1e-9:
        raise ValueError("Sphero translation exceeds the 0.20 m/s classroom bound")
    if magnitude <= 1e-9:
        return SpheroRoll(heading_degrees=0, speed_value=0)
    heading = round(math.degrees(math.atan2(right, forward))) % 360
    speed = min(
        SPHERO_MAX_SPEED_VALUE,
        round(255 * magnitude / SPHERO_REPORTED_TOP_METERS_PER_SECOND),
    )
    return SpheroRoll(heading_degrees=heading, speed_value=max(1, speed))


def velocity_constraints() -> dict[str, Any]:
    return {
        "arguments": {
            "forwardMetersPerSecond": {
                "minimum": -SPHERO_MAX_TRANSLATION_METERS_PER_SECOND,
                "maximum": SPHERO_MAX_TRANSLATION_METERS_PER_SECOND,
            },
            "rightMetersPerSecond": {
                "minimum": -SPHERO_MAX_TRANSLATION_METERS_PER_SECOND,
                "maximum": SPHERO_MAX_TRANSLATION_METERS_PER_SECOND,
            },
            "clockwiseRadiansPerSecond": {"minimum": 0, "maximum": 0},
        },
        "maximumVectorMagnitudeMetersPerSecond": SPHERO_MAX_TRANSLATION_METERS_PER_SECOND,
        "simultaneousLinearAngular": False,
    }
