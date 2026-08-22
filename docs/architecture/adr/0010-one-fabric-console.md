# ADR-0010: Use one capability-driven Fabric console for all integration nodes

- Status: accepted
- Date: 2026-08-21

## Context

The first hardware launchers each started a private Fabric instance. Their
contracts were common, but glasses/agents on port 8766 and Leap/RoboMaster on
port 8767 could not be observed or assigned from one screen. Adding another
device-specific UI would recreate the pairwise architecture the Fabric is
intended to remove.

## Decision

Windows hardware operation uses one shared Fabric host and the same-origin
`/fabric` console. Component launchers attach through the existing
transport-neutral adapter contract and own only their adapter processes,
credentials, and sessions.

The console derives I/O presentation from capabilities rather than plugin or
model names:

- published capabilities make a node an input to the Fabric;
- consumed capabilities make a node an output from the Fabric;
- nodes with both are bidirectional.

The UI displays all registered nodes and their full publish/consume capability
lists. It does not maintain a hardcoded device catalog. Logical role assignment,
site/room scope, arbitration, safety, and emergency stop remain core services.

## Consequences

New adapters automatically appear in the one console without UI routing
changes. Stopping a component cannot terminate other adapters or the shared
Fabric; stopping the shared host intentionally performs the global safety stop.
Standalone component-owned Fabric startup remains temporarily available for
backward compatibility, but the documented multi-device path uses the shared
launcher. Physical dispatch remains an explicit process-level opt-in and does
not arm any session automatically.
