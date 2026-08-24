# ADR-0026: Ephemeral robot media and semantic Leap hand view

Status: Accepted

Date: 2026-08-24

## Context

The unified classroom page already had an authenticated latest-frame media
plane and working Meta and Tello publishers, but RoboMaster only advertised a
possible media kind. The Leap adapter published bounded movement vectors, so a
tutor could not verify hand detection before enabling a lesson. Importing DJI,
OpenCV, or LeapC into the runtime would violate the vendor boundary, while
putting raw video or high-rate tracking frames in SQLite would violate data
minimization and the edge-processing design.

## Decision

- Keep the existing in-memory, latest-frame media plane as the only browser
  path for Meta, Tello, RoboMaster, and approved local cameras.
- Run RoboMaster capture inside the existing external DJI worker that already
  owns the robot connection. A background camera pump reads 360p SDK frames;
  the safety-sensitive JSON command loop only copies the latest bounded JPEG.
- Give only the RoboMaster adapter identity `fabric.media.publish`. The camera
  publisher has no session-management, movement, or media-read permission.
- Register and publish the camera independently of chassis arming. A camera
  failure appears in health metrics and must not crash, arm, or move the robot.
- Do not create a second DJI robot connection for video. Do not publish a
  physical SDK camera for the stock desktop-app transport until that boundary
  has separate characterization and HIL evidence.
- Extend the existing Leap semantic gesture event with one validated reduced
  hand sample: handedness, palm position/velocity/direction/normal, pinch,
  grab, and tracking metadata. Raw Leap frames and images remain inside the
  vendor worker.
- Allow physical Leap observation after the tutor explicitly connects the
  adapter, even while the lesson and robot remain disarmed. The session,
  arbitration, safety, and adapter bounds continue to gate every command.
- Render the hand sample as a bilingual semantic top-down view. It is a tutor
  diagnostic, not an anatomical reconstruction or biometric assessment.
- Poll authenticated live camera frames at a bounded four checks per second
  and snapshot sources every 1.5 seconds. Poll Leap events only while a Leap
  node and selected session are present.

## Consequences

All requested feeds share one UI and one transport-neutral media contract,
while each publisher remains independently supervised. Video is never placed on
the event bus or disk, and Leap sends enough information to verify detection
without streaming raw sensor frames. Camera and tracking status are observable
without granting physical-control authority.

The browser preview is a bounded classroom diagnostic rather than full-rate
teleoperation video. Physical RoboMaster camera throughput, OpenCV availability,
Leap responsiveness, simultaneous multi-feed load, disconnect handling, and
Windows firewall behavior still require hardware-in-the-loop evidence.
