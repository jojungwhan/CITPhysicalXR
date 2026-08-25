# 0023 — Capability-derived I/O direction and safe parallel fan-out

Status: Accepted — 2026-08-23

## Context

Tutors need to understand whether an integration supplies lesson information,
receives actions, or does both. A fixed “input device” versus “output device”
taxonomy is inaccurate for glasses, agents, robots, drones, LEGO hubs, and
smart plugs. Lessons also need one semantic cue to reach several independently
controlled outputs without creating another direct device-to-device program.

## Decision

For a registered node, I/O direction is derived from the canonical capability
lists: published capabilities make it an input, consumed capabilities make it
an output, and non-empty lists on both sides make it bidirectional. This is the
runtime source of truth. The integration catalog declares the same three-way
`ioType` only for setup and discovery before a concrete node is online. A
connected node's advertised capabilities always take precedence over the
catalog declaration; for example, a sensor-only LEGO configuration is shown as
input-only even though the LEGO integration type can support both directions.
Course role requirements may also declare `ioType` to group the jobs a tutor is
assigning. That describes the role within one lesson, while the connected
node's capabilities describe the device itself. Legacy course packs may omit
the additive field and remain valid.

Declarative flow recipes may opt into a named `parallelGroup`. When one event
matches several enabled flows in the same group, the Fabric creates one normal
command request per flow and dispatches them concurrently. It does not create a
compound vendor command. Every request keeps its own target role, action,
idempotency key, TTL, schema and capability validation, arbitration lease,
safety decision, lifecycle result, and adapter-level bounds. Missing optional
role bindings are skipped. A rejection or unavailable output is reported for
that output and does not erase the other outputs' results.

The reference `simultaneous-device-cue` course assigns up to four
Leap/R1/G2/Meta inputs, eight ground-mobility outputs, two text outputs, and the
optional bounded Tello fleet controller. Ground roles are capability-based, so
RoboMaster, Sphero, Dash, and a mobile LEGO hub can be selected without changing
the flow. Flight uses only
`mobility.flight.fleet_sequence.start` after its separate instructor arm and
aircraft checklist. The Fabric still exposes no general Tello takeoff command.

“Parallel” means concurrent best-effort dispatch on the local runtime, not
atomic execution or hard-real-time clock synchronization across vendors. Each
device begins when its adapter accepts its independently authorized command.

## Consequences

- Discovery, connected-device status, and lesson setup use the same plain
  Input only / Input + output / Output only vocabulary.
- A new output is added to a fan-out recipe as another target flow rather than
  by modifying the input adapter or orchestration routing code.
- Failures remain attributable to exact command and target lifecycles.
- Device-specific latency can produce small start-time differences, which must
  be measured in hardware-in-the-loop tests when a lesson needs tighter timing.
- A cross-output rollback is not implied. Emergency stop and adapter safe-state
  behavior remain the recovery mechanisms for physical outputs.
