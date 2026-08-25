# Wonder Workshop Dash and Dot — Windows hardware guide

Status: software path implemented; physical Bluetooth validation pending.

## What tutors use

1. Charge Dash or Dot and switch it on near the tutor computer.
2. Close Wonder, Blockly, or another app connected to that robot. BLE normally
   permits only one active controller.
3. Open **CIT Classroom Control** from the Windows CIT button and choose
   **Start classroom devices**.
4. Choose **Find devices**. In **Wonder Workshop Dash and Dot**, match the
   printed/classroom robot to its exact visible name and signal level.
5. Select one to four exact robots, then choose **Connect selected robots**.
   Connection starts sensor monitoring only and sends no robot command.
6. In the monitoring lesson, confirm that each robot is assigned to a
   **Dash or Dot** role and that its sensor card changes when a button is
   pressed or the robot is picked up.

## First output test

Keep Dash's wheels raised for the first test and clear the floor area. Choose a
light, sound, head, or movement control directly; the first command prepares
the local control session automatically.

- Dot intentionally has no drive or head buttons.
- Dash arrows issue short nudges, not continuous free driving. The adapter
  writes a stop after 350 ms unless another approved command arrives.
- The red stop button remains available as a safe-state request. **Stop all
  devices** in the page header overrides all ordinary controls.

## Technician validation

The business installer installs the optional Bleak transport. A technician can
run a non-connecting diagnostic if needed:

```powershell
pnpm hardware:wonder:windows -- -Mode Preflight
```

Expected output lists opaque `wonder-*` candidates and
states that no connection or command was sent. Tutors should not need this
command; normal setup is entirely in the page.

For a launcher self-check without Bluetooth:

```powershell
pnpm hardware:wonder:windows -- -Mode Preflight -Simulation
```

Full adapter simulation is exercised by the automated contract suite. Physical
selection input is supplied by the authenticated UI. Do not type or store a
Bluetooth address in a course pack.

## Hardware evidence checklist

- Record Windows version, Bluetooth adapter, robot model, and firmware/app
  version without recording a BLE address.
- Verify exact selection with two powered robots in range.
- Verify Dash forward, reverse, left, right, explicit stop, and the 350 ms
  deadman with wheels raised before a floor test.
- Verify Dot exposes no movement/head capability.
- Verify RGB, all three fixed sound cues, buttons, picked-up state, and Dash
  proximity/head/wheel telemetry.
- Disconnect Bluetooth during Dash movement and confirm local safe stop.
- Confirm raw microphone amplitude, Bluetooth addresses, and credentials do
  not appear in Fabric events, recordings, logs, or browser data.
