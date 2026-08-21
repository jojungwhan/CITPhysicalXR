# ADR 0008: Mirror Agent Mesh behavior before native target-selection cutover

- Status: Accepted
- Date: 2026-08-21

## Context

G2 and Meta already dispatch prompts successfully through Agent Mesh. Redirecting that path through a new orchestrator before cross-system idempotency and cancellation are proven could lose a learner request or execute it twice.

## Decision

The first wrapper is opt-in compatibility mirroring. Agent Mesh performs its unchanged exact-session dispatch, persists a bounded semantic intent, and exposes it to one least-authority bridge identity. Fabric evaluates the course flow, but the bridge reports success only when target session and semantic prompt hash match the already-dispatched operation. It never dispatches that prompt again. A mismatch or Fabric-originated prompt is rejected. Existing completion projection is likewise confirmed without a second glasses notification.

## Consequences

- Existing G2, Meta, Codex, and Claude behavior remains the rollback path.
- The slice proves discovery, contracts, role validation, correlation, durable replay, process isolation, and output routing without changing the one-dispatch invariant.
- Role assignment cannot yet substitute a different agent after glasses input; native cutover requires an Agent Mesh idempotency API and cancellation recovery first.
- Compatibility status and rejection codes remain visible in command lifecycle and audit output.
