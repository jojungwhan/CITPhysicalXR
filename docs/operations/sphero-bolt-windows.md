# Sphero BOLT — Windows hardware guide

## Tutor setup in Classroom Control

You do **not** pair BOLT in Windows Bluetooth Settings and do not need a Sphero
account, app, or cloud service for CIT control.

1. Charge BOLT. Remove it from its cradle to wake it and read its exact
   `SB-XXXX` name.
2. Close Sphero Edu, Sphero Play, browser Bluetooth dialogs, or any other app
   connected to that robot. One BLE client can normally control it at a time.
3. Open **CIT Classroom Control** from the Windows shortcut and choose
   **Start classroom devices**.
4. Choose **Find devices**. In **Sphero BOLT**, tick the exact `SB-XXXX` robot
   you are holding and choose **Connect selected BOLT robots**. CIT does not
   select the strongest or nearest advertisement.
5. Connection starts sensor monitoring only. Select the monitoring lesson and
   choose **Enable physical controls** only with BOLT on a clear floor.
6. Turn BOLT until its blue tail light points toward you. Choose **Set this
   direction as forward**. The direction away from you is now forward.
7. Test **Stop**, an LED colour, and one arrow. Each arrow is a 0.20 m/s bounded
   nudge; the adapter stops locally after 750 ms.

If Windows Settings already shows BOLT as paired, remove that pairing, close
Settings, wake BOLT, and scan again in CIT. Pairing is not proof of a live CIT
connection.

## Technician preflight

This read-only scan connects to nothing and sends no robot command:

```powershell
pnpm hardware:sphero:windows -- -Mode Preflight
```

Expected output lists opaque `sphero-*` candidates beside exact `SB-XXXX`
names. A radio-free check is also available:

```powershell
pnpm hardware:sphero:windows -- -Mode Preflight -Simulation
```

Tutors should use the UI, not these commands. The CLI remains available for
installation diagnostics and recovery.

## Required physical acceptance evidence

Use one BOLT at first, in a clear enclosed floor area:

- record BOLT firmware, Windows version, Bluetooth adapter, and exact name;
- prove a scan makes no connection, LED, aim, or roll change;
- prove only the selected `SB-XXXX` connects when two robots are visible;
- verify aim reset, all four 0.20 m/s directions, matrix/front/back RGB/off,
  and sensor cards;
- verify duplicate delivery produces one action;
- verify the robot stops within the expected 750 ms deadman window;
- verify **Stop**, disarm, session stop, adapter stop, Bluetooth loss, and
  process termination all leave the robot stopped;
- inspect `%LOCALAPPDATA%\CITPhysicalXR\sphero-bolt\logs` and save the result
  without BLE addresses or credentials.

Until this checklist passes for the installed firmware, the UI's simulator is
the supported lesson-development path and physical HIL remains pending.
