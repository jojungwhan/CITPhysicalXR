# ADR 0018 — Independent device adapters and exact external-source pins

- Status: Superseded in part by ADR-0020 and ADR-0022
- Date: 2026-08-22

## Context

Brain2Devices implements both MindWave Mobile 2 and Tello behavior, while the
selected RoboMaster repository implements both Leap input and S1 output. Running
either pair as one permanent integration would couple lifecycle, credentials,
capabilities, failure domains, and future upgrades. Repeating capability names,
course definitions, and source revisions across adapters and launchers would
also create drift.

Existing vendor implementations are working assets and must be wrapped, not
silently rewritten or imported into the orchestration core.

## Decision

- Run Tello, MindWave, Leap, RoboMaster, LEGO, Matter, and legacy Tuya as
  separately registered plugin/node processes with separately scoped adapter
  credentials and process supervision.
- Keep vendor SDK imports inside their adapter or external child process.
- Use `packages/integration-sdk-py` only for transport-neutral registration,
  heartbeat, event, lifecycle, sequence, bounded replay, and exact-clean-source
  verification mechanics. Device policy, parsing, bounds, and safe-state
  behavior remain in each adapter.
- Use the SDK's bounded command-result replay cache for stable adapter-level
  idempotency semantics; adapters must not retain command identifiers forever.
- Maintain capabilities, integration discovery presentation, course YAML, and
  external repositories/revisions in canonical configuration sources and
  generate runtime-specific resources from them.
- Pin Brain2Devices at
  `f20a58cbcfb9f6181ca5a4742bf646541f5dc97e` and RoboMaster gesture control at
  `3c213c110b0cdf2912985bfcde442d67092b98f0`. Installers and launchers fail
  closed on source drift and never overwrite dirty external worktrees.
- Reuse Brain2Devices' hardware ports and blink callback, but do not expose its
  optional automatic EEG-to-flight demo trigger. Flight activation remains a
  separate deterministic CIT safety decision.
- Preserve compatibility launch modes where a working upstream service already
  owns the hardware connection; add direct port wrappers without forcing an
  upstream rewrite.
- Permit a physical session to start unarmed only for a no-flow monitoring pack
  whose bound role requirements are informational. This does not bypass the
  command gate; only declared safe-state actions such as Tello land/emergency
  remain eligible.
- Let independently launched informational adapters join one shared monitoring
  session through optional, capability-checked role slots. Active control
  sessions remain immutable, and the monitoring session remains unarmed.

## Consequences

- One device adapter can fail or restart without terminating its paired input or
  output integration.
- A new adapter consumes generated contracts without editing core routing code.
- Matter and legacy Tuya reuse the same Fabric wire client as Tello, MindWave,
  and LEGO while retaining independent device policy and vendor transports.
- External upgrades are explicit changes to one source catalog followed by
  regeneration, characterization, and review.
- Tello intentionally exposes no takeoff/movement and MindWave exposes no raw
  EEG. Expanding either is a new capability/safety decision, not a vendor-text
  passthrough.
- Tutors see concurrent Tello, MindWave, and LEGO telemetry in one session even
  though every adapter retains its own process, credential, and failure domain.
- There are more small processes and scoped credentials to supervise; the shared
  launcher and one tutor UI hide that operational detail.
