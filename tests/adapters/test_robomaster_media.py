from __future__ import annotations

from cit_robomaster_leap.backend import (
    GestureSignal,
    LeapHandSample,
    demo_hand_preview_signal,
    gesture_event_payload,
)
from cit_robomaster_leap.media import RoboMasterMediaPublisher, _simulation_png
from cit_runtime.fabric_media import image_dimensions


class CameraBackend:
    async def start_camera(self) -> None:
        return None

    async def camera_frame(self, *, after_sequence: int):  # type: ignore[no-untyped-def]
        del after_sequence
        return None

    async def stop_camera(self) -> None:
        return None


def hand() -> LeapHandSample:
    return LeapHandSample(
        hand_id=7,
        handedness="right",
        visible_time_seconds=1.25,
        palm_x_mm=12.0,
        palm_y_mm=180.0,
        palm_z_mm=-90.0,
        velocity_x_mm_per_second=1.0,
        velocity_y_mm_per_second=2.0,
        velocity_z_mm_per_second=3.0,
        direction_x=0.0,
        direction_y=0.0,
        direction_z=-1.0,
        normal_x=0.0,
        normal_y=1.0,
        normal_z=0.0,
        pinch_strength=0.82,
        grab_strength=0.14,
        pinch_distance_mm=22.0,
        yaw_degrees=5.0,
    )


def test_leap_gesture_payload_carries_reduced_hand_tracking_without_raw_frames() -> None:
    payload = gesture_event_payload(
        GestureSignal(
            sequence=3,
            monotonic_nanoseconds=4,
            state="DRIVING",
            reason="pinch held",
            confidence=0.95,
            forward_meters_per_second=0.1,
            right_meters_per_second=-0.05,
            clockwise_radians_per_second=0.2,
            tracking=True,
            hand=hand(),
            sensor_frame_id=99,
            sensor_frame_rate_hz=115.0,
            total_hand_count=1,
            service_connected=True,
            device_present=True,
        )
    )

    assert payload["sensorFrameId"] == 99
    assert payload["totalHandCount"] == 1
    assert payload["hand"] == {
        "handId": 7,
        "handedness": "right",
        "visibleTimeSeconds": 1.25,
        "palmMillimeters": {"x": 12.0, "y": 180.0, "z": -90.0},
        "velocityMillimetersPerSecond": {"x": 1.0, "y": 2.0, "z": 3.0},
        "direction": {"x": 0.0, "y": 0.0, "z": -1.0},
        "palmNormal": {"x": 0.0, "y": 1.0, "z": 0.0},
        "pinchStrength": 0.82,
        "grabStrength": 0.14,
        "pinchDistanceMillimeters": 22.0,
        "yawDegrees": 5.0,
    }
    assert "image" not in payload
    assert "rawFrame" not in payload


def test_simulated_robomaster_camera_is_visible_and_bounded() -> None:
    frame = _simulation_png(3)

    assert len(frame) < 1_048_576
    assert image_dimensions(frame, "image/png") == (480, 270)


def test_simulated_leap_preview_stays_visible_without_requesting_motion() -> None:
    preview = demo_hand_preview_signal(7)

    assert preview.sequence == preview.sensor_frame_id == 7
    assert preview.tracking is True
    assert preview.hand is not None
    assert preview.state == "WAITING"
    assert preview.forward_meters_per_second == 0
    assert preview.right_meters_per_second == 0
    assert preview.clockwise_radians_per_second == 0


def test_robomaster_media_source_id_is_stable_and_bounded() -> None:
    publisher = RoboMasterMediaPublisher(
        fabric_origin="http://127.0.0.1:8766",
        credential="x" * 48,
        site_id="local-site",
        room_id="local-room",
        node_id="RoboMaster S1 / classroom A",
        backend=CameraBackend(),
        simulated=True,
    )

    assert publisher.source_id == "robomaster-robomaster-s1---classroom-a"
    assert len(publisher.source_id) <= 64
