# Protocol Foundation

## Source of truth

`packages/protocol-schema/schemas/cit-protocol.schema.json` is the Draft 2020-12 source of truth for protocol major version 1. It defines:

- `CitEnvelope`
- `SafetyContext`
- `DeviceCommandIntent`
- `DeviceEvent`
- `DeviceDescriptor`
- `CommandResult`
- `ProtocolError`

Identifiers are bounded and pattern-validated. Commands always carry an exact `deviceId`, session, issued/expiry times, idempotency key, source, and safety context. Unknown fields are rejected on safety-relevant objects.

## Generation

`pnpm generate` deterministically regenerates TypeScript declarations/schema exports and Python Pydantic models. `pnpm generate:check` regenerates into a temporary directory and fails on committed drift. Generated files are not edited by hand.

Shared JSON fixtures are accepted by both Ajv/TypeScript and jsonschema/Pydantic tests. The validators also prove rejection of an unknown protocol major version and a command missing exact device identity.

## Authority

A schema-valid command is only an intent. Validation does not arm a device, acquire a lease, authorize movement, or dispatch anything. Those responsibilities remain below callers in the local runtime and safety supervisor planned for Milestone 1.
