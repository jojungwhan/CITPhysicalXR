"""Small, attributed subset of the Dash/Dot BLE packet protocol.

The byte-level behavior is adapted from the Apache-2.0 bleak-dash/morseapi
implementations pinned in config/external-sources.yaml. No third-party runtime
package is embedded here.
"""

from __future__ import annotations

from collections.abc import Mapping

COMMAND_CHARACTERISTIC_UUID = "af230002-879d-6186-1f49-deca0e85d9c1"
COMMON_SENSOR_CHARACTERISTIC_UUID = "af230003-879d-6186-1f49-deca0e85d9c1"
DASH_SENSOR_CHARACTERISTIC_UUID = "af230006-879d-6186-1f49-deca0e85d9c1"

_SOUND_PAYLOADS: tuple[bytes, ...] = (
    bytes.fromhex("53595354424f545f435554455f300b000000"),  # beep
    bytes.fromhex("535953545441485f4441485f30310b000000"),  # ta-da
    bytes.fromhex("5359535446585f4341545f3031000b000000"),  # cat
)


def _signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value > (1 << (bits - 1)) - 1 else value


def _encoded_speed(value: int) -> int:
    bounded = max(-2048, min(2048, value))
    return 0x8000 + abs(bounded) if bounded < 0 else bounded


def drive_packet(linear: int, angular: int) -> bytes:
    """Encode one continuous linear or angular motion.

    Classroom callers bound each axis to +/-200 before this pure encoder.
    The pinned protocol reference has overlapping payload bytes for linear and
    angular speed, so a mixed command is rejected instead of guessed.
    """

    if linear and angular:
        raise ValueError("Dash cannot combine linear and angular velocity in one BLE packet")
    if angular:
        value = _encoded_speed(angular)
        return bytes((0x02, 0, value & 0xFF, (value >> 8) & 0xFF))
    value = _encoded_speed(linear)
    return bytes((0x02, value & 0xFF, (value >> 8) & 0xFF, 0))


def stop_packet() -> bytes:
    return bytes((0x02, 0, 0, 0))


def color_packets(red: int, green: int, blue: int) -> tuple[bytes, ...]:
    rgb = bytes((red, green, blue))
    return (
        bytes((0x03,)) + rgb,
        bytes((0x0B,)) + rgb,
        bytes((0x0C,)) + rgb,
        bytes((0x0D,)) + rgb,
        bytes((0x08, max(red, green, blue))),
        bytes((0x09, 0x1F if any(rgb) else 0, 0xFF if any(rgb) else 0)),
    )


def sound_packet(cue_index: int) -> bytes:
    return bytes((0x18,)) + _SOUND_PAYLOADS[cue_index]


def _angle_byte(angle: int) -> int:
    return angle & 0xFF


def head_packets(pan_degrees: int, tilt_degrees: int) -> tuple[bytes, bytes]:
    return (
        bytes((0x06, _angle_byte(pan_degrees))),
        bytes((0x07, _angle_byte(tilt_degrees))),
    )


def decode_common_sensor(packet: bytes) -> dict[str, object]:
    if len(packet) < 20:
        raise ValueError("Dash/Dot common sensor packet must contain at least 20 bytes")
    posture = packet[11]
    return {
        "pitch": _signed(((packet[4] & 0xF0) << 4) | packet[2], 12),
        "roll": _signed(((packet[4] & 0x0F) << 8) | packet[3], 12),
        "acceleration": _signed(((packet[5] & 0xF0) << 4) | packet[6], 12),
        "mainButtonPressed": bool(packet[8] & 0x10),
        "buttonOnePressed": bool(packet[8] & 0x20),
        "buttonTwoPressed": bool(packet[8] & 0x40),
        "buttonThreePressed": bool(packet[8] & 0x80),
        "moving": posture == 0,
        "pickedUp": bool(posture & 0x04),
        "hit": bool(posture & 0x01),
        "onSide": (posture & 0x20) == 0x20,
        "nominal": (posture & 0x30) == 0x30,
        # Only the semantic clap edge is retained; microphone amplitude is
        # intentionally omitted as sensitive raw audio-derived data.
        "clapDetected": bool(posture & 0x01),
    }


def decode_dash_sensor(packet: bytes, previous: Mapping[str, object]) -> dict[str, object]:
    if len(packet) < 20:
        raise ValueError("Dash sensor packet must contain at least 20 bytes")
    yaw = _signed((packet[13] << 8) | packet[12], 12)
    previous_yaw = previous.get("yaw")
    return {
        "proximityRight": packet[6],
        "proximityLeft": packet[7],
        "proximityRear": packet[8],
        "yaw": yaw,
        "yawDelta": yaw - previous_yaw if isinstance(previous_yaw, int) else 0,
        "leftWheelEncoder": (packet[15] << 8) | packet[14],
        "rightWheelEncoder": (packet[17] << 8) | packet[16],
        "headPitch": _signed(packet[18], 8),
        "headYaw": _signed(packet[19], 8),
        "wheelDistance": _signed(((packet[9] & 0x0F) << 12) | (packet[11] << 8) | packet[10], 16),
    }
