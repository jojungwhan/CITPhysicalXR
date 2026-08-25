# Sphero Ollie — Windows hardware guide

## Tutor setup in Classroom Control

No Sphero account or cloud service is needed. Do not pair Ollie in Windows
Bluetooth Settings; CIT connects directly over local BLE.

1. Charge Ollie, switch it on, and read its exact `2B-XXXX` advertised name.
2. Close Sphero Edu and any other program currently connected to the robot.
3. Open **CIT Classroom Control**, start classroom devices, then choose
   **Find devices**.
4. In **Sphero Ollie**, choose the exact `2B-XXXX` robot. Connection starts
   sensor monitoring only and sends no movement. Vendor-safe startup may clear
   the current LEDs.
5. Put Ollie on a clear floor and keep **Stop all devices** visible. Point the
   blue tail light toward the tutor and choose **Set this direction as forward**.
6. Test **Stop**, one LED colour, and one arrow. The adapter uses a conservative
   raw speed ceiling and stops locally within 750 ms.

The UI remembers the exact local profile. **Reconnect remembered devices** can
reopen it later without scanning every integration, provided Ollie is awake and
not connected to another app.

## Technician preflight

The following diagnostic is read-only and sends no robot command:

```powershell
pnpm hardware:sphero-ollie:windows -- -Mode Preflight
```

Expected output lists opaque `sphero-ollie-*` candidates beside exact
`2B-XXXX` names. This radio-free installation check is also available:

```powershell
pnpm hardware:sphero-ollie:windows -- -Mode Preflight -Simulation
```

If support is missing, rerun the current CIT business installer. Logs are in
`%LOCALAPPDATA%\CITPhysicalXR\sphero-ollie\logs`.

## Required physical acceptance evidence

Use one charged Ollie first, with wheels raised for the first actuator check and
then in a clear enclosed floor area:

- record firmware, Windows version, Bluetooth adapter, and exact name;
- prove scanning makes no connection, LED, aim, or movement change;
- confirm connection sends no movement and record the expected startup LED
  clear;
- prove only the selected `2B-XXXX` connects when two candidates are visible;
- verify aim reset, four bounded directions, stop, RGB/off, and sensor cards;
- measure travel on the classroom surface before changing the conservative
  speed-value ceiling;
- verify duplicate delivery produces one action;
- verify deadman, Stop, disarm, session stop, adapter stop, Bluetooth loss, and
  process termination all leave the robot stopped;
- preserve redacted logs without BLE addresses or credentials.

Until this checklist passes, simulation is the supported lesson-development
path and the physical adapter remains HIL pending.
