# ADR 0002: JSON Schema is the transport-neutral contract source

- Status: Accepted
- Date: 2026-08-21

## Context

Adapters span Python, TypeScript, Java/Android, and future runtimes. Binding the contract to Pydantic, Zod, protobuf RPC, MQTT, or one language would force rewrites or transport coupling.

## Decision

Maintain Draft 2020-12 JSON Schema as the canonical source, versioned independently of HTTP/WebSocket/in-process transport. Generate Python and TypeScript bindings and validate shared fixtures in both runtimes. Keep existing protocol v1 types and add Fabric definitions rather than redefining them incompatibly.

## Consequences

- Wire interoperability is testable without sharing implementation packages.
- Generated files are never hand edited.
- Some semantic checks remain runtime policy because JSON Schema cannot authorize a command or prove device state.
- Schema evolution requires compatibility fixtures and explicit major-version negotiation.
