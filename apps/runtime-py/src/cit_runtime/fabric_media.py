"""Ephemeral local media and object-detection support for Interaction Fabric.

Raw camera data deliberately does not enter the semantic event repository.  A
publisher owns one exact source and replaces its latest in-memory frame.  The
web console can fetch that frame with its normal bearer credential, while
semantic detections may be copied into ordinary events by a flow later.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import re
import struct
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

MEDIA_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
MEDIA_NODE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
MAX_MEDIA_SOURCES = 32
MAX_FRAME_BYTES = 1_048_576
MAX_DETECTIONS = 50
DEFAULT_VISION_LABELS = ("lamp", "drone", "smart plug", "robot", "light")

MediaKind = Literal[
    "meta_glasses",
    "robomaster",
    "tello",
    "usb_camera",
    "simulator",
]
CaptureMode = Literal["video", "snapshot"]


class FabricMediaError(ValueError):
    """A bounded media request failed without exposing frame contents."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class MediaSourceRegistration:
    source_id: str
    display_name: str
    kind: MediaKind
    capture_mode: CaptureMode
    site_id: str
    room_id: str
    node_id: str | None = None


@dataclass(frozen=True, slots=True)
class MediaFrame:
    source_id: str
    sequence: int
    captured_at: datetime
    received_at: datetime
    content_type: str
    width: int
    height: int
    data: bytes

    @property
    def etag(self) -> str:
        return f'"media-{self.source_id}-{self.sequence}"'


@dataclass(frozen=True, slots=True)
class ObjectDetection:
    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True, slots=True)
class VisionAnalysis:
    source_id: str
    frame_sequence: int
    analyzed_at: datetime
    model: str
    labels: tuple[str, ...]
    detections: tuple[ObjectDetection, ...]


