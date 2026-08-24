# ADR-0025: Independent exact-selection Sphero BOLT BLE boundary

Status: Accepted

Date: 2026-08-23

## Context

The unified device catalog represented Sphero BOLT, but Windows discovery only
reported broad PnP presence. It could not prove an exact `SB-XXXX` identity,
connect a robot, publish sensors, or execute a bounded command. Sphero's public
Python SDK targets RVR rather than BOLT. The available BOLT protocol package is
the unofficial MIT-licensed `spherov2`, whose BOLT support and bundled Bleak
adapter require hardware-specific validation.

## Decision

- Implement `cit.sphero-bolt` as an independent out-of-process adapter. Neither
  the Fabric core nor another robot adapter imports `spherov2` or Bleak.
- Discover only exact `SB-[0-9A-Z]{4}` advertisements. Keep BLE addresses in
  the local process and expose a stable SHA-256-derived candidate ID to the UI.
- Do not use Windows pairing, a Sphero account, or a Sphero cloud service.
- Pin `spherov2` 0.12.1 and source revision
  `4252ddb1a12a25db725257d66e3e8ec3057dd48b`. Supply its synchronous adapter
  boundary with the pinned modern Bleak runtime rather than relying on its old
  default scanner.
- Map the canonical two-dimensional ground translation vector to BOLT heading:
  0° forward, 90° right, 180° backward, and 270° left. Do not pretend BOLT
  implements canonical angular velocity; non-zero angular input is rejected.
- Limit translation magnitude to 0.20 m/s and the corresponding conservative
  speed value, then stop locally after 750 ms without a renewed command. The
  original 350 ms pulse did not produce observable movement on the first
  Windows BOLT check because motor startup consumed most of the short pulse.
- Validate the error status in every BOLT command response. Bypass the broken
  `spherov2` 0.12.1/Python 3.13 BOLT LED capability probe by issuing the
  supported matrix and front/back LED commands explicitly in the adapter.
- Expose `sphero.aim.reset` as an explicit vendor capability. It stops first,
  then makes the current physical direction zero. Aim and movement require an
  armed physical lesson.
- Publish normalized sensor summaries at no more than 10 Hz. Do not publish raw
  BLE packets or an unbounded sensor stream.
- Include a software simulator. Keep real firmware/Bluetooth behavior marked
  as pending until a physical HIL checklist passes.

## Consequences

BOLT can be selected and controlled from the same bilingual UI as other
devices while retaining a separate process, manifest, launcher, credential,
state directory, logs, policy, and optional dependency graph. Duplicate
commands do not repeat actions, disconnect/shutdown requests stop locally, and
the browser cannot choose the nearest anonymous robot.

The unofficial protocol dependency remains a compatibility risk. A successful
simulator suite is not evidence that every BOLT firmware accepts every command;
physical HIL must validate connect, aim, LED, sensor, stop, deadman, disconnect,
and shutdown behavior before classroom movement is approved.
