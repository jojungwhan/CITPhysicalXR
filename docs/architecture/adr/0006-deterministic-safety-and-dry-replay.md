# ADR 0006: Deterministic safety precedes every physical dispatch

- Status: Accepted
- Date: 2026-08-21

## Context

Inputs include noisy sensors and LLM-generated proposals; outputs include motors, flight, and electrical power. Durable messaging and replay can repeat effects.

## Decision

Every physical request passes schema, capability, session authorization, arbitration, deterministic safety, adapter validation, execution, and result monitoring. Emergency stop is locally handled and highest priority. LLM text and flow data are never evaluated as code. Movement commands have short TTLs, idempotency, exclusive leases, rate/bound limits, local watchdogs, and no replayable durable dispatch queue. Semantic replay is dry-run by default.

## Consequences

- An adapter repeats device-level bounds even after core authorization.
- Some availability is intentionally sacrificed to fail closed.
- Drone support waits for proven lower-risk safety, simulation, and instructor controls.
- Command trace records decisions and outcomes but is not itself an instruction to re-execute hardware.
