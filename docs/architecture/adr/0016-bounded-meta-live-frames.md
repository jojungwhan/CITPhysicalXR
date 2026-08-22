# ADR-0016: Use bounded Meta live frames with snapshot fallback

Status: accepted, 2026-08-22.

## Context

ADR-0015 selected an opt-in snapshot source because physical Meta streaming
support had not yet been verified. Meta Device Access Toolkit 0.9.0 exposes a
video stream as well as photo capture. A tutor needs a current glasses view for
local object recognition, but continuous recording, hidden capture, or a new
high-bandwidth event-bus path would violate the existing privacy boundary.

## Decision

The optional Android companion requests a low-quality DAT stream at two frames
per second and publishes each decoded frame as a bounded JPEG through the
existing latest-frame media endpoint. It copies SDK-owned buffers before
asynchronous work, performs conversion and JPEG encoding off the main thread,
and rejects unexpected dimensions, byte counts, compression state, or images
larger than 1 MiB.

Live sharing requires a visible phone screen, explicit Meta camera permission,
and an explicit **Share live camera** action. Leaving the screen or tapping
**Stop sharing** closes the stream and session. After three consecutive frame
failures the bridge stops; the user may explicitly choose the photo-based
snapshot fallback. Neither mode writes frames to Android storage, Fabric
SQLite, semantic recording, replay, or assessment evidence.

The Fabric source advertises `captureMode: video` or `snapshot`. Both modes use
the same authenticated, site/room-scoped, latest-frame contract and the same
tutor-triggered YOLO and reviewed-action policy from ADR-0015.

## Consequences

- The unified camera wall can show a current Meta view without treating the
  event bus as a video broker.
- Two FPS bounds phone conversion, classroom LAN traffic, browser polling, and
  object-recognition input while remaining useful for tutor-reviewed vision.
- Snapshot fallback preserves compatibility when a phone decoder returns an
  unsupported raw layout or a glasses/firmware combination cannot stream.
- Official DAT 0.9.0 API compilation and an official MockDeviceKit live-frame
  emulator test do not replace a real phone-and-glasses hardware-in-the-loop
  gate.
