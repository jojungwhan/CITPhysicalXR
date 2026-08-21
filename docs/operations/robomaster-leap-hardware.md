# RoboMaster S1 and Leap Motion hardware runbook

Status: the adapter, simulator, course flow, UI, and Python 3.8 process boundary
are implemented. This development host still lacks
`build/leap_hand_bridge.dll`, its adjacent `LeapC.dll`, and a running Ultraleap
service, so no physical movement is claimed yet.

## What the launcher controls

`tools/hardware/robomaster-leap-hardware-test.ps1` creates a dedicated local
Fabric on port `8767`, stores credentials with current-user DPAPI, installs the
`gesture-ground-robot` course, registers separate Leap and S1 nodes, assigns
logical roles, and opens the existing Fabric UI at
<http://127.0.0.1:8767/fabric>.

The default path is software-only:

```powershell
pnpm hardware:robot:windows -- -Mode Preflight
pnpm hardware:robot:windows -- -Mode Start
pnpm hardware:robot:windows -- -Mode CopyCredential
pnpm hardware:robot:windows -- -Mode Verify
pnpm hardware:robot:windows -- -Mode Stop
```

It uses the real upstream `DryRunRobot` and `CommandPump`, but a generated
semantic gesture pulse. `Verify` should report at least one gesture event, one
bounded robot-command event, and one `SUCCEEDED` lifecycle.

`CopyCredential` places the current-user DPAPI-protected Fabric credential on
the Windows clipboard without printing it. Paste it into the UI, select
**Connect locally**, and immediately clear the clipboard:

```powershell
Set-Clipboard -Value ''
```

## Prepare physical Leap input

1. Install and start the Ultraleap tracking software supported by the attached
   controller.
2. Install Visual Studio C++ Build Tools and CMake.
3. Build the preserved native bridge from the pinned upstream checkout:

   ```powershell
   Set-Location D:\dev\robomaster-gesture-control-reference
   .\build.ps1
   ```

4. Confirm both files exist in the same directory:

   ```text
   build\leap_hand_bridge.dll
   build\LeapC.dll
   ```

5. Run `-Mode Preflight -Live`. The launcher refuses live startup if the exact
   upstream revision, external Python, DLLs, tracking service, or DJI SDK is
   missing.

## Prepare RoboMaster

For DJI SDK mode, power on the robot, enable SDK mode, connect this computer by
AP, STA, or RNDIS as appropriate, and close the desktop RoboMaster app before
STA broadcast discovery. Passing `-RobotIp` skips broadcast discovery.

For a stock S1 using its Windows app, open the live drive view first and select
`-RobotTransport s1-app`. The upstream focus interlock releases W/A/S/D if the
window loses focus; run the app and launcher at the same privilege level.

Use a clear floor area, lift the drive wheels for the first test, keep the
instructor at the computer, and identify the physical power switch before arm.

## Start a live session

```powershell
pnpm hardware:robot:windows -- -Mode Preflight -Live -RobotTransport sdk -Connection sta
pnpm hardware:robot:windows -- -Mode Start -Live -RobotTransport sdk -Connection sta -RobotIp 192.168.2.1 -MaxSpeed 0.10 -MaxYaw 10
```

The startup order is deliberate:

1. Fabric starts with physical execution explicitly enabled.
2. The robot process connects and sends zero speed.
3. The two nodes register but Leap input remains inactive.
4. The course roles are assigned.
5. Fabric arms and starts the physical session.
6. Only then does the launcher create the exact activation signal that permits
   Leap semantic events.

Show one open hand until `READY`, then pinch and hold to engage. Release the
pinch to stop. A fist, missing hand, second hand, stale tracking frame, adapter
disconnect, process exit, session emergency stop, or command silence stops the
robot.

Use the red **Emergency stop** control in the Fabric UI, or run:

```powershell
pnpm hardware:robot:windows -- -Mode Stop
```

The UI also has **Test robot stop**. It sends only the allowlisted
`mobility.ground.stop` action and is safe to use as an output-path check.

## Acceptance evidence

After a deliberate low-speed gesture and release:

```powershell
pnpm hardware:robot:windows -- -Mode Verify -Live
```

Record the robot firmware, Leap controller model, Ultraleap software version,
connection mode, measured end-to-end latency, and operator. Do not mark the HIL
gate complete until pinch release, tracking loss, adapter termination, and UI
emergency stop have each produced a physical stop.

Logs and the persistent Fabric database remain under:

```text
%LOCALAPPDATA%\CITPhysicalXR\robomaster-leap-hardware-test
```

No raw Leap frames are stored.
