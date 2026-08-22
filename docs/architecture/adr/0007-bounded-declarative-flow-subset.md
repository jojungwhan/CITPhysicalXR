# ADR 0007: Begin with a bounded declarative flow subset

- Status: Accepted
- Date: 2026-08-21

## Context

Courses need reusable mappings, but a general expression language or visual editor before stable contracts would create an arbitrary-code surface and premature abstraction.

## Decision

The first flow engine accepts version-controlled YAML/JSON recipes with strict schema validation and an allowlisted deterministic operator set: event/intent match, confidence, TTL, debounce, fixed/bounded parameter mapping, role target, simple guards, and typed actions. It has no `eval`, shell, dynamic module, templated code, or network operator.

## Consequences

- Unsupported recipes fail visibly instead of falling through to vendor logic.
- Course packs remain reviewable and portable.
- Stateful sequences, fusion, timers, parallelism, and a visual editor are added only after their semantics and safety tests are stable.
