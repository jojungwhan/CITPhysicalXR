# 0030 — Bounded manual Tello control

Status: Accepted — 2026-08-25

## Context

The independent Tello adapter originally exposed telemetry, land, and emergency
stop only. Tutors could connect one grounded aircraft but received no ordinary
takeoff or movement controls. The separate MindWave demo and fleet sequence are
purpose-specific one-shot workflows and are not a usable substitute for direct
per-aircraft teaching controls.

Windows also retained managed static routes for unplugged USB Wi-Fi adapters.
Brain2Devices correctly rejected broad auto-connect in that state, leaving the
visible replacement radio undiscoverable from the tutor workflow even though
Brain2Devices already provided a no-takeoff single-radio preparation path.

## Decision

Each `cit.tello` node consumes five canonical operations: takeoff, discrete
move, rotate, land, and emergency stop. Physical takeoff, move, and rotate are
accepted only when all of these conditions hold:

- the Fabric session is active and armed;
- physical dispatch is explicitly enabled;
- priority is `instructor_override`, never `autonomous_agent`;
- the safety profile is `classroom-drone-monitoring`;
- `instructorPresent`, `flightAreaClear`, and `emergencyPlanReady` are exactly
  `true` with no unrecognized parameters;
- movement uses one of six discrete directions and an integer distance from 20
  through 50 cm;
- rotation uses a boolean direction and an integer angle from 1 through 90°.

The runtime policy validates this contract before dispatch. The Tello adapter
independently repeats the exact-shape, confirmation, direction, and numeric
checks before translating to the loopback-only Brain2Devices fleet API or the
pinned out-of-process vendor port. No continuous RC, arbitrary SDK packet, or
text-to-command path is exposed. Land and emergency stop remain safe-state
operations available without arming.

The tutor card always shows the safety checklist and bounded controls for a
current Tello node. Its first non-safe command explicitly prepares the existing
monitoring session, or creates and assigns a scoped device-monitoring session if
none exists. Takeoff also requires a final confirmation dialog.

When broad local-radio auto-connect fails with Brain2Devices' exact stale
managed-static-route refusal, discovery calls its existing fully automatic
**prepare** endpoint. That path reconciles the currently present radio and
performs the SDK handshake without sending takeoff. No other connection failure
is silently converted to this recovery path.

## Consequences

- One connected Tello now has direct controls without requiring the multi-drone
  fleet controller or MindWave demo.
- Generated capability bindings remain the single source of truth across the
  runtime and adapter.
- Replay remains dry-run, agents cannot command flight, and connection still
  cannot actuate an aircraft.
- Software tests cover recovery selection, dual safety validation, translation,
  idempotency, session selection, and rendered controls.
- Physical takeoff, movement, rotation, lost-link, and landing evidence still
  require a propeller-safe or netted hardware-in-the-loop session.
