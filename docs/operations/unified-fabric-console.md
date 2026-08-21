# Unified Interaction Fabric console

The supported classroom topology is one local Fabric process and one `/fabric`
UI. Every running adapter registers into that process, so sensors, wearables,
robots, IoT devices, simulators, and coding agents can be assigned and observed
without opening a device-specific console.

Only integrations that are actually connected are shown. The UI does not fake
support for a device whose adapter has not been implemented or started.

## Start the shared console

If a legacy per-integration Fabric is already using port 8766, stop its
component launcher first. This preserves its database while releasing the port:

```powershell
pnpm hardware:glasses:windows -- -Mode Stop
```

Do not kill the Python PID directly; the component launcher also restores its
temporary Agent Mesh changes. Then start the shared host:

```powershell
pnpm hardware:fabric:windows -- -Mode Preflight
pnpm hardware:fabric:windows -- -Mode Start
pnpm hardware:fabric:windows -- -Mode CopyCredential
```

Open <http://127.0.0.1:8766/fabric>, paste the copied credential, select
**Connect locally**, then clear the clipboard:

```powershell
Set-Clipboard -Value ''
```

The credential ciphertext, logs, and shared SQLite state remain under
`%LOCALAPPDATA%\CITPhysicalXR\interaction-fabric`. The plaintext credential is
never printed or stored in the repository.

## Attach integrations

Every component launcher receives the same shared root and port but retains a
separate component state directory:

```powershell
$fabricRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"

# Existing G2/Meta and Codex/Claude bridge
pnpm hardware:glasses:windows -- -Mode Start -SharedFabricRoot $fabricRoot -FabricPort 8766 -SelectMostRecentAgentSession

# Leap and RoboMaster using semantic demo input and the real upstream dry-run robot
pnpm hardware:robot:windows -- -Mode Start -SharedFabricRoot $fabricRoot -FabricPort 8766
```

Refresh the UI. Leap appears under **Inputs**. A robot, glasses endpoint, or
coding agent normally appears under **Bidirectional** because it publishes
telemetry/output and consumes commands. A command-only adapter appears under
**Outputs**. Each card shows its complete **Publishes** and **Consumes** lists.

Site and room scopes still isolate sessions. Create or select the relevant
course pack, assign connected capability-compatible nodes to logical roles,
then start the session. One UI can monitor multiple rooms without allowing one
session to commandeer another room's node.

## Physical devices

Simulation is the default. To run a physical motor adapter, stop the shared
Fabric, restart it with physical dispatch explicitly enabled, and follow that
adapter's hardware runbook:

```powershell
pnpm hardware:fabric:windows -- -Mode Stop
pnpm hardware:fabric:windows -- -Mode Start -AllowPhysical
```

`-AllowPhysical` only enables the policy path. Every physical session remains
disarmed until its explicit arm transition, and the UI emergency stop remains
higher priority than every lesson, student, or agent command.

## Status and shutdown

```powershell
pnpm hardware:fabric:windows -- -Mode Status
pnpm hardware:robot:windows -- -Mode Stop -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:glasses:windows -- -Mode Stop -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:fabric:windows -- -Mode Stop
```

Stop component adapters before the shared process. A component stop affects
only its own session; the red **Emergency stop** in the UI and the shared
launcher stop intentionally apply the global safety stop.
