# ADR 0003: Strangler migration and wrapper-first reuse

- Status: Accepted
- Date: 2026-08-21

## Context

Working G2, Meta, Codex, Claude, MindWave, Tello, Leap, and RoboMaster behavior exists across repositories. Several repositories are private or have no top-level licence, and they use different runtimes.

## Decision

Preserve existing implementations behind characterized process/API boundaries. Use, in order: unchanged wrapper, thin schema compatibility layer, shared utility extraction after stable duplication, protected internal refactor, and rewrite only with documented evidence that a safe wrapper is impossible.

## Consequences

- Fabric mode is additive and opt-in until end-to-end acceptance.
- Source is not copied across incompatible licence boundaries.
- Temporary dual paths and compatibility shims are expected.
- Rollback is configuration-based rather than a large source revert.
