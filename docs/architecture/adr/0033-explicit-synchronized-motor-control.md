# 0033 — Explicit synchronized motor-control session

Status: Accepted — 2026-08-25

## Context

Tutors need one compact switch and one directional pad for moving every
connected Sphero BOLT and Ollie together. The same bounded group needs to accept
G2 and Meta structured voice, Even R1 ring gestures, and MindWave input. Tello
may be reachable through only one classroom Wi-Fi route and cannot be treated
as an always-available ground robot.

Reusing the ordinary device-monitoring session as the enable switch would be
unsafe: an unrelated direct-control click can arm that session, accidentally
making wearable or biosignal flows live. A vendor-to-vendor controller would
also violate the Fabric boundary and lose per-output lifecycle and safety
decisions.

## Decision

Use the dedicated `synchronized-motor-control` course and create a fresh
physical session only after the tutor selects **Control connected BOLT and
Ollie together**. Disabling the switch submits an independent stop to every
assigned ground role and terminates that session. Reloaded consoles adopt and
show an existing active, armed synchronized session instead of presenting a
false off state.

Each ground output is an exact `ground_output_1..8` role requiring
`mobility.ground.nudge`. The runtime expands one matching semantic event into
one normal command per role in a named `parallelGroup`; adapter bounds,
idempotency, arbitration, safety evaluation, lifecycle reporting, and local
watchdogs remain independent.

Input mappings are deterministic:

- confirmed G2 or Meta `interaction.intent.device_control` directions fan out
  to every assigned ground role;
- R1 scroll up/down maps to forward/backward, and tap maps to stop;
- one debounced `mindwave.blink` starts one adapter-bounded 10 cm
  demonstration on every assigned ground robot;
- R1 double-tap and confirmed glasses takeoff/land retain the separately armed
  Tello fleet contract.

MindWave uses a second publish-only projection of the already local
Brain2Devices state, with a distinct node and session credential. It does not
open another Bluetooth connection or persist raw EEG. Blink is treated as a
discrete interaction event; vendor eSense values are not renamed or interpreted
as objective attention.

Tello directional movement is excluded by default. The console enables its
separate checkbox only after a live bounded Tello route and the existing flight
safety confirmation are present. The drone must be taken off through its
normal controls first. Group stop never maps to Tello emergency motor stop or
an implicit landing.

## Consequences

- Ordinary Sphero controls cannot silently enable wearable or MindWave flows.
- G2, Meta, R1, and MindWave converge in the orchestration recipe without
  importing or calling an output adapter.
- “Synchronized” is concurrent best-effort dispatch, not atomic motion or a
  hard-real-time start guarantee. Vendor latency and kinematics remain visible.
- One stock access-point-mode Tello remains limited to one usable Wi-Fi route;
  additional simultaneous aircraft require independent radios or supported
  station-mode routes.
- Tello arming, takeoff, landing, and emergency behavior remain outside the
  ground group switch.
