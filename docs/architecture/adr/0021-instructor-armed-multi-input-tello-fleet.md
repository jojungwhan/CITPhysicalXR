# 0021 — Instructor-armed multi-input Tello fleet sequence

Status: Accepted — 2026-08-23

## Context

Tutors need one classroom control to launch several Tellos in a chosen order.
The same one-shot plan may be triggered by the tutor button, a deliberate Leap
open-hand-to-pinch transition, or an exact voice phrase from G2 or Meta glasses.
Per-aircraft Tello nodes intentionally expose no takeoff or movement capability,
and glasses/Leap launchers previously created separate sessions whose events
could not safely reach the drone lesson.

## Decision

Use a separate out-of-process plugin, `cit.brain2devices-fleet`, for the ordered
workflow. It consumes only arm, start, and stop; publishes semantic status; and
does not advertise raw takeoff, move, or rotate. Arm is instructor-only and
records an ordered list of one to eight independently routed aircraft, approved
input node IDs, a bounded interval and battery floor, plus four explicit safety
contract fields. The console obtains those fields from one combined, unchecked
tutor attestation and preselects connected aircraft and approved trigger inputs.
Its prepare action also starts and arms the enclosing session. Start consumes
that arm exactly once. The controller also expires
an unused arm after 60 seconds independently of the enclosing lesson session.

For each selected aircraft the controller revalidates landed state and battery,
requests one takeoff through the loopback-only Brain2Devices boundary, waits for
that exact aircraft to report flying, and only then waits the configured spacing
before advancing. Failure, cancellation, adapter shutdown, and tutor stop end
the sequence and request landing for every confirmed or possibly launched
aircraft.

Leap and Agent Mesh wearable adapters publish
`interaction.intent.flight_sequence_start`. The declarative monitoring recipe
maps only `{ "intent": "start" }` with confidence, debounce, role, connection,
arm, and instructor-override guards. Exact G2/Meta phrases are deterministic;
raw transcript text is not copied into this operational event. A trigger cannot
arm the plan.

The Windows Connect actions attach Leap or G2/Meta as input-only nodes to the
existing fleet monitoring session. They do not start RoboMaster, select a coding
agent, or stop the shared session when the input bridge exits.

An unarmed monitoring session may contain an enabled flow only when its target
role is optional and every deterministic dormant-flow guard is present:
`session_is_active`, `role_is_assigned`, `target_is_connected`,
`target_is_armed`, and `instructor_override_is_clear`. All bound monitoring
roles must remain informational. The normal command gate independently rejects
physical non-safe-state commands until the session is armed.

## Consequences

- The tutor page provides default aircraft/input selection, launch order,
  interval, battery floor, one physical confirmation, one-click session
  preparation and one-shot arm, start, and stop/land.
- Button, Leap, R1, G2, and Meta converge on one command contract and correlation
  path while remaining independent adapter processes.
- Simulators and replay can validate semantics without aircraft; replay remains
  dry-run.
- Physical fleet use requires one stable network route per aircraft. Stock
  access-point-mode Tellos therefore require separate Wi-Fi adapters or another
  explicitly validated independent-routing arrangement.
- Physical multi-aircraft flight, network-loss behavior, and device-specific
  latency still require controlled hardware-in-the-loop evidence.
- Agent Mesh currently publishes mirrored wearable intents after its existing
  coding-agent dispatch. The exact fleet phrase can therefore also reach the
  wearable's selected agent session, but that agent has no fleet capability or
  authority; a native pre-dispatch wearable-intent route remains follow-up work.
