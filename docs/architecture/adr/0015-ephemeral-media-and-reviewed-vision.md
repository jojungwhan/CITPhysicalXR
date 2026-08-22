# ADR-0015: Keep camera frames ephemeral and vision actions reviewed

Status: accepted; Meta snapshot-only consequence superseded by ADR-0016, 2026-08-22.

## Context

Tutors need Meta, robot, drone, and future camera views beside normalized LEGO
and other sensor readings. Raw images do not belong in the semantic event bus,
database, replay log, or assessment record. Phone bridges also cannot be given
the tutor credential, and object-recognition output must not bypass physical
safety policy.

## Decision

Interaction Fabric has a transport-specific local media plane beside, rather
than inside, the canonical event plane. An authenticated publisher registers a
site/room-scoped source and replaces one bounded JPEG or PNG in process memory.
The runtime accepts at most 1 MiB per frame, validates image dimensions, keeps
at most 32 sources, returns `no-store` and ETag headers, and loses all media on
restart. No media table or recorder hook exists.

Tutors issue a high-entropy, five-minute, one-use pairing code for the Meta
phone companion. Redemption produces a seven-day identity with only
`fabric.media.publish` in one site and room. Pairing codes and bearer values are
never written to SQLite. LAN ingress is opt-in at the fixed Windows launcher,
uses one explicit RFC1918 origin, and does not broaden command authority.

YOLO-World runs locally and only after a tutor chooses analysis for one exact
latest frame. The configured vocabulary is bounded. Detections show labels,
confidence, and boxes, but are not commands. Any resulting plug, robot, or
drone action requires a separate explicit tutor control and traverses the
ordinary role, session, authorization, arbitration, safety, and adapter path.
The console only offers the outlet control for the exact `lamp`, `light`, and
`smart plug` labels. Drone and robot detections remain advisory and cannot
expose outlet, movement, arming, or flight controls.

Normalized scalar device readings remain canonical semantic events. The console
derives its sensor cards from the latest `sensor.*`, `telemetry.*`, and
`biosignal.*` event per source/topic and filters media- and credential-shaped
payload keys.

## Consequences

- One page can display heterogeneous views without making the event fabric a
  high-bandwidth video broker.
- A camera or sensor appears only when its adapter really publishes; discovery
  cannot fabricate availability.
- Meta uses opt-in snapshots rather than invisible background capture. The
  Android bridge stores only its scoped token in Android Keystore-backed
  storage and holds images in memory.
- RoboMaster and Tello still require explicit publisher adapters. Supporting
  their source kinds in the media contract does not claim that physical camera
  wiring or HIL is complete.
- The optional local Ultralytics runtime is covered by its own upstream license;
  it does not relicense the rest of the project.
