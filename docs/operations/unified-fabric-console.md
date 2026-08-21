# Unified Interaction Fabric console

The supported classroom topology is one local Fabric process and one `/fabric`
UI. Every running adapter registers into that process, so sensors, wearables,
robots, IoT devices, simulators, and coding agents can be assigned and observed
without opening a device-specific console.

The discovery center shows every supported integration, but keeps hardware
candidates separate from authenticated Fabric nodes. The connected-node
inventory still shows only adapters that actually registered; the UI does not
fake a capability because an SSID, USB name, process, or encrypted profile was
found.

## Start the shared console

If a legacy per-integration Fabric is already using port 8766, stop its
component launcher first. This preserves its database while releasing the port:

```powershell
pnpm hardware:glasses:windows -- -Mode Stop
```

Do not kill the Python PID directly; the component launcher also restores its
temporary Agent Mesh changes. Then start the shared host:

```powershell
pnpm hardware:devices:windows -- -Mode Start
```

The launcher opens **CIT Classroom Control** and signs this Windows user in
automatically. No credential needs to be copied or pasted. To reopen the tutor
screen without restarting Fabric or any adapter, run:

```powershell
pnpm hardware:fabric:windows -- -Mode Open
```

The launcher exchanges a one-use, short-lived URL-fragment ticket for a
12-hour instructor session. It removes the ticket from the address bar before
loading classroom data, holds the resulting access only in page memory, and
clears it on reload or sign-out. The administrator bootstrap remains
current-user DPAPI protected under
`%LOCALAPPDATA%\CITPhysicalXR\interaction-fabric`; it is never printed, copied
to the browser, or stored in the repository.

## Tutor workflow

The main screen always highlights one next action. A normal lesson takes five
steps:

1. **Find devices** — power on today's equipment, plug in USB devices, then
   choose **Find devices**. Review Connected, Found, Ready, or Setup needed on
   each supported integration card. Discovery cannot arm or actuate hardware.
2. **Choose lesson** — select the large card that matches the activity and
   choose **Set up this lesson**. If exactly one compatible device is connected
   for a role, CIT assigns it automatically.
3. **Assign devices** — use the card's fixed setup step where needed, select a device
   for each missing role, and choose **Use this device**. The screen explains
   what each role does; protocol names are hidden under **Technical details**.
4. **Safety check** — simulation remains locked from real hardware. Physical
   lessons require the tutor acknowledgement and **Enable physical controls**
   before **Start lesson** becomes available.
5. **Teach** — use only the controls relevant to the selected lesson. Pause,
   end, and the red **Stop all devices** control remain visible. Detailed
   events, command lifecycle, identifiers, and audit records are collapsed
   under **Technical diagnostics**.

If automatic sign-in cannot complete, expand **Use an access code instead** on
the welcome screen and use `-Mode CopyCredential` as a recovery-only path.
Clear the clipboard immediately afterward. Tutors should normally use
`-Mode Open`.

## Attach integrations

Every component launcher receives the same shared root and port but retains a
separate component state directory:

```powershell
$fabricRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"

# Preserved Tello/MindWave host; connection buttons then appear in this UI
pnpm hardware:brain:windows -- -Mode Start -SharedFabricRoot $fabricRoot

# Existing G2/Meta and Codex/Claude bridge
pnpm hardware:glasses:windows -- -Mode Start -SharedFabricRoot $fabricRoot -FabricPort 8766 -SelectMostRecentAgentSession

# Leap and RoboMaster using semantic demo input and the real upstream dry-run robot
pnpm hardware:robot:windows -- -Mode Start -SharedFabricRoot $fabricRoot -FabricPort 8766

# Tuya-compatible smart-plug simulator (same UI, no outlet contacted)
pnpm hardware:plug:windows -- -Mode Start -SharedFabricRoot $fabricRoot -FabricPort 8766
```

Each component launcher reopens the same tutor screen after attaching. Choose
**Refresh devices** if it was already open. The device inventory groups devices
as **Sends information**, **Sends and receives**, and **Receives instructions**.
Technical capability and adapter identifiers remain available inside each
device's collapsed details. The smart plug appears in the bidirectional group
because it reports state and receives the bounded on/off instruction.

Site and room scopes still isolate sessions. Create or select the relevant
course pack, assign connected capability-compatible nodes to logical roles,
then start the session. One UI can monitor multiple rooms without allowing one
session to commandeer another room's node.

The Tello card can associate discovered USB Wi-Fi radios and start grounded
SDK handshakes through Brain2Devices. It cannot fly an aircraft. The MindWave
card can start the preserved headset connection. Smart plugs cannot be
authenticated from network presence: configure each exact DPAPI-protected
profile once from PowerShell. See `device-discovery.md`.

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
pnpm hardware:plug:windows -- -Mode Stop -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:fabric:windows -- -Mode Stop
```

Stop component adapters before the shared process. A component stop affects
only its own session; the red **Emergency stop** in the UI and the shared
launcher stop intentionally apply the global safety stop.
