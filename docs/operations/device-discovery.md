# Find and connect classroom devices

Use this workflow on the Windows tutor computer. It brings the supported
hardware checklist into **CIT Classroom Control** without scanning for secrets
or enabling physical outputs.

## Start the device host

1. Double-click **CIT Classroom Control** on the Windows Desktop or choose it
   from the Start menu.
2. Choose **Start classroom devices**. If a simulation-only host is already
   running, choose **Enable classroom devices** and confirm the safe restart.
3. Wait for the browser tutor screen to open automatically.

The button starts or preserves the shared Fabric on `127.0.0.1:8766`, starts or
preserves the existing Brain2Devices helper on `127.0.0.1:8765`, and opens the
single tutor UI with automatic local sign-in. Starting these services does not
connect a headset, send a Tello SDK packet, arm a robot, start an agent, or
switch a plug. Physical-adapter mode permits authenticated physical adapters
to register, but every newly created lesson remains disarmed.

In the UI, choose **Find devices**. When one or more validated connectors are
available, choose **Connect all available** to attach them in sequence. This is
connect-only: lessons, robots, drones, and outlets remain disarmed. If a Tello
is included, the button stays locked until the tutor confirms that every
aircraft is grounded with its propellers removed or guarded. You can still use
an individual card's connection button when troubleshooting one integration.

After an adapter has connected successfully once, CIT remembers its fixed,
allowlisted reconnect action for this Windows host. On later starts, CIT
automatically reuses the exact local Matter, LEGO, Sphero, Dash/Dot, glasses,
sensor, or other non-aircraft adapter profile without running the broad
USB/Bluetooth/Wi-Fi/Android scan. **Connect remembered devices** retries the
same profiles immediately when troubleshooting. The full **Find devices**
button remains available for new, changed, missing, or partially connected
hardware.

Remembering a connection stores only the host ID, fixed reconnect action ID,
grounded-aircraft requirement, actor, and timestamp in the Fabric SQLite
database. Vendor credentials and raw discovery identifiers are not copied.
Adapter-owned profiles remain the source of truth for exact device selection.
Already-live adapter groups are left running. Automatic reconnect never carries
an aircraft-grounded confirmation, so Tello actions are skipped until a tutor
confirms grounded status and presses the remembered-device button manually.
Reconnect does not arm a lesson or enable movement, motor, takeoff, agent tool,
or plug power-on commands.

Each integration has one of these states:

| State          | Meaning                                                                |
| -------------- | ---------------------------------------------------------------------- |
| Connected      | An authenticated adapter registered a live Fabric capability node.     |
| Found          | Hardware or a vendor service is visible; connection is still separate. |
| Computer ready | Required host software/radio/profile is ready; hardware may be off.    |
| Setup needed   | Follow the numbered card steps once, then scan again.                  |
| Not found      | The check ran and no matching candidate was visible.                   |

Candidates also carry a separate read-only link label such as **Attached
now**, **Connected now**, **Recently active**, **Visible nearby**, **Paired**,
or **Configured**. These labels describe the evidence Windows, Android, or a
local service can currently observe. They do not replace the **Connected**
integration state, which requires an authenticated CIT adapter registration.

The host scan checks these paths without pairing or controlling a device:

- present USB/PnP hardware, including Leap and DJI RNDIS links;
- present matching Bluetooth devices and their required local bridge service;
- current Wi-Fi interfaces, routes, visible Tello networks, and local Matter
  reachability;
- authorized physical Android phones visible through ADB over USB or Wi-Fi;
- recently used, profile-specific G2 and Meta identities in Agent Mesh.

ADB serials, Bluetooth addresses, Agent Mesh device IDs, and credentials are
discarded. The report retains only a generic candidate number, sanitized phone
model, connection path, known CIT companion-package readiness, and coarse
activity state. A generic LAN host is never guessed to be a robot, phone, or
smart plug.

**Copy setup command** copies only a fixed CIT command. Android serials, Agent
Mesh device IDs, tokens, setup codes, and credentials never enter the general
browser report.

## Tello and USB Wi-Fi radios

For stock Tello access-point mode, use one physical USB Wi-Fi adapter per
simultaneous aircraft. Tello EDU/RoboMaster TT station mode may instead use
unique addresses on a common access point.

1. Remove propellers for the first connection test. Keep every aircraft
   grounded and separated.
2. Attach and enable the USB Wi-Fi adapters.
3. Power on each aircraft and wait for its `TELLO-*` or `RMTT-*` SSID.
4. Choose **Find devices**. Every physical radio and visible aircraft network
   is listed independently.
5. Tick the one grounded-aircraft confirmation and choose **Connect all
   available grounded drones**. The same confirmation also applies to remembered
   reconnect and the Tello-card action; it is not repeated in each panel.
   Windows may request administrator approval to create unique on-link routes.
6. Wait for the card to report a connected Fabric node for each aircraft.

After the first aircraft connects, **Available now** collapses so the live
controls stay in one screen. Expand it whenever another device needs setup.
The Tello card keeps **Connect all available grounded drones** visible after the
first connection, allowing another scanned radio/aircraft route to join the
same fleet.

The connection action may associate radios, configure isolated routes, import
the fleet, and start SDK handshakes. It then projects each connected aircraft
through its own `cit.tello` node in an unarmed monitoring session. Connection
sends no takeoff, landing, movement, or emergency packet. The node publishes
telemetry and exposes tutor-confirmed takeoff, movement, rotation, land, and
emergency stop. Non-safe commands become available only after the tutor
completes the one visible flight attestation, which maps to the three bounded
contract confirmations; the first flight command explicitly arms and starts
the device session. Manual
movement is discrete and bounded to 20–50 cm, and rotation to 1–90°. Do not
treat discovery/handshake evidence as flight approval.

