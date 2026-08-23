"""Single source for Dash/Dot device-level command policy."""

from __future__ import annotations

from typing import Any

DASH_MAX_FORWARD_METERS_PER_SECOND = 0.20
DASH_MAX_CLOCKWISE_RADIANS_PER_SECOND = 0.6108652382
DASH_HEAD_PAN_MIN_DEGREES = -53
DASH_HEAD_PAN_MAX_DEGREES = 53
DASH_HEAD_TILT_MIN_DEGREES = -5
DASH_HEAD_TILT_MAX_DEGREES = 10
DASH_DEADMAN_MILLISECONDS = 350
DASH_DEADMAN_SECONDS = DASH_DEADMAN_MILLISECONDS / 1_000
WONDER_SOUND_CUE_COUNT = 3


def dash_velocity_constraints() -> dict[str, Any]:
    """Return an unshared descriptor copy safe for Pydantic normalization."""

    return {
        "arguments": {
            "forwardMetersPerSecond": {
                "minimum": -DASH_MAX_FORWARD_METERS_PER_SECOND,
                "maximum": DASH_MAX_FORWARD_METERS_PER_SECOND,
            },
            "rightMetersPerSecond": {"minimum": 0, "maximum": 0},
            "clockwiseRadiansPerSecond": {
                "minimum": -DASH_MAX_CLOCKWISE_RADIANS_PER_SECOND,
                "maximum": DASH_MAX_CLOCKWISE_RADIANS_PER_SECOND,
            },
        },
        "simultaneousLinearAngular": False,
    }
