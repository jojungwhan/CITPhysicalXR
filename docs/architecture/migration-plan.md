# Migration Plan

Status: reconciled strangler plan as of 2026-08-23. Existing working paths remain available until their replacement slice passes end to end.

## Reconciliation checkpoint

| Phase                   | State                                                 | Evidence / remaining gate                                                                                                                                     |
| ----------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A — inventory           | Complete                                              | Required architecture documents and external integration scan retained                                                                                        |
| B — contracts           | Complete for the reference slice                      | Generated Python/TypeScript Fabric and adapter contracts; legacy fixtures remain valid                                                                        |
| C — runtime/API         | Complete as a standalone service                      | Scoped auth, SQLite, flow/lifecycle, adapter WebSocket, fail-closed physical default                                                                          |
| D — glasses/agents      | Software-complete in compatibility mode               | Agent Mesh bridge and durable no-duplicate tests; owner G2/Meta hardware round trip pending                                                                   |
| E — P0 console          | Complete for Fabric operations                        | Same-origin five-stage `/fabric` route, launcher sign-in, safe host discovery, nodes/roles/sessions/safety/stop/lifecycle/audit                               |
| F — ground robot        | Software wrappers complete; HIL pending               | Separate pinned Leap/S1 processes plus canonical LEGO bridge, role substitution, dual bounds, UI/launchers, and simulated evidence                            |
| G — media/sensors       | UI and Meta live-frame software complete              | Ephemeral authenticated wall, local reviewed YOLO, sensor cards, DAT 0.9.0/MockDeviceKit live video with snapshot fallback; physical HIL pending              |
| H — remaining/hardening | Device software slices complete; physical HIL pending | Matter, exact-pinned Brain Tello/MindWave adapters, bounded multi-input Tello fleet, installer, catalogs, and shared SDK; clean-machine/hardware gates remain |

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
- read-only host candidate discovery with explicit found/ready/setup/connected
  states, no browser/device credential input, and audited allowlisted connection
  actions.

Exit gate: every mutation is scoped, audited, protected from cross-origin use, and unavailable to observer/student roles where prohibited. The browser retains no bearer after refresh.

Rollback: serve the existing simulator lab route and disable the `/fabric` console entry.

## Phase F — Ground robot slice

The selected Leap and RoboMaster checkout is now wrapped as independent nodes at
revision `3c213c1...`. `interaction.gesture.velocity` resolves through the
declarative `gesture-ground-robot` flow to
`mobility.ground.set_velocity`. Fabric and the external worker both validate
bounds; the upstream 200 ms stale watchdog, Fabric exclusive lease, instructor
emergency stop, disconnect disarm, simulator, UI, and launcher are present.

The existing LEGO Pybricks adapter is now exposed through a separate canonical
Fabric bridge. It publishes sensor/battery state for any configured hub and
advertises the same ground capability only when two motors are present. The
remaining Phase F work is real Leap/S1 and LEGO HIL plus local p95 latency.
Software-only evidence must not be reported as physical.

No upstream implementation source is copied into the core. The owner authorized
the external private/noncommercial wrapper. Physical movement remains behind a
separately enabled local Fabric, explicit arm/start, and the hardware checklist.

## Phase G — Camera and sensor presentation

Implemented:

- authenticated in-memory latest-frame sources, scoped one-use phone pairing,
  camera wall, freshness state, ETag polling, and restart erasure;
- optional Meta DAT Android live-frame source inside the existing glasses
  companion, bounded to 2 FPS, with explicit phone permission/share controls,
  a manual snapshot fallback, and no background capture;
- fixed local YOLO-World model preparation, bounded labels, tutor-triggered
  inference, overlays, and a separate reviewed smart-plug action restricted to
  switchable-load labels;
- normalized scalar sensor cards for LEGO, robot, biosignal, and telemetry
  events.

The optional APK compiles and builds against the official DAT 0.9.0 artifacts,
and the official MockDeviceKit produces a frame accepted by the strict I420
converter on an Android 16 emulator.
Tello's Brain2Devices MJPEG feed now has a scoped latest-frame publisher and
simulator. Remaining gates are technician package credentials for repeatable
Meta installation and real glasses HIL, the RoboMaster camera publisher,
physical Tello video/firewall evidence, physical LEGO bridge HIL, and
multi-camera performance/privacy evidence. A
contract-supported source kind is not physical-completion evidence.

## Phase H — Remaining integrations and hardening

- Run the implemented independent MindWave and Tello adapters against physical
  hardware at exact Brain2Devices revision `536a256...`. Tello intentionally
  remains a telemetry/land/emergency slice, not a general flight-control slice.
  Validate the separately bounded one-shot demo node and ephemeral Tello video
  using the documented instructor, flight-area, cancellation, firewall, and
  rapid-handoff checks.
- Validate the separate two-to-eight-aircraft fleet controller with one stable
  route per Tello, exact ordered airborne confirmation, cancel/land on partial
  failure, and each tutor/Leap/G2/Meta trigger. The three-drone process and real
  browser simulation are complete; physical fleet evidence is not.
- Validate the implemented LEGO Fabric/Pybricks bridge on each approved hub and
  record the optional transport's distribution/licence decision separately.
- Commission each approved Matter model through a clean Windows 11 business
  install; record firmware, Bluetooth/Wi-Fi behavior, restart/network-loss,
  verified state, and safe-off evidence.
- Add multimodal state windows after calibration semantics stabilize.
- Add any generic Tello takeoff or movement only under a new drone safety ADR;
  ADRs 0020 and 0021 authorize only their exact bounded one-shot workflows.
- Run Windows/Linux, multi-host, crash, network-loss, restart, privacy, security, performance, and hardware-in-loop gates.

## Change discipline

- Preserve external repository working trees and do not bulk-move files.
- Keep schema/runtime/console/bridge changes reviewable as separate checkpoints and preserve the pre-reconciliation snapshot branch until acceptance.
- Add characterization or contract tests before modifying an existing behavior.
- Prefer wrappers, then compatibility layers, then tested internal refactors; rewrite only with documented evidence.
- Record unresolved hardware, licensing, or semantic assumptions in the risk register and ADRs.
