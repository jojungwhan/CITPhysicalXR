# ADR 0035: Canonical turn-on-all demonstration

- Status: accepted
- Date: 2026-08-26

## Context

The G2 controls package previously treated **Activate all** as a local menu
shortcut. It expanded robot and drone commands inside the glasses client and
deliberately omitted smart plugs. Meta could not request the same demonstration,
and changing its meaning required duplicating orchestration rules across clients.

CIT needs one tutor-confirmed demonstration that visibly activates every
assigned output type: supported robot LEDs and bounded movement, local Matter
plug power, and an already-prepared Tello fleet.

## Decision

Wearables publish one allowlisted `interaction.intent.device_control` event with
`target: all_outputs`, `action: activate`, and `confirmed: true`. The
`glasses-device-control` course pack is the single source of fan-out behavior.
Its named parallel flow group maps that event to:

- cyan LEDs where `robot.light.set` is available;
- a preemptible 0.1 m ground-robot demonstration;
- `power.switch.set` with `on: true` for assigned smart plugs; and
- `mobility.flight.fleet_sequence.start` for the assigned fleet controller.

Every generated command retains its own role, capability validation,
arbitration, safety decision, idempotency key, lifecycle, and adapter bounds.
Missing optional roles and unsupported LED capabilities fail independently. The
action does not arm a lesson or a Tello fleet. **Stop all** remains an immediate
client expansion to robot stop, fleet land, and plug Off commands.

The course schema already permits up to 128 validated flows. Course packs alone
therefore receive a 128 KiB persistence ceiling; all other Fabric records retain
the 64 KiB ceiling. This keeps the storage contract aligned with the schema
without relaxing event, command, identity, node, or lifecycle limits.

## Consequences

- G2 menu/voice and Meta voice use the same canonical action and course recipe.
- The smart-plug behavior is explicit in the reviewed demonstration instead of
  being a hidden side effect of a robot-only client shortcut.
- The exact phrases **CIT turn on all devices** and **CIT 모든 장치 켜기** require
  confirmation before the Fabric accepts the intent.
- A physical output still acts only when its existing session, assignment,
  connection, arming, policy, and adapter checks pass.
- Course pack version 1.2 replaces earlier glasses-control sessions for this
  behavior.
