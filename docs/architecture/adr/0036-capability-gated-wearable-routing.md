# ADR 0036: Capability-gated wearable routing

- Status: accepted
- Date: 2026-09-06

## Context

Wearable control had three competing descriptions of the same classroom: the
course pack declared Fabric routes, Agent Mesh inferred actions from role-name
patterns, and the G2 client expanded group requests into exact-role commands.
Meta implemented a smaller phrase set. This drift excluded light-only robots
such as Dot, made new numbered output families require UI code changes, and
left safe **Stop all** behavior dependent on the client that originated it.

The Tello fleet creates a separate constraint. A stock aircraft in access-point
mode owns its Wi-Fi network. Switching one radio between airborne aircraft
would discard the stable command and telemetry route needed to land the
previous aircraft safely.

## Decision

The installed, exact-version course pack is the single source of wearable
device routing. A flow target is one of three closed forms:

- one static lesson role;
- a bounded explicit list of lesson roles; or
- one role selected from an explicit allowlist by a structured payload field.

Every candidate must be a declared output role and must appear in the flow's
`outputRoles`. Dynamic targets may name a `requiredCapability`, which must equal
the command action. At runtime, a request resolves only through the active
session's role bindings. Group members whose live node does not consume the
required output capability are skipped; payload-selected roles outside the
course allowlist are rejected. Browser or wearable input can never supply an
arbitrary node ID.

The Agent Mesh bridge reads the active session, scoped nodes, and the matching
installed course pack. It derives each assigned output's actions from enabled
device-control flows and the node's consumed capability descriptors. Role-name
patterns do not define device behavior. G2 menus and both G2 and Meta voice
publish one canonical group or exact-role event. In particular,
`{ target: all_outputs, action: stop }` is one safe-state event; the course pack
maps it to capability-gated robot stop, fleet landing, and smart-plug off
commands. Each resulting command still receives its own authorization,
arbitration, lifecycle, idempotency, and adapter validation. A flight-start
route is exposed only when the same fleet controller also supports landing.
Course role requirements encode that start/stop pairing as an
`allOfCapabilities` gate.

Numbered lesson banks use the generic `<family>_<positive integer>` convention
for deterministic tutor defaults. This convention is presentation-only; it
does not grant capabilities or routing authority.

The Tello fleet remains one independently armed fleet-controller role. The
controller validates aircraft and issues takeoff or landing to one aircraft at
a time, confirming state before advancing. Simultaneous stock Tellos require a
stable interface/route per aircraft; station-mode EDU/RoboMaster TT aircraft
may instead use stable unique addresses on one LAN. One radio may be switched
between aircraft only for grounded, non-flight setup checks. It is never used
as an airborne fleet handoff.

## Consequences

- Course pack `glasses-device-control` version 1.3.0 replaces 125 duplicated
  routes with bounded group and payload-selected recipes.
- A light-only Dot can occupy a ground output, appears with only **Light**, and
  is skipped for movement or demonstration commands it cannot consume.
- G2 and Meta support matching group commands plus exact numbered robot and
  smart-plug commands in English and Korean.
- Adding a compatible output normally requires capability publication and a
  course role/flow update, not new bridge role regexes or client fan-out code.
- The bridge's scoped read identity now includes `fabric.course.read`; launcher
  credential version 2 rotates older identities that lack it.
- The three **Stop all** recipes share one parallel group, so ground stop,
  fleet landing, and smart-plug off are dispatched without serially delaying
  one safe-state domain behind another.
- Inventory projection fails closed unless the bridge can load the exact course
  ID and version named by the active session. Existing sessions must be moved
  to `glasses-device-control` 1.3.0 before the new routes appear.
- Physical G2, Meta, robot, plug, and multi-Tello behavior remains subject to
  the owner hardware acceptance checks; automated tests prove only the schema,
  projection, parser, routing, and simulator boundaries.
