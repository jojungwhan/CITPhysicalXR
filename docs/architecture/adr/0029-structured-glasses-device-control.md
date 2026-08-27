# ADR 0029: Structured glasses device control

- Status: superseded in part by ADR 0035
- Date: 2026-08-24

## Context

G2 voice originally routed RoboMaster commands through an Agent Mesh-specific
relay, while other phrases were first dispatched to a coding agent and only
then mirrored into the Fabric. Meta voice also required an agent session. That
split path could not safely or portably control Sphero, LEGO, Dash, and Tello.
It also made device control depend on Codex or Claude.

Ground robots expose different kinematics. Sphero and RoboMaster can translate
laterally, while LEGO and Dash use differential turning. Sending one raw
velocity tuple to every model does not preserve the meaning of “left”.

## Decision

G2 and Meta publish an explicitly confirmed
interaction.intent.device_control event through the existing durable Agent Mesh
interaction feed. The event contains only an allowlisted action, logical target,
device kind, and confirmation flag; it does not contain the raw transcript.

The parser is deterministic, exact, bilingual, and requires the CIT wake word.
Movement and takeoff require a second glasses press or tap. Stop and land are
explicit safe-state utterances and are submitted immediately.

Ground movement uses mobility.ground.nudge with forward, backward, left, right,
or stop. Sphero, RoboMaster, LEGO, and Dash advertise that capability and
translate it inside their independent adapters. Existing low-level velocity and
stop capabilities remain available.

Tello uses the existing fleet start/stop capabilities. No glasses or LLM path
can bypass the fleet controller's tutor checklist, one-shot arm, arbitration,
or local safe-state behavior.

The unified console passes the exact selected physical lesson ID to one
allowlisted glasses-control connection action. The runtime checks the course,
session scope, and role-assignment permission before the launcher receives the
ID. The launcher issues a session-scoped adapter credential and binds only
G2/Meta nodes that advertise the structured device-control capability.

The bridge also uses a separate session-scoped, read-only Fabric credential to
project the current lesson's exact output-role assignments to Agent Mesh. G2
uses that projection for its output menu; it does not browse unrelated rooms or
accept node IDs from the wearer. The menu can select all assigned motion
outputs, all assigned ground robots, the assigned drone fleet, or one exact
ground-output role.

**Activate all** is a G2 presentation action, not a new unrestricted Fabric
command. The plugin expands it into one correlated batch of exact-role actions:
cyan light on robots that advertise `robot.light.set`, a preemptible 10 cm
forward/stop/backward/stop demonstration on robots that advertise
`mobility.ground.demonstration.start`, and takeoff on the assigned fleet
controller. It never arms a session or drone controller. Each expanded command
still passes independently through the normal recipe, arbitration, safety, and
adapter checks. **Stop all** similarly expands to exact robot stops and fleet
landing.

## Consequences

- G2 and Meta can control assigned devices without an agent session.
- One event can fan out concurrently to multiple independently checked outputs.
- Vendor-specific kinematics remain outside the glasses and orchestration core.
- Wearable events cannot silently route into a stale coding-agent or monitoring
  session when a tutor prepares device control.
- Adding another compatible ground robot requires only adapter-level nudge
  translation and contract tests.
- An output appears only with actions its live node advertises; unsupported LED
  or movement operations are not guessed by the G2 client.
- The exact phrase set must be updated in both TypeScript and Android Java with
  matching tests until generated mobile bindings are introduced.
