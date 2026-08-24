"""Ephemeral Tello camera bridge from Brain2Devices into Fabric media."""

from __future__ import annotations

import asyncio
import json
import re
import struct
import zlib
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

_MAX_FRAME_BYTES = 1_048_576


class _MediaSourceMissingError(ValueError):
    """The ephemeral runtime registry was lost and must be recreated."""


class TelloMediaPublisher:
    """Replace one in-memory Fabric frame; never place video on the event bus."""

    def __init__(
        self,
        *,
        fabric_origin: str,
        credential: str,
        site_id: str,
        room_id: str,
        node_id: str,
        activation_file: Path,
        simulated: bool,
        brain2devices_origin: str = "http://127.0.0.1:8765",
        brain2devices_drone_id: str = "primary",
    ) -> None:
        if not credential:
            raise ValueError("Tello media publishing requires a scoped credential")
        if not simulated and brain2devices_origin != "http://127.0.0.1:8765":
            raise ValueError("Brain2Devices video is restricted to loopback")
        self._fabric_origin = fabric_origin.rstrip("/")
        self._credential = credential
        self._site_id = site_id
        self._room_id = room_id
        self._node_id = node_id
        self._activation_file = activation_file
        self._simulated = simulated
        self._brain2devices_origin = brain2devices_origin
        self._drone_id = brain2devices_drone_id
        normalized = re.sub(r"[^a-z0-9._-]", "-", node_id.casefold())[:54]
        self.source_id = f"tello-{normalized}"
        self.last_error: str | None = None
        self.frames_published = 0
        self._registered = False

    async def run(self) -> None:
        try:
            while True:
                if not self._activation_file.is_file():
                    await asyncio.sleep(0.25)
                    continue
                try:
                    if not self._registered:
                        await asyncio.to_thread(self._register)
                        self._registered = True
                    frame = (
                        _simulation_png()
                        if self._simulated
                        else await asyncio.to_thread(self._brain2devices_frame)
                    )
                    if frame is not None:
                        await asyncio.to_thread(self._publish_frame, frame)
                        self.frames_published += 1
                        self.last_error = None
                except (OSError, ValueError, URLError) as error:
                    self.last_error = str(error)[:500]
                    if isinstance(error, _MediaSourceMissingError):
                        self._registered = False
                # The UI displays an authenticated preview, not a control loop.
                # Four frames per second is responsive enough for tutors while
                # keeping decoding and classroom-network load bounded.
                await asyncio.sleep(0.25)
        finally:
            if self._registered:
                try:
                    await asyncio.to_thread(self._remove)
                except (OSError, URLError):
                    pass

    def _register(self) -> None:
        self._fabric_json(
            "/api/v1/fabric/media/sources",
            method="POST",
            body={
                "sourceId": self.source_id,
                "displayName": (
                    "Simulated Tello camera"
                    if self._simulated
                    else f"Tello {self._drone_id} camera"
                ),
                "kind": "simulator" if self._simulated else "tello",
                "captureMode": "video",
                "siteId": self._site_id,
                "roomId": self._room_id,
                "nodeId": self._node_id,
            },
        )

    def _publish_frame(self, frame: bytes) -> None:
        request = Request(
            f"{self._fabric_origin}/api/v1/fabric/media/sources/{quote(self.source_id)}/frame",
            data=frame,
            method="PUT",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._credential}",
                "Content-Type": "image/png" if self._simulated else "image/jpeg",
                "X-CIT-Captured-At": datetime.now(UTC).isoformat(),
            },
        )
        self._open_checked(request, limit=65_536)

    def _remove(self) -> None:
        request = Request(
            f"{self._fabric_origin}/api/v1/fabric/media/sources/{quote(self.source_id)}",
            method="DELETE",
            headers={"Authorization": f"Bearer {self._credential}"},
        )
        try:
            self._open_checked(request, limit=1024)
        except (HTTPError, _MediaSourceMissingError) as error:
            if isinstance(error, HTTPError) and error.code != 404:
                raise

    def _brain2devices_frame(self) -> bytes | None:
        state = self._json_request(f"{self._brain2devices_origin}/api/state")
        video = state.get("video")
        feeds = video.get("feeds") if isinstance(video, dict) else None
        if not isinstance(feeds, list):
            raise ValueError("Brain2Devices video status is unavailable")
        feed = next(
            (
                item
                for item in feeds
                if isinstance(item, dict) and item.get("drone_id") == self._drone_id
            ),
            None,
        )
        if not isinstance(feed, dict):
            raise ValueError(f"Brain2Devices has no camera feed for {self._drone_id}")
        session_id = feed.get("session_id")
        if not isinstance(session_id, str) or len(session_id) != 32 or not session_id.isalnum():
            state_name = str(feed.get("state", "waiting"))
            if state_name in {"waiting", "starting", "stopped"}:
                return None
            raise ValueError(str(feed.get("message", "Tello camera session is unavailable")))
        stream = (
            f"{self._brain2devices_origin}/api/video/{quote(self._drone_id)}/stream.mjpg"
            f"?session={quote(session_id)}"
        )
        try:
            with urlopen(stream, timeout=5) as response:
                return parse_mjpeg_frame(response)
        except HTTPError as error:
            raise ValueError(f"Brain2Devices camera returned HTTP {error.code}") from error

    def _fabric_json(
        self,
        path: str,
        *,
        method: str,
        body: dict[str, object],
    ) -> dict[str, object]:
        request = Request(
            f"{self._fabric_origin}{path}",
            data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._credential}",
                "Content-Type": "application/json",
            },
        )
        raw = self._open_checked(request, limit=262_144)
        value: object = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Fabric media response must be an object")
        return value

    @staticmethod
    def _json_request(url: str) -> dict[str, object]:
        request = Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=5) as response:
                raw = response.read(262_144)
            value: object = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Brain2Devices returned invalid video status") from error
        if not isinstance(value, dict):
            raise ValueError("Brain2Devices video status must be an object")
        return value

    @staticmethod
    def _open_checked(request: Request, *, limit: int) -> bytes:
        try:
            with urlopen(request, timeout=10) as response:
                raw = response.read(limit)
            if not isinstance(raw, bytes):
                raise ValueError("HTTP response body must be bytes")
            return raw
        except HTTPError as error:
            detail = ""
            try:
                value = json.loads(error.read(65_536).decode("utf-8"))
                if isinstance(value, dict):
                    detail = str(value.get("message") or value.get("error") or "")
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass
            message = detail or f"Fabric media returned HTTP {error.code}"
            if error.code == 404:
                raise _MediaSourceMissingError(message[:500]) from error
            raise ValueError(message[:500]) from error