class VisionDetector(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def labels(self) -> tuple[str, ...]: ...

    @property
    def minimum_confidence(self) -> float: ...

    async def analyze(self, frame: MediaFrame, *, at: datetime) -> VisionAnalysis: ...


@dataclass(slots=True)
class _MediaSourceState:
    registration: MediaSourceRegistration
    publisher_identity_id: str
    registered_at: datetime
    latest_frame: MediaFrame | None = None
    latest_analysis: VisionAnalysis | None = None
    sequence: int = 0


class FabricMediaRegistry:
    """Latest-frame registry with no filesystem or database persistence."""

    def __init__(self) -> None:
        self._sources: dict[str, _MediaSourceState] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        registration: MediaSourceRegistration,
        *,
        publisher_identity_id: str,
        at: datetime,
    ) -> dict[str, object]:
        _validate_registration(registration)
        timestamp = _aware_utc(at)
        async with self._lock:
            existing = self._sources.get(registration.source_id)
            if existing is not None and existing.publisher_identity_id != publisher_identity_id:
                raise FabricMediaError(
                    "MEDIA_SOURCE_OWNED",
                    "That media source belongs to a different scoped publisher",
                    status_code=409,
                )
            if existing is None and len(self._sources) >= MAX_MEDIA_SOURCES:
                raise FabricMediaError(
                    "MEDIA_SOURCE_LIMIT",
                    "The local media source limit has been reached",
                    status_code=409,
                )
            state = _MediaSourceState(
                registration=registration,
                publisher_identity_id=publisher_identity_id,
                registered_at=existing.registered_at if existing is not None else timestamp,
                latest_frame=existing.latest_frame if existing is not None else None,
                latest_analysis=existing.latest_analysis if existing is not None else None,
                sequence=existing.sequence if existing is not None else 0,
            )
            self._sources[registration.source_id] = state
            return _source_wire(state, at=timestamp)

    async def remove(
        self,
        source_id: str,
        *,
        identity_id: str,
        can_manage: bool,
    ) -> bool:
        async with self._lock:
            state = self._sources.get(source_id)
            if state is None:
                return False
            if not can_manage and state.publisher_identity_id != identity_id:
                raise FabricMediaError(
                    "MEDIA_SOURCE_OWNED",
                    "That media source belongs to a different scoped publisher",
                    status_code=403,
                )
            del self._sources[source_id]
            return True

    async def publish_frame(
        self,
        source_id: str,
        data: bytes,
        *,
        content_type: str,
        captured_at: datetime,
        publisher_identity_id: str,
        at: datetime,
    ) -> MediaFrame:
        timestamp = _aware_utc(at)
        capture_time = _aware_utc(captured_at)
        if capture_time > timestamp:
            raise FabricMediaError(
                "MEDIA_CAPTURE_TIME_INVALID",
                "A camera frame cannot be timestamped in the future",
            )
        if (timestamp - capture_time).total_seconds() > 30:
            raise FabricMediaError(
                "MEDIA_FRAME_EXPIRED",
                "The camera frame is more than 30 seconds old",
                status_code=409,
            )
        normalized_type = content_type.split(";", 1)[0].strip().lower()
        width, height = image_dimensions(data, normalized_type)
        async with self._lock:
            state = self._sources.get(source_id)
            if state is None:
                raise FabricMediaError(
                    "MEDIA_SOURCE_NOT_FOUND",
                    "Register the camera source before publishing frames",
                    status_code=404,
                )
            if state.publisher_identity_id != publisher_identity_id:
                raise FabricMediaError(
                    "MEDIA_SOURCE_OWNED",
                    "That media source belongs to a different scoped publisher",
                    status_code=403,
                )
            state.sequence += 1
            frame = MediaFrame(
                source_id=source_id,
                sequence=state.sequence,
                captured_at=capture_time,
                received_at=timestamp,
                content_type=normalized_type,
                width=width,
                height=height,
                data=bytes(data),
            )
            state.latest_frame = frame
            state.latest_analysis = None
            return frame

    async def list_sources(
        self,
        *,
        site_id: str | None,
        room_id: str | None,
        at: datetime,
    ) -> list[dict[str, object]]:
        timestamp = _aware_utc(at)
        async with self._lock:
            return [
                _source_wire(state, at=timestamp)
                for state in sorted(
                    self._sources.values(), key=lambda item: item.registration.display_name
                )
                if (site_id is None or state.registration.site_id == site_id)
                and (room_id is None or state.registration.room_id == room_id)
            ]

    async def source(self, source_id: str) -> _MediaSourceState:
        async with self._lock:
            state = self._sources.get(source_id)
            if state is None:
                raise FabricMediaError(
                    "MEDIA_SOURCE_NOT_FOUND",
                    "The camera source is not registered",
                    status_code=404,
                )
            return state

    async def frame(self, source_id: str) -> MediaFrame:
        state = await self.source(source_id)
        if state.latest_frame is None:
            raise FabricMediaError(
                "MEDIA_FRAME_NOT_AVAILABLE",
                "The camera has not published a frame yet",
                status_code=404,
            )
        return state.latest_frame

    async def analyze(
        self,
        source_id: str,
        detector: VisionDetector,
        *,
        at: datetime,
    ) -> VisionAnalysis:
        frame = await self.frame(source_id)
        analysis = await detector.analyze(frame, at=_aware_utc(at))
        async with self._lock:
            state = self._sources.get(source_id)
            if state is not None and state.latest_frame is not None:
                if state.latest_frame.sequence == analysis.frame_sequence:
                    state.latest_analysis = analysis
        return analysis