When one or more independently routed Tellos are connected, CIT also starts a
separate bounded fleet-sequence controller. Its tutor buttons take off and land
the selected aircraft one at a time, confirming each state before advancing.
Re-run **Find devices** and connect
Leap or G2/Meta afterward to attach those input-only nodes to the same monitoring
session. Per-aircraft manual controls remain independent from the fleet
controller. The physical attestation remains explicit; **Take off one by one**
prepares and consumes one ordered arm, while **Prepare ring / sensor trigger**
leaves that one-shot arm waiting for an approved input.

## MindWave Mobile 2

1. Pair the headset in Windows Bluetooth settings.
2. Install and start ThinkGear Connector, select its outgoing COM port, and
   confirm `localhost:13854` is listening.
3. Open Classroom Control and choose **Find devices**.
4. Choose **Connect headset**. Adjust the forehead and ear contacts until the
   vendor signal-quality value is stable.

The action registers an independent, publish-only `cit.mindwave-mobile2` node.
Neither discovery nor the adapter emits or persists raw EEG. Values remain
explicitly labelled as MindWave/vendor eSense values and are not medical or
objective attention data. Follow the exact setup and HIL checklist in
[Brain2Devices Tello and MindWave integration](brain2devices-fabric.md).

## RoboMaster S1 and Leap Motion

The scan checks the Ultraleap USB/service/runtime boundary and briefly listens
for incoming DJI STA broadcasts on UDP 45678. It sends no discovery packet and
does not identify a generic LAN host as a robot.

When the Leap runtime/controller and a RoboMaster STA broadcast are both found,
choose **Connect robot and Leap**. CIT starts two separately supervised adapter
processes with separate plugin identities and credentials. Each can reconnect
or fail without terminating the other. Both nodes are bound to an unstarted,
disarmed lesson with no activation file. For AP, RNDIS, or explicit-address setups,
use **Copy setup command** and follow
[RoboMaster and Leap hardware validation](robomaster-leap-hardware.md). For the
first robot connection, raise the wheels. A found network candidate is not a
completed DJI handshake, and movement still requires the tutor to complete the
separate safety/start step.

If the active monitoring session already contains the bounded fleet controller,
the same Connect action deliberately starts Leap only and assigns it to the first
free fleet-input role. It does not start or connect RoboMaster. The open-hand to
pinch transition can consume only a tutor's current one-shot fleet arm.

## Matter smart plugs (recommended)

The business installer starts a CIT-owned Matter controller on loopback and
configures the classroom Wi-Fi once. In the unified UI, use **Matter smart
plugs (cloud-free)**, put a Matter-certified plug in pairing mode, and enter the
setup code printed beside its Matter QR label. The value is carried only by the
authenticated request and fixed process stdin; it is not a Fabric event,
command-line argument, audit detail, or saved browser setting.

The controller and plug communicate locally. No proprietary vendor account,
API, device ID, local key, or cloud is used. Only a Descriptor-advertised Matter
On/Off Plug-in Unit endpoint is registered; CIT does not expose arbitrary
clusters. Follow [Matter smart plugs on Windows](matter-smart-plug-windows.md).

## Glasses, agents, and LEGO

- Even Realities G2 and Meta Ray-Ban have separate cards, setup instructions,
  Android package checks, activity evidence, and node matching. Both reuse the
  authenticated Agent Mesh transport. For setup diagnostics, an Android phone
  may be authorized in ADB over USB or Android wireless debugging. Normal
  classroom use may remain on the phone's local Wi-Fi Agent Mesh connection;
  ADB is not placed in the semantic interaction or media data path.
- Codex/Claude cards distinguish installed executables from supervised Agent
  Mesh sessions. **Connect glasses and agent** starts only the fixed bridge for
  an already approved session; it never creates an agent or grants a workspace.
- LEGO cards show visible candidates but never choose the nearest BLE hub. Do
  not pair a Pybricks hub in Windows Settings; remove an existing pairing. In
  the card, enter the exact Pybricks Bluetooth name, select the hub model, map
  its ports, and choose **Save and connect hub**. One sensor or motor is enough
  for monitoring; two motors are required before the node advertises ground
  mobility. Setup starts an unarmed monitoring session and issues no motor
  command.

## Local BLE classroom robots

- Sphero BOLT discovery accepts only exact `SB-XXXX` advertisements and returns
  opaque `sphero-*` IDs. Do not pair BOLT in Windows Settings. Select the exact
  robot in the card; connection starts unarmed sensor monitoring. Aim reset and
  movement remain locked until the physical lesson is armed, and each movement
  has a 750 ms local deadman. See [Sphero BOLT on Windows](sphero-bolt-windows.md).
- Dash and Dot likewise use exact local advertisements and opaque IDs. They do
  not share the Sphero adapter, state, protocol, or process.

## Command-line checks

The following commands are technician diagnostics, not tutor startup steps:

```powershell
pnpm hardware:devices:windows -- -Mode Scan
pnpm hardware:devices:windows -- -Mode Status
pnpm hardware:brain:windows -- -Mode Preflight
pnpm hardware:brain:windows -- -Mode Status
pnpm hardware:brain:fabric:windows -- -Mode Preflight -Device All
pnpm hardware:lego:windows -- -Mode Status
pnpm hardware:sphero:windows -- -Mode Preflight
```

The JSON scan is read-only and accepts no browser or device credential. Its
Agent Mesh readiness check uses Agent Mesh's existing locally scoped CLI
credential, reduces the result to a count, and discards session metadata.
Status output contains counts and connection states, not tokens, paths,
prompts, or device credentials.
