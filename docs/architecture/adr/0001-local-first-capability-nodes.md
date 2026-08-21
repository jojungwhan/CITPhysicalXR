# ADR 0001: Local-first capability nodes with ports and adapters

- Status: Accepted
- Date: 2026-08-21

## Context

CIT integrations are bidirectional, polyglot, and connected through incompatible vendor transports. Pairwise input-to-output programs scale as N×M and couple lessons to hardware models.

## Decision

Represent every running device, application, simulator, or agent session as an integration node. Nodes advertise versioned published/consumed capabilities and connect through in-process or authenticated out-of-process adapter ports. The local orchestrator owns semantic routing, roles, policy, and trace; vendor SDKs stay inside adapters.

## Consequences

- A lesson targets a capability-bearing logical role rather than a model or address.
- New adapters do not require core routing branches.
- High-rate reduction and emergency behavior remain at the edge.
- Capability compatibility needs explicit units, constraints, latency, and semantic versioning; matching names alone is insufficient.
