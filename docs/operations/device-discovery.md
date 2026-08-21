# Find and connect classroom devices

Use this workflow on the Windows tutor computer. It brings the supported
hardware checklist into **CIT Classroom Control** without scanning for secrets
or enabling physical outputs.

## Start the device host

```powershell
pnpm hardware:devices:windows -- -Mode Start
```

This starts or preserves the shared Fabric on `127.0.0.1:8766`, starts or
preserves the existing Brain2Devices helper on `127.0.0.1:8765`, and opens the
single tutor UI with automatic local sign-in. Starting these services does not
connect a headset, send a Tello SDK packet, arm a robot, start an agent, or
switch a plug.

In the UI, choose **Find devices**. Each integration has one of these states:

| State        | Meaning                                                                |
| ------------ | ---------------------------------------------------------------------- |
| Connected    | An authenticated adapter registered a live Fabric capability node.     |
| Found        | Hardware or a vendor service is visible; connection is still separate. |
| Ready        | Required host software/radio/profile is ready; hardware may be off.    |
| Setup needed | Follow the numbered card steps once, then scan again.                  |
| Not found    | The check ran and no matching candidate was visible.                   |

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

Use **Copy setup command** on either card, then follow
[RoboMaster and Leap hardware validation](robomaster-leap-hardware.md). For the
first robot connection, raise the wheels and use the upstream connect-only
check before any live lesson. A found network candidate is not a completed DJI
handshake, and physical movement still requires the separately enabled Fabric
and the robot runbook.

## Tuya and Gosund plugs

Network presence cannot authenticate a Tuya-compatible outlet. Configure every
approved plug once with its exact private address, device ID, local key,
protocol version, and boolean switch DPS:

```powershell
pnpm hardware:plug:windows -- -Mode Configure
```

The key is entered in PowerShell, protected with current-user DPAPI, and never
returned by discovery. Scan again to see the encrypted profile as **Ready**,
then follow [Tuya/Gosund hardware validation](tuya-smart-plug-hardware.md).
Discovery never turns a plug on or off.

## Glasses, agents, and LEGO

- Even G2/Meta cards distinguish Agent Mesh readiness, authorized Android
  bridges, and actual recently connected wearable nodes.
- Codex/Claude cards distinguish installed executables from supervised Agent
  Mesh sessions. Discovery never starts an agent or grants a workspace.
- LEGO cards show paired candidates but never choose the nearest BLE hub. Bind
  each Pybricks hub by its unique classroom name before connecting motors.

## Command-line checks

```powershell
pnpm hardware:devices:windows -- -Mode Scan
pnpm hardware:devices:windows -- -Mode Status
pnpm hardware:brain:windows -- -Mode Preflight
pnpm hardware:brain:windows -- -Mode Status
```

The JSON scan is credential-free and read-only. Status output contains counts
and connection states, not tokens or device credentials.
