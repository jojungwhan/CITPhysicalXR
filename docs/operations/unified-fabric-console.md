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
temporary Agent Mesh changes. Then double-click **CIT Control Tower** on
the Windows Desktop or choose it from the Start menu. Choose **Start classroom
devices**. The launcher opens one dedicated Control Tower app window and
signs this Windows user in automatically. No credential or command needs to be
copied or pasted. Use the same button again to replace the previous CIT-owned
window with a freshly signed-in one without restarting Fabric or any adapter.
Normal browser windows and tabs are never closed.

The launcher exchanges a one-use, short-lived URL-fragment ticket for a
12-hour instructor session. It removes the ticket from the address bar before
loading classroom data, holds the resulting access only in page memory, and
clears it on reload or sign-out. The administrator bootstrap remains
current-user DPAPI protected under
`%LOCALAPPDATA%\CITPhysicalXR\interaction-fabric`; it is never printed, copied
to the browser, or stored in the repository.

## Allow selected local Wi-Fi devices

Control Tower does not require an IPTIME/router allowlist. When local-network
access is enabled, the Windows firewall rule admits only Private-profile,
local-subnet TCP traffic to this computer's exact Control Tower address and
port. Control Tower then resolves each same-link IPv4 client through the local
ARP table and rejects it unless its canonical MAC address appears in the app's
allowlist. Bearer/session authentication is still required after that check;
MAC filtering is defense in depth and must never be treated as internet-safe
authentication.

On the tutor computer, open **Settings > Local Wi-Fi access**. Add a named MAC
address manually, or connect the dedicated Android phone by USB and choose
**Allow and open USB phone**. The latter reads Android's private, per-network
Wi-Fi MAC over the authorized ADB connection, stores it in the local runtime
state, and opens an exact LAN URL with a short-lived one-use session ticket. If
Android changes that privacy address, enroll it again. Android and
other remote sessions cannot view or change this list; management is accepted
only from a loopback tutor console with the dedicated permission.

For another listed phone, tablet, or computer, choose **Copy access link** and
open the copied URL on that exact allowed device within 90 seconds. The URL
contains a one-use ticket, creates the limited remote-control session, and is
removed from the address bar before device data loads. Do not reuse the local
administrator recovery credential on a remote device.

Windows needs administrator approval once for the narrow inbound rule. If the
launcher reports that setup is required, run the following from an elevated
PowerShell window, substituting the private IPv4 address assigned to the Control
Tower computer when necessary:

```powershell
pnpm hardware:fabric:windows -- -Mode ConfigureLanFirewall -FabricPort 8766 -LanAddress 192.168.1.10
```

The rule uses `LocalSubnet`, the exact local address, TCP port 8766, and the
Private profile. It does not change the router and does not expose the service
through a WAN interface. Routed/VPN clients and IPv6 LAN clients fail closed
because the MAC gate supports only directly reachable IPv4 neighbors.

## Turn on selected plugs when the dedicated phone unlocks

This is a local Wi-Fi automation; the phone does not remain connected by USB.
Control Tower must be running with physical devices and scoped local-network
access enabled, and the phone must use the same directly reachable private
Wi-Fi as this PC.

1. Connect the dedicated Android phone by USB once and approve USB debugging.
2. In the PC's **Settings > Phone unlock automation**, choose **Install and
   pair companion**. Control Tower builds/installs its small native companion,
   provisions a unique signing identity, and adds the phone's current
   per-network Wi-Fi MAC to the application allowlist. The server keeps the
   automation off after pairing.
3. On the main smart-plug panel, check only the outlets that may turn on. Return
   to settings and choose **Save currently checked plugs**. Browser checkbox
   persistence and the background automation target are deliberately separate.
4. Enable **Turn on saved plugs when this phone unlocks**. Read the saved target
   count before enabling it.
5. Confirm that the phone shows the ongoing Control Tower unlock-monitoring
   notification. You may then disconnect USB. Locking and securely unlocking
   the phone sends one signed event over local Wi-Fi.

The companion starts itself after a phone reboot when Android permits it. On a
Samsung phone, open the companion's **Battery settings** button and exempt it
from sleep/background restrictions if the monitoring notification disappears.
The app requires a secure device lock and ignores a screen wake that was not a
real locked-to-unlocked transition.

