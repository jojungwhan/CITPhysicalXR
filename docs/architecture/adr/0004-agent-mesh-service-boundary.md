# ADR 0004: Agent Mesh remains the coding-agent authority

- Status: Accepted
- Date: 2026-08-21

## Context

Agent Mesh already normalizes Codex and Claude sessions and owns workspace validation, process isolation, prompt delivery, approvals, durable commands, output minimization, and glasses clients. Reimplementing those responsibilities in CIT would duplicate security-sensitive code and cross a licence boundary.

## Decision

Integrate through a dedicated bridge with least-authority identities on both systems. A Fabric `coding_agent` role binds an existing Agent Mesh managed or observed session node. CIT may submit a typed prompt/cancel request and consume normalized status/output, but Agent Mesh remains authoritative for workspace, process, tool, and approval policy.

## Consequences

- Glasses code does not select Codex versus Claude in Fabric mode.
- CIT never imports vendor CLI adapters or receives vendor credentials/raw frames.
- Cross-system idempotency, version negotiation, and correlation become required contract tests.
- Bridge loss degrades agent interaction without affecting local physical safety.
