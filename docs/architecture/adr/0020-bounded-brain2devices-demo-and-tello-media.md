# ADR 0020 — Bounded Brain2Devices demo and ephemeral Tello media

- Status: Accepted
- Date: 2026-08-23

## Context

Brain2Devices v0.6.35 adds two reusable behaviors beyond the previously pinned
hardware ports: an operator-armed, one-shot MindWave trigger for its automatic
Tello demonstration and locally decoded Tello MJPEG video with an app-scoped
Windows UDP 11111 firewall rule. Reimplementing these would discard tested
vendor-facing behavior. Importing them into either the MindWave or Tello
adapter, or calling the upstream API directly from the browser, would couple
independent nodes and bypass Fabric command tracing and safety.

The preserved rapid single-radio workflow may release an aircraft during Wi-Fi
handoff. Once released, that aircraft may no longer be reachable from the
current adapter. It therefore cannot be represented as ordinary continuous
brain control or a generic takeoff command.

## Decision

- Pin Brain2Devices to merged `main` revision
  `536a256ef3f4b3182a74891b5971e9124ed051b0` (v0.6.35) through
  `config/external-sources.yaml` and generated runtime catalogs.
- Keep `cit.mindwave-mobile2` publish-only and keep `cit.tello` limited to
  telemetry, land, and emergency stop.
- Add `cit.brain2devices-demo` as a third out-of-process plugin. It wraps only
  `mobility.flight.brain_demo.arm`, `mobility.flight.brain_demo.stop`, and
  `telemetry.flight.brain_demo.status` through the fixed loopback API.
- Permit the physical arm command only for the exact device-monitoring safety
  profile, an active and armed physical session, instructor priority, and three
  affirmative confirmations: instructor present, entire flight area clear, and
  emergency plan ready. Autonomous-agent priority remains denied. The adapter
  independently validates the complete parameter set and at least one selected
  signal before calling upstream.
- Retain Brain2Devices' own fresh-reading, signal-quality, calibration, landed,
  single-fleet-slot, one-shot, headset-disconnect, and takeoff-acknowledgement
  checks as a second boundary. CIT does not parse text into flight commands.
- Implement simulation in the third plugin without a drone call. It advances
  through the same visible arm/status lifecycle and completes with an explicit
  simulated phase.
- Let the Tello adapter run an optional media worker in simulation and
  Brain2Devices API modes. The worker registers with the scoped adapter token,
  reads one Content-Length-bounded JPEG at a time, and replaces only the latest
  in-memory Fabric frame. Frames never enter the event bus, SQLite, or replay.
- A camera failure remains diagnostic and never disables land/emergency paths.
  Adapter stop removes its media source and requests safe state.

## Rejected alternatives

- Direct browser-to-Brain2Devices calls would expose the upstream page token,
  omit Fabric audit/lifecycle checks, and couple UI origin policy to a vendor
  process.
- Adding the demo arm capability to the Tello node would make one aircraft
  adapter depend on headset state and hide the legacy combined boundary.
- Mapping ordinary MindWave events to takeoff/movement flows would allow a noisy
  sensor to drive flight and is outside the approved safety model.
- Streaming H.264 or MJPEG through the canonical event bus would violate data
  minimization and overload semantic recording/replay.

## Consequences

- Tutors see signals, demo state, safe-state drone controls, and Tello frames in
  one page while three independently supervised nodes retain clear ownership.
- The core contains one explicit, name/profile/priority-bound flight exception;
  all other non-safe-state flight commands remain rejected.
- The UI and simulator can be regression-tested without hardware. Physical
  video, Windows firewall behavior, MindWave gating, rapid handoff, and recovery
  still require the documented flight-area HIL procedure.
- Upstream API shape is contained in the compatibility plugin and Tello media
  worker; a future native CIT flight lesson can replace them without rewriting
  the independent sensor or telemetry adapters.
