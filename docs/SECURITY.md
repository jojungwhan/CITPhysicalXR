# Security Foundation

## Milestone 0 posture

No application in this milestone opens a network listener, launches an external adapter, imports a device SDK, or exposes a shell/process-execution API. The bridge scaffold is policy-only. The Quest scaffold is not paired or exported.

Configuration is strict and local-first:

- bind hosts are limited to loopback values;
- committed defaults disable physical devices and Agent Mesh;
- unknown keys and literal credential structures are rejected;
- only secret-store provider/namespace references are representable;
- active local configuration and environment files are ignored by Git;
- Windows and Linux paths remain distinct strings.

Protocol inputs reject unknown fields, invalid identifiers, malformed timestamps, and unsupported major versions. Command expiry, idempotency, exact device identity, lease exclusion, and source denial are separate checks so schema validity cannot imply execution authority.

## Deferred controls

Authenticated localhost IPC, Quest pairing, scoped tokens, origin checks, rate limits, audit persistence, log redaction, secret-store implementation, process isolation, and dependency/security scanning are implemented and reviewed with the runtime or integration milestone that uses them. No public bind or general-purpose execution endpoint is permitted.
