# Migration Plan

Status: reconciled strangler plan as of 2026-08-21. Existing working paths remain available until their replacement slice passes end to end.

## Reconciliation checkpoint

| Phase                   | State                                   | Evidence / remaining gate                                                                                                                |
| ----------------------- | --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| A — inventory           | Complete                                | Required architecture documents and external integration scan retained                                                                   |
| B — contracts           | Complete for the reference slice        | Generated Python/TypeScript Fabric and adapter contracts; legacy fixtures remain valid                                                   |
| C — runtime/API         | Complete as a standalone service        | Scoped auth, SQLite, flow/lifecycle, adapter WebSocket, fail-closed physical default                                                     |
| D — glasses/agents      | Software-complete in compatibility mode | Agent Mesh bridge and durable no-duplicate tests; owner G2/Meta hardware round trip pending                                              |
| E — P0 console          | Complete for Fabric operations          | Same-origin guided `/fabric` route, launcher-assisted sign-in, nodes/roles/sessions/safety/stop/lifecycle/audit                          |
| F — ground robot        | Software wrapper complete; HIL pending  | Pinned Leap/S1 workers, canonical flow, dual bounds, UI/launcher, and dry-run evidence; LEGO Fabric substitution and physical HIL remain |
| G — remaining/hardening | Smart-plug software slice complete      | Tuya-LAN adapter/simulator/UI/launcher complete; all physical, network-loss, multi-host, privacy, and performance evidence remains       |

## Phase A — Baseline and inventory

Deliverables:

- current-state, integration-matrix, target-state, migration-plan, risk-register, and ADR documents;
- clean, repeatable baseline gates for each reusable repository;
- characterization fixtures for Agent Mesh glasses prompt/completion behavior;
- explicit hardware and licence gaps.

Exit gate: no production behavior has been rewritten, and every proposed wrapper identifies its current public/process boundary and rollback path.

## Phase B — Core Fabric contracts

Deliver additively in `CITPhysicalXR`:

- versioned plugin, node, capability, health, event, command-lifecycle, interaction-session, role-binding, course-pack, flow, and adapter-wire schemas;
- generated Python and TypeScript models;
- SQLite migrations for plugins, nodes, capabilities, Fabric sessions, role bindings, semantic messages, command lifecycle, identities/tokens, and audit;
- strict schema and compatibility tests;
- authenticated out-of-process adapter frames and fixtures.

Exit gate: an unknown plugin can register without a core code edit; legacy protocol v1 fixtures remain valid.

Rollback: stop the standalone Fabric process and retain the upstream classroom runtime, Studio, LEGO, and simulation paths unchanged.

## Phase C — Runtime and authenticated API

Deliver:

- plugin/node/capability/health registries;
- course-pack loader and explicit role assignment;
- deterministic first-subset flow engine;
- role target selection, priority/lease arbitration, and lifecycle trace;
- scoped hashed CIT token authority and deny-by-default Fabric routers;
- authenticated adapter WebSocket with origin/identity, heartbeat, size, rate, and lease enforcement;
- semantic recorder and dry-run replay.

Exit gate: simulator nodes can register through both in-process and wire paths, an instructor can assign roles, one event deterministically creates one correlated command, duplicates execute once, and emergency stop wins.

Rollback: stop the Fabric listener; no physical adapter has been enabled and the upstream Milestone 6 runtime remains usable.

## Phase D — Glasses and coding-agent reference slice

Current checkpoint: compatibility mirror implemented and characterized on top of `b74bb2b`; native target-selection cutover and physical glasses evidence remain pending.

In `glasses2CLI`, add opt-in Fabric configuration and preserve default legacy behavior:

1. G2/Meta preserves its existing prompt dispatch and records a canonical intent with one durable identity and expiry.
2. The existing Agent Mesh Hub exposes a least-authority Fabric service outbox/API.
3. `apps/agent-mesh-bridge` registers G2, Meta, and existing Agent Mesh session nodes in CIT.
4. The bridge acknowledges intents only after CIT durably accepts them.
5. CIT resolves `coding_agent` from the active lesson role and emits `agent.prompt.submit`.
6. In compatibility mode, the bridge proves that the role and prompt match the already-dispatched Agent Mesh operation, then reports success without a second invocation. A mismatch fails closed.
7. Normalized Agent Mesh status/output/completion becomes Fabric semantic events.
8. CIT routes display output to assigned roles; the bridge confirms the correlated existing Agent Mesh projection without a duplicate display.

Exit gate:

- compatibility gate: Codex and Claude nodes are independently discoverable and exact-session role binding is enforced;
- G2 and Meta simulators both complete the path;
- prompt and output share correlation/causation IDs;
- bridge restart replays durable semantic events and lifecycle reports;
- no agent/vendor SDK is imported into CIT;
- legacy mode still passes its existing tests.

Native-cutover exit gate (pending): role assignment can select Codex or Claude before the one and only prompt dispatch, with a cross-system idempotency key and cancellation recovery.

Rollback: omit Agent Mesh's `--cit-fabric-bridge-device` option and stop the bridge process; no schema/data migration removes legacy notification state.

## Phase E — P0 instructor console (software complete)

Deliver the same-origin console with:

- login/token exchange, logout, expiry, and visible actor/scope;
- node, health, connection, battery/telemetry summaries;
- course selection and exact role assignment;
- session start/stop, arm/disarm, local stop-all;
- input/output tests and simulator selection;
- live signal, command lifecycle, active lease, safety state, agent status, errors, and disconnects.

Exit gate: every mutation is scoped, audited, protected from cross-origin use, and unavailable to observer/student roles where prohibited. The browser retains no bearer after refresh.

Rollback: serve the existing simulator lab route and disable the `/fabric` console entry.

## Phase F — Ground robot slice

The selected Leap and RoboMaster checkout is now wrapped as independent nodes at
revision `3c213c1...`. `interaction.gesture.velocity` resolves through the
declarative `gesture-ground-robot` flow to
`mobility.ground.set_velocity`. Fabric and the external worker both validate
bounds; the upstream 200 ms stale watchdog, Fabric exclusive lease, instructor
emergency stop, disconnect disarm, simulator, UI, and launcher are present.

Remaining Phase F work is to expose the existing LEGO Pybricks adapter through
the same canonical Fabric capability, run real Leap/S1 and LEGO HIL, and record
local p95 latency. Software-only evidence must not be reported as physical.

No upstream implementation source is copied into the core. The owner authorized
the external private/noncommercial wrapper. Physical movement remains behind a
separately enabled local Fabric, explicit arm/start, and the hardware checklist.

## Phase G — Remaining integrations and hardening

- Wrap MindWave and Tello from Brain2Devices as separate processes.
- Complete the approved LEGO transport/licensing split.
- Run the implemented TinyTuya LAN adapter against each approved Tuya or
  compatible Gosund model; record exact model, firmware, DPS, loss behavior,
  and safe-off evidence before classroom use.
- Add multimodal state windows after calibration semantics stabilize.
- Integrate Tello only after simulator, ground robot, console, and safety evidence pass.
- Run Windows/Linux, multi-host, crash, network-loss, restart, privacy, security, performance, and hardware-in-loop gates.

## Change discipline

- Preserve external repository working trees and do not bulk-move files.
- Keep schema/runtime/console/bridge changes reviewable as separate checkpoints and preserve the pre-reconciliation snapshot branch until acceptance.
- Add characterization or contract tests before modifying an existing behavior.
- Prefer wrappers, then compatibility layers, then tested internal refactors; rewrite only with documented evidence.
- Record unresolved hardware, licensing, or semantic assumptions in the risk register and ADRs.
