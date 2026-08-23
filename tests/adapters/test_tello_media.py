from __future__ import annotations

from io import BytesIO

import pytest
from cit_runtime.fabric_media import image_dimensions
from cit_tello.media import _simulation_png, parse_mjpeg_frame


def test_tello_mjpeg_parser_reads_one_bounded_jpeg() -> None:
    jpeg = b"\xff\xd8frame-bytes\xff\xd9"
    response = BytesIO(
        b"--frame\r\n"
        b"Content-Type: image/jpeg\r\n"
        + f"Content-Length: {len(jpeg)}\r\n\r\n".encode()
        + jpeg
        + b"\r\n"
    )

    assert parse_mjpeg_frame(response) == jpeg


@pytest.mark.parametrize(
    "response",
    [
        b"not-a-boundary\r\n",
        b"--frame\r\nContent-Type: image/png\r\nContent-Length: 4\r\n\r\ntest",
        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 9999999\r\n\r\n",
    ],
)
def test_tello_mjpeg_parser_fails_closed(response: bytes) -> None:
    with pytest.raises(ValueError):
        parse_mjpeg_frame(BytesIO(response))


def test_simulated_tello_frame_is_visible_and_within_media_limits() -> None:
    frame = _simulation_png()

    assert len(frame) < 1_048_576
    assert image_dimensions(frame, "image/png") == (320, 180)
