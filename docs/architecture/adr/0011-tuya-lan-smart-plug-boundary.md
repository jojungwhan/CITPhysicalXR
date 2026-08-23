# ADR-0011: Expose smart plugs through one exact local-LAN boolean capability

- Status: superseded by ADR-0022
- Date: 2026-08-21

## Context

The repository scan found no existing Tuya or Gosund implementation to wrap.
Smart-plug brands and models vary in protocol version and datapoint mapping;
exposing arbitrary vendor datapoints would create an electrical command escape
hatch. Vendor cloud control would also put internet availability and cloud
credentials into a classroom control path.

## Decision

The first smart-plug adapter uses pinned TinyTuya 1.20.0 for an exact private
LAN address. It registers one bidirectional node with only:

- `power.switch.set` with exactly `{ "on": boolean }`;
- `power.switch.state` with normalized verified state.

The capability is classified `electrical`. Physical on requires an explicitly
enabled Fabric, physical session, arm, and active state. Off is a deterministic
safe-state command that remains available while disarmed or inactive. The
adapter repeats boolean/DPS validation, suppresses duplicate command IDs,
verifies state after a write, polls for external changes, and attempts off on
startup, Fabric stop/disconnect, and shutdown.

Device ID and local key enter only the adapter process environment from a
current-user DPAPI ciphertext. They do not appear in manifests, node metadata,
events, commands, logs, or course packs. The adapter never scans, uses the Tuya
cloud, or accepts arbitrary DPS writes.

`gosund` is descriptive metadata only. A Gosund model is compatible only after
the exact unit passes the same Tuya-LAN read-only probe and hardware checklist.

## Consequences

The simulator and course/UI path work without hardware. Real deployment needs
an exact local key and per-model protocol/DPS evidence. If Wi-Fi to an already-on
plug is unavailable, software cannot guarantee delivery of off; only approved
nonessential loads may be used, and that behavior remains a physical HIL gate.