Events are not queued or retried. If the PC is off, Control Tower is stopped,
the phone is on a Sony/DJI Wi-Fi Direct network, or any saved plug is offline,
nothing is switched later. Reconnect the phone to the Control Tower Wi-Fi and
unlock again only after checking the saved targets. Use **Unpair phone** before
replacing the dedicated phone; the next one-time pairing resets only the
Control Tower Companion app's old local credentials.

## Tutor workflow

The main screen always highlights one next action. A normal lesson takes five
steps:

1. **Find devices** — power on today's equipment, plug in USB devices, then
   choose **Find devices**. Review Connected, Found, Ready, or Setup needed on
   each supported integration card. Cards are grouped as **Inputs**, **Inputs +
   outputs**, and **Outputs**. Leap, Even R1, and MindWave are input-only; a connected
   node's published and consumed capabilities determine its final group. Choose
   **Connect all available** to run
   every verified connect-only adapter; aircraft require the grounded safety
   confirmation first. Every integration card also has **Scan this device
   again**, so a tutor can retry a device that the first classroom scan missed
   and then use that card's validated **Connect** or setup control. Discovery
   never actuates hardware. Connection cannot arm a lesson; approved smart-plug
   adapters may place their outlet in the declared off safe state.
2. **Choose lesson** — select the large card that matches the activity and
   choose **Set up this lesson**. If exactly one compatible device is connected
   for a role, CIT assigns it automatically.
3. **Assign devices** — use the card's fixed setup step where needed, select a device
   for each missing role, and choose **Use this device**. The screen explains
   what each role does and groups lesson jobs under **Inputs**, **Inputs +
   outputs**, and **Outputs**; protocol names are hidden under **Technical
   details**.
   The **Simultaneous multi-device cue** lesson lets the tutor assign one or
   more Leap/R1/G2/Meta inputs and independently select RoboMaster, Sphero,
   LEGO, or Dash ground outputs, G2/Meta message outputs, and the optional
   bounded Tello fleet. Its
   **Simultaneous output plan** shows exactly which assigned outputs will run.
4. **Safety check** — simulation remains isolated from real hardware. For a
   spatial physical lesson, complete the tutor acknowledgement and choose
   **Start lesson**; CIT prepares the session in that same action. Inline
   device controls prepare their local session on the first direct command.
5. **Teach** — use only the controls relevant to the selected lesson. Pause,
   end, and the red **Stop all devices** control remain visible. Detailed
   events, command lifecycle, identifiers, and audit records are collapsed
   under **Technical diagnostics**.

The Even Realities G2 card lists its supported input and display paths. G2 can
send semantic voice or button requests to an assigned Codex or Claude session
and show normalized completion text. Telegram is not installed on the glasses:
install it on the paired phone and enable Telegram in **Even app > Settings >
Notification**. The existing Agent Mesh deployment can also project its
dedicated Telegram-bot feed. Control Tower does not currently provide an
arbitrary-text G2 composer; its physical G2 display route preserves agent
completions and configured notifications.

The **Glasses device control** lesson accepts the same structured voice contract
from G2 and Meta. Assign one or both glasses inputs and up to eight ground
outputs. CIT robots forward/backward/left/right/stop fans out to all assigned
RoboMaster, Sphero, LEGO, and Dash nodes; each adapter translates the semantic
direction locally. CIT drones take off/land targets the existing Tello fleet
controller. Movement and takeoff require a second glasses press, while takeoff
also remains blocked until the tutor completes and arms the independent flight
checklist. Raw transcripts are not written to the device-control feed.

For physical use, choose **Physical devices**, set up the lesson, then use its
**Connect G2 / Meta** button. That button binds the bridge to the exact selected
lesson and assigns available compatible glasses inputs. It does not select a
Codex or Claude session and cannot be reused to launch an arbitrary local
action.

For the simultaneous cue, start the physical lesson, then separately
complete **Arm this one sequence** in the fleet panel if drones are assigned.
The approved Leap pinch, R1 double-tap, or exact G2/Meta fleet phrase sends one
semantic event.
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

# Shared transport for distinct Even R1, G2, Meta Ray-Ban, Codex, and Claude profiles
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
Fabric node per connected aircraft. The teaching panel offers instructor-only
takeoff, discrete 20–50 cm movement, 1–90° rotation, land, and a confirmed
emergency motor stop behind exact preflight confirmations. Its latest
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
Control Tower** Windows button and choose **Enable classroom devices**. The
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
