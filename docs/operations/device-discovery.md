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

Each integration has one of these states:

| State          | Meaning                                                                |
| -------------- | ---------------------------------------------------------------------- |
| Connected      | An authenticated adapter registered a live Fabric capability node.     |
| Found          | Hardware or a vendor service is visible; connection is still separate. |
| Computer ready | Required host software/radio/profile is ready; hardware may be off.    |
| Setup needed   | Follow the numbered card steps once, then scan again.                  |
| Not found      | The check ran and no matching candidate was visible.                   |

**Copy setup command** copies only a fixed CIT command. Device IDs, local
keys, tokens, IP addresses, and credentials never enter the browser report.

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
5. Tick the grounded-aircraft confirmation and choose **Connect grounded
   drones**. Windows may request administrator approval to create unique
   on-link routes.
6. Scan again. Brain2Devices connection state is summarized in the Tello card.

The connection action may associate radios, configure isolated routes, import
the fleet, and start SDK handshakes. It sends no takeoff, landing, movement, or
emergency packet. Canonical Fabric flight commands are still pending the drone
safety slice; do not treat discovery/handshake evidence as flight approval.

## MindWave Mobile 2

1. Pair the headset in Windows Bluetooth settings.
2. Install and start ThinkGear Connector, select its outgoing COM port, and
   confirm `localhost:13854` is listening.
3. Start Brain2Devices with the command above and choose **Find devices**.
4. Choose **Connect headset**. Adjust the forehead and ear contacts until the
   vendor signal-quality value is stable.

Discovery persists no EEG samples. Values remain explicitly labelled as
MindWave/vendor eSense values and are not medical or objective attention data.

## RoboMaster S1 and Leap Motion

The scan checks the Ultraleap USB/service/runtime boundary and briefly listens
for incoming DJI STA broadcasts on UDP 45678. It sends no discovery packet and
does not identify a generic LAN host as a robot.

When the Leap runtime/controller and a RoboMaster STA broadcast are both found,
choose **Connect robot and Leap**. CIT runs the characterized adapter in
connect-only mode, binds both nodes to an unstarted lesson, and leaves the lesson
disarmed with no activation file. For AP, RNDIS, or explicit-address setups,
use **Copy setup command** and follow
[RoboMaster and Leap hardware validation](robomaster-leap-hardware.md). For the
first robot connection, raise the wheels. A found network candidate is not a
completed DJI handshake, and movement still requires the tutor to complete the
separate safety/start step.

## Tuya and Gosund plugs

Network presence cannot authenticate a Tuya-compatible outlet. Configure every
approved plug once with its exact private address, device ID, local key,
protocol version, and boolean switch DPS:

```powershell
pnpm hardware:plug:windows -- -Mode Configure
```

The key is entered in PowerShell, protected with current-user DPAPI, and never
returned by discovery. The scan passively listens for Tuya-family LAN
announcements and may show only a possible-device count; it does not send a
probe, return addresses, guess credentials, or assume that every Gosund model
supports local Tuya control. Scan again after configuration, then choose
**Connect approved plug**. The adapter reads current state, registers against
an unstarted lesson, and remains disarmed; it does not change the outlet state. Follow
[Tuya/Gosund hardware validation](tuya-smart-plug-hardware.md) before enabling
student use.

## Glasses, agents, and LEGO

- Even G2/Meta cards distinguish Agent Mesh readiness, authorized Android
  bridges, and actual recently connected wearable nodes.
- Codex/Claude cards distinguish installed executables from supervised Agent
  Mesh sessions. **Connect glasses and agent** starts only the fixed bridge for
  an already approved session; it never creates an agent or grants a workspace.
- LEGO cards show paired candidates but never choose the nearest BLE hub. Bind
  each Pybricks hub by its unique classroom name before connecting motors.

## Command-line checks

The following commands are technician diagnostics, not tutor startup steps:

```powershell
pnpm hardware:devices:windows -- -Mode Scan
pnpm hardware:devices:windows -- -Mode Status
pnpm hardware:brain:windows -- -Mode Preflight
pnpm hardware:brain:windows -- -Mode Status
```

The JSON scan is read-only and accepts no browser or device credential. Its
Agent Mesh readiness check uses Agent Mesh's existing locally scoped CLI
credential, reduces the result to a count, and discards session metadata.
Status output contains counts and connection states, not tokens, paths,
prompts, or device credentials.
