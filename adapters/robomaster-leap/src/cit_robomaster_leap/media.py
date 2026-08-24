"""Ephemeral RoboMaster camera publisher for the shared Fabric media plane."""

from __future__ import annotations

import asyncio
import json
import re
import struct
import zlib
from datetime import UTC, datetime
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .backend import RobotCameraFrame


class RoboMasterCameraBackend(Protocol):
    async def start_camera(self) -> None: ...

    async def camera_frame(self, *, after_sequence: int) -> RobotCameraFrame | None: ...

    async def stop_camera(self) -> None: ...


class _MediaSourceMissingError(ValueError):
    """The ephemeral runtime registry was lost and must be recreated."""


class RoboMasterMediaPublisher:
    """Publish only the latest preview frame; no camera data is persisted."""

    def __init__(
        self,
        *,
        fabric_origin: str,
        credential: str,
        site_id: str,
        room_id: str,
        node_id: str,
        backend: RoboMasterCameraBackend,
        simulated: bool,
    ) -> None:
        if not credential:
            raise ValueError("RoboMaster media publishing requires a scoped credential")
        normalized = re.sub(r"[^a-z0-9._-]", "-", node_id.casefold())[:49]
        if not normalized:
            raise ValueError("RoboMaster node id cannot produce an empty media source id")
        self._fabric_origin = fabric_origin.rstrip("/")
        self._credential = credential
        self._site_id = site_id
        self._room_id = room_id
        self._node_id = node_id
        self._backend = backend
        self._simulated = simulated
        self.source_id = f"robomaster-{normalized}"
        self.last_error: str | None = None
        self.frames_published = 0
        self._registered = False
        self._camera_started = False
        self._vendor_sequence = 0

    async def run(self) -> None:
        try:
            while True:
                delay = 0.25
                try:
                    if not self._registered:
                        await asyncio.to_thread(self._register)
                        self._registered = True
                    if self._simulated:
                        frame = await asyncio.to_thread(_simulation_png, self.frames_published)
                        content_type = "image/png"
                    else:
                        if not self._camera_started:
                            await self._backend.start_camera()
                            self._camera_started = True
                        captured = await self._backend.camera_frame(
                            after_sequence=self._vendor_sequence
                        )
                        if captured is None:
                            await asyncio.sleep(delay)
                            continue
                        self._vendor_sequence = captured.sequence
                        frame = captured.jpeg
                        content_type = "image/jpeg"
                    await asyncio.to_thread(self._publish_frame, frame, content_type)
                    self.frames_published += 1
                    self.last_error = None
                except (OSError, RuntimeError, ValueError, URLError) as error:
                    self.last_error = str(error)[:500]
                    delay = 1.0
                    if isinstance(error, _MediaSourceMissingError):
                        self._registered = False
                    if self._camera_started and not self._simulated:
                        await self._backend.stop_camera()
                        self._camera_started = False
                await asyncio.sleep(delay)
        finally:
            if self._camera_started:
                await self._backend.stop_camera()
                self._camera_started = False
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
                    "Simulated RoboMaster S1 camera" if self._simulated else "RoboMaster S1 camera"
                ),
                "kind": "simulator" if self._simulated else "robomaster",
                "captureMode": "video",
                "siteId": self._site_id,
                "roomId": self._room_id,
                "nodeId": self._node_id,
            },
        )

    def _publish_frame(self, frame: bytes, content_type: str) -> None:
        request = Request(
            f"{self._fabric_origin}/api/v1/fabric/media/sources/{quote(self.source_id)}/frame",
            data=frame,
            method="PUT",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._credential}",
                "Content-Type": content_type,
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


def _simulation_png(sequence: int = 0) -> bytes:
    width, height = 480, 270
    rows: list[bytes] = []
    shift = sequence % 64
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            grid = 24 if ((x + shift) // 32 + y // 32) % 2 else 0
            center = 36 if abs(x - width // 2) < 80 and abs(y - height // 2) < 55 else 0
            row.extend((24 + grid, 62 + grid + center, 105 + grid + center))
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