def parse_mjpeg_frame(response: object) -> bytes:
    """Read exactly one Content-Length-delimited JPEG from an MJPEG response."""

    readline = getattr(response, "readline", None)
    read = getattr(response, "read", None)
    if not callable(readline) or not callable(read):
        raise ValueError("MJPEG response is not readable")
    boundary = readline(256)
    if not isinstance(boundary, bytes) or not boundary.startswith(b"--"):
        raise ValueError("MJPEG stream has no frame boundary")
    headers: dict[str, str] = {}
    for _ in range(32):
        line = readline(4096)
        if not isinstance(line, bytes):
            raise ValueError("MJPEG header is invalid")
        if line in {b"\r\n", b"\n"}:
            break
        try:
            name, value = line.decode("ascii").split(":", 1)
        except (UnicodeDecodeError, ValueError) as error:
            raise ValueError("MJPEG header is invalid") from error
        headers[name.strip().casefold()] = value.strip()
    else:
        raise ValueError("MJPEG headers are too large")
    if headers.get("content-type", "").casefold() != "image/jpeg":
        raise ValueError("MJPEG frame is not JPEG")
    try:
        length = int(headers["content-length"])
    except (KeyError, ValueError) as error:
        raise ValueError("MJPEG frame has no valid content length") from error
    if not 1 <= length <= _MAX_FRAME_BYTES:
        raise ValueError("MJPEG frame size is outside Fabric limits")
    frame = read(length)
    if not isinstance(frame, bytes) or len(frame) != length:
        raise ValueError("MJPEG frame ended early")
    if not frame.startswith(b"\xff\xd8") or not frame.endswith(b"\xff\xd9"):
        raise ValueError("MJPEG payload is not a complete JPEG")
    return frame


def _simulation_png() -> bytes:
    width, height = 320, 180
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            stripe = 30 if (x // 24 + y // 24) % 2 else 0
            row.extend((32 + stripe, 91 + stripe, 65 + stripe))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = struct.pack(">I", zlib.crc32(kind + data))
        return struct.pack(">I", len(data)) + kind + data + checksum

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, level=6))
        + chunk(b"IEND", b"")
    )
