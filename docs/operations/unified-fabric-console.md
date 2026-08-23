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
temporary Agent Mesh changes. Then double-click **CIT Classroom Control** on
the Windows Desktop or choose it from the Start menu. Choose **Start classroom
devices**. The launcher opens the browser and signs this Windows user in
automatically. No credential or command needs to be copied or pasted. Use the
same button again to reopen the tutor screen without restarting Fabric or any
adapter.

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
   each supported integration card. Cards are grouped as **Inputs**, **Inputs +
   outputs**, and **Outputs**. Leap and MindWave are input-only; a connected
   node's published and consumed capabilities determine its final group. Choose
   **Connect all available** to run
   every verified connect-only adapter; aircraft require the grounded safety
   confirmation first. Discovery never actuates hardware. Connection cannot arm
   a lesson; approved smart-plug adapters may place their outlet in the declared
   off safe state.
2. **Choose lesson** — select the large card that matches the activity and
   choose **Set up this lesson**. If exactly one compatible device is connected
   for a role, CIT assigns it automatically.
3. **Assign devices** — use the card's fixed setup step where needed, select a device
   for each missing role, and choose **Use this device**. The screen explains
   what each role does and groups lesson jobs under **Inputs**, **Inputs +
   outputs**, and **Outputs**; protocol names are hidden under **Technical
   details**.
   The **Simultaneous multi-device cue** lesson lets the tutor assign one or
   more Leap/G2/Meta inputs and independently select RoboMaster or LEGO ground
   outputs, G2/Meta message outputs, and the optional bounded Tello fleet. Its
   **Simultaneous output plan** shows exactly which assigned outputs will run.
4. **Safety check** — simulation remains locked from real hardware. Physical
   lessons require the tutor acknowledgement and **Enable physical controls**
   before **Start lesson** becomes available.
5. **Teach** — use only the controls relevant to the selected lesson. Pause,
   end, and the red **Stop all devices** control remain visible. Detailed
   events, command lifecycle, identifiers, and audit records are collapsed
   under **Technical diagnostics**.

For the simultaneous cue, start and arm the physical lesson, then separately
complete **Arm this one sequence** in the fleet panel if drones are assigned.
The approved Leap pinch or exact G2/Meta fleet phrase sends one semantic event.
Assigned ground and display actions are dispatched concurrently; the fleet
starts only if its one-shot controller is still armed. “Concurrent” is not a
hard-real-time guarantee, and each output can independently succeed, reject, or
enter its adapter safe state.

Below the teaching controls, the same page contains a camera wall, a guided
MindWave one-shot demonstration panel, and live
sensor cards. Authenticated Meta, robot, drone, simulator, and future camera
publishers receive one latest-frame tile. Normalized LEGO, robot, biosignal,
and battery events receive one latest-reading card. The UI support does not
claim that every physical publisher is complete; see
`classroom-cameras-and-sensors.md` for the exact hardware matrix and Meta phone
setup.

If automatic sign-in cannot complete, expand **Use an access code instead** on
the welcome screen and use `-Mode CopyCredential` as a recovery-only path.
Clear the clipboard immediately afterward. Tutors should normally use the
Windows button. Command-line recovery is for technicians only.

## Install the Windows button

The repository/source installation creates the Desktop and Start menu entries
once with:

```powershell
pnpm hardware:install-button:windows
```

This is a maintainer installation step, not part of the tutor workflow. The
shortcut opens a fixed native launcher; it accepts no command, URL, device
address, or credential from the user.

## Attach integrations

Every component launcher receives the same shared root and port but retains a
separate component state directory:

```powershell
$fabricRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"

# Preserved Tello/MindWave host; UI buttons attach independent Fabric nodes
pnpm hardware:brain:windows -- -Mode Start -SharedFabricRoot $fabricRoot

# Software-only independent Tello and MindWave nodes
pnpm hardware:brain:fabric:windows -- -Mode Start -Device All -Simulation -SharedFabricRoot $fabricRoot -FabricPort 8766

# Shared transport for distinct Even G2, Meta Ray-Ban, Codex, and Claude profiles
pnpm hardware:glasses:windows -- -Mode Start -SharedFabricRoot $fabricRoot -FabricPort 8766 -SelectMostRecentAgentSession

# Leap and RoboMaster using semantic demo input and the real upstream dry-run robot
pnpm hardware:robot:windows -- -Mode Start -SharedFabricRoot $fabricRoot -FabricPort 8766

# Cloud-free Matter controller/adapters (business installer and UI are preferred)
pnpm hardware:matter:windows -- -Mode Start -SharedFabricRoot $fabricRoot -FabricPort 8766

# LEGO simulator or a previously saved physical exact-name profile
pnpm hardware:lego:windows -- -Mode Start -Simulation -SharedFabricRoot $fabricRoot -FabricPort 8766
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

The Tello card can associate discovered USB Wi-Fi radios, start grounded SDK
handshakes through exact-pinned Brain2Devices, and register one independent
Fabric node per connected aircraft. The teaching panel offers only land and a
confirmed emergency motor stop—no ordinary takeoff or movement. Its latest
Brain2Devices video frame appears in the common camera wall. The MindWave card
starts an independent publish-only node. A third bounded-demo node is assigned
automatically and shows one explicit instructor-gated arm plus stop control; it
does not change either ordinary adapter contract. The LEGO card accepts its exact hub name,
model, and port map directly in this UI and starts unarmed sensor monitoring.
Smart plugs cannot be authenticated from network presence: new sites should
use the Matter card, which commissions compatible plugs locally from their
printed setup code. See `device-discovery.md`.

## Physical devices

Simulation is the default. To run physical adapters, use the installed **CIT
Classroom Control** Windows button and choose **Enable classroom devices**. The
button safely restarts the shared Fabric with physical dispatch and scoped
phone-camera access; tutors do not type an `-AllowPhysical` command.

The equivalent commands remain available only for technicians diagnosing the
launcher.

`-AllowPhysical` only enables the policy path. Every physical session remains
disarmed until its explicit arm transition, and the UI emergency stop remains
higher priority than every lesson, student, or agent command.

## Status and shutdown

```powershell
pnpm hardware:fabric:windows -- -Mode Status
pnpm hardware:robot:windows -- -Mode Stop -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:brain:fabric:windows -- -Mode Stop -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:lego:windows -- -Mode Stop -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:glasses:windows -- -Mode Stop -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:matter:windows -- -Mode Stop -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:fabric:windows -- -Mode Stop
```

Stop component adapters before the shared process. A component stop affects
only its own session; the red **Emergency stop** in the UI and the shared
launcher stop intentionally apply the global safety stop.