class UltralyticsWorldDetector:
    """Lazy YOLO-World detector; the large optional dependency stays out of core CI."""

    def __init__(
        self,
        *,
        model: str = "yolov8s-worldv2.pt",
        labels: Iterable[str] = DEFAULT_VISION_LABELS,
        minimum_confidence: float = 0.20,
    ) -> None:
        normalized = tuple(dict.fromkeys(label.strip() for label in labels if label.strip()))
        if not normalized:
            raise ValueError("At least one bounded vision label is required")
        if not 0.05 <= minimum_confidence <= 0.95:
            raise ValueError("Vision confidence must be between 0.05 and 0.95")
        self._model_name = model
        self._labels = normalized
        self._minimum_confidence = minimum_confidence
        self._model: Any | None = None
        self._inference_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def labels(self) -> tuple[str, ...]:
        return self._labels

    @property
    def minimum_confidence(self) -> float:
        return self._minimum_confidence

    async def analyze(self, frame: MediaFrame, *, at: datetime) -> VisionAnalysis:
        async with self._inference_lock:
            detections = await asyncio.to_thread(self._analyze_sync, frame)
        return VisionAnalysis(
            source_id=frame.source_id,
            frame_sequence=frame.sequence,
            analyzed_at=_aware_utc(at),
            model=self._model_name,
            labels=self._labels,
            detections=detections,
        )

    def _analyze_sync(self, frame: MediaFrame) -> tuple[ObjectDetection, ...]:
        try:
            import cv2
            import numpy

            yolo_world = _load_yolo_world()
        except (ImportError, AttributeError) as error:
            raise FabricMediaError(
                "VISION_RUNTIME_UNAVAILABLE",
                "Install the optional local YOLO vision runtime before analyzing images",
                status_code=503,
            ) from error

        encoded = numpy.frombuffer(frame.data, dtype=numpy.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise FabricMediaError(
                "VISION_IMAGE_INVALID",
                "YOLO could not decode the latest camera frame",
            )
        try:
            if self._model is None:
                model = yolo_world(self._model_name)
                model.set_classes(list(self._labels))
                self._model = model
            results = self._model.predict(
                source=image,
                conf=self._minimum_confidence,
                verbose=False,
            )
        except FabricMediaError:
            raise
        except Exception as error:
            raise FabricMediaError(
                "VISION_MODEL_UNAVAILABLE",
                "The local object-recognition model is not ready; restart "
                "Classroom Control after technician setup",
                status_code=503,
            ) from error
        result = next(iter(results), None)
        if result is None:
            return ()
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return ()
        names: dict[int, str] = dict(getattr(result, "names", {}))
        coordinates = boxes.xyxy.cpu().tolist()
        confidences = boxes.conf.cpu().tolist()
        classes = boxes.cls.cpu().tolist()
        detections: list[ObjectDetection] = []
        for coordinate, confidence, class_index in zip(
            coordinates, confidences, classes, strict=True
        ):
            label = names.get(int(class_index), f"class-{int(class_index)}")
            x1, y1, x2, y2 = (float(value) for value in coordinate)
            detections.append(
                ObjectDetection(
                    label=label,
                    confidence=float(confidence),
                    x1=max(0.0, min(x1, float(frame.width))),
                    y1=max(0.0, min(y1, float(frame.height))),
                    x2=max(0.0, min(x2, float(frame.width))),
                    y2=max(0.0, min(y2, float(frame.height))),
                )
            )
        detections.sort(key=lambda item: item.confidence, reverse=True)
        return tuple(detections[:MAX_DETECTIONS])


def _load_yolo_world() -> Any:
    """Resolve Ultralytics' lazily exported YOLOWorld class."""

    ultralytics: Any = importlib.import_module("ultralytics")
    return ultralytics.YOLOWorld


def configured_vision_detector() -> VisionDetector:
    labels = tuple(
        label.strip()
        for label in os.environ.get("CITXR_VISION_LABELS", ",".join(DEFAULT_VISION_LABELS)).split(
            ","
        )
        if label.strip()
    )
    return UltralyticsWorldDetector(
        model=os.environ.get("CITXR_VISION_MODEL", "yolov8s-worldv2.pt"),
        labels=labels,
        minimum_confidence=float(os.environ.get("CITXR_VISION_CONFIDENCE", "0.20")),
    )


def image_dimensions(data: bytes, content_type: str) -> tuple[int, int]:
    if not 32 <= len(data) <= MAX_FRAME_BYTES:
        raise FabricMediaError(
            "MEDIA_FRAME_SIZE_INVALID",
            f"Camera frames must contain between 32 and {MAX_FRAME_BYTES} bytes",
        )
    if content_type == "image/png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 24:
            raise FabricMediaError("MEDIA_FRAME_INVALID", "The PNG camera frame is invalid")
        width, height = struct.unpack(">II", data[16:24])
    elif content_type == "image/jpeg":
        width, height = _jpeg_dimensions(data)
    else:
        raise FabricMediaError(
            "MEDIA_TYPE_UNSUPPORTED",
            "Camera publishers must send image/jpeg or image/png",
            status_code=415,
        )
    if not 1 <= width <= 8192 or not 1 <= height <= 8192:
        raise FabricMediaError(
            "MEDIA_DIMENSIONS_INVALID",
            "Camera frame dimensions must be between 1 and 8192 pixels",
        )
    return width, height


def _jpeg_dimensions(data: bytes) -> tuple[int, int]:
    if not data.startswith(b"\xff\xd8"):
        raise FabricMediaError("MEDIA_FRAME_INVALID", "The JPEG camera frame is invalid")
    offset = 2
    start_of_frame = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        while marker == 0xFF and offset < len(data):
            marker = data[offset]
            offset += 1
        if marker in {0xD8, 0xD9}:
            continue
        if marker == 0xDA:
            break
        if offset + 2 > len(data):
            break
        segment_length = int.from_bytes(data[offset : offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(data):
            break
        if marker in start_of_frame and segment_length >= 7:
            height = int.from_bytes(data[offset + 3 : offset + 5], "big")
            width = int.from_bytes(data[offset + 5 : offset + 7], "big")
            return width, height
        offset += segment_length
    raise FabricMediaError(
        "MEDIA_FRAME_INVALID", "The JPEG camera frame does not contain dimensions"
    )


def analysis_wire(analysis: VisionAnalysis) -> dict[str, object]:
    return {
        "sourceId": analysis.source_id,
        "frameSequence": analysis.frame_sequence,
        "analyzedAt": analysis.analyzed_at.isoformat(),
        "model": analysis.model,
        "labels": list(analysis.labels),
        "detections": [
            {
                "label": item.label,
                "confidence": item.confidence,
                "box": {
                    "x1": item.x1,
                    "y1": item.y1,
                    "x2": item.x2,
                    "y2": item.y2,
                },
            }
            for item in analysis.detections
        ],
    }


def _source_wire(state: _MediaSourceState, *, at: datetime) -> dict[str, object]:
    frame = state.latest_frame
    last_frame_at = frame.received_at if frame is not None else None
    online = last_frame_at is not None and (at - last_frame_at).total_seconds() <= 5
    registration = state.registration
    return {
        "sourceId": registration.source_id,
        "displayName": registration.display_name,
        "kind": registration.kind,
        "captureMode": registration.capture_mode,
        "siteId": registration.site_id,
        "roomId": registration.room_id,
        "nodeId": registration.node_id,
        "state": "online" if online else "waiting",
        "registeredAt": state.registered_at.isoformat(),
        "lastFrameAt": None if frame is None else frame.received_at.isoformat(),
        "frameSequence": 0 if frame is None else frame.sequence,
        "width": None if frame is None else frame.width,
        "height": None if frame is None else frame.height,
        "contentType": None if frame is None else frame.content_type,
        "latestAnalysis": (
            None if state.latest_analysis is None else analysis_wire(state.latest_analysis)
        ),
    }


def _validate_registration(registration: MediaSourceRegistration) -> None:
    if MEDIA_SOURCE_ID.fullmatch(registration.source_id) is None:
        raise FabricMediaError(
            "MEDIA_SOURCE_ID_INVALID",
            "Media source IDs must be 3-64 lowercase letters, numbers, dots, "
            "dashes, or underscores",
        )
    if not 1 <= len(registration.display_name.strip()) <= 100:
        raise FabricMediaError(
            "MEDIA_DISPLAY_NAME_INVALID", "Media source display names must be 1-100 characters"
        )
    if registration.node_id is not None and MEDIA_NODE_ID.fullmatch(registration.node_id) is None:
        raise FabricMediaError("MEDIA_NODE_ID_INVALID", "The media node ID is invalid")
    for label, value in (("site", registration.site_id), ("room", registration.room_id)):
        if not 1 <= len(value.strip()) <= 100 or any(character.isspace() for character in value):
            raise FabricMediaError(
                "MEDIA_SCOPE_INVALID", f"The media {label} ID must be a bounded identifier"
            )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise FabricMediaError(
            "MEDIA_TIMESTAMP_INVALID", "Camera timestamps must include a UTC offset"
        )
    return value.astimezone(UTC)
