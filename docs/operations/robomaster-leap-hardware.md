# RoboMaster S1 and Leap Motion hardware runbook

Status: the adapter, simulator, course flow, UI, and Python 3.8 process boundary
are implemented. This development host still lacks
`build/leap_hand_bridge.dll`, its adjacent `LeapC.dll`, and a running Ultraleap
service, so no physical movement is claimed yet.

## What the launcher controls

`tools/hardware/robomaster-leap-hardware-test.ps1` attaches to the shared local
Fabric, creates a `gesture-ground-robot` session, registers separate Leap and
S1 nodes, assigns logical roles, and uses the same UI as glasses and coding
agents at <http://127.0.0.1:8766/fabric>. The adapter launcher stops only its
own session and processes.

The default path is software-only:

```powershell
pnpm hardware:fabric:windows -- -Mode Start
$fabricRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"
pnpm hardware:robot:windows -- -Mode Preflight -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:robot:windows -- -Mode Start -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:robot:windows -- -Mode Verify -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:robot:windows -- -Mode Stop -SharedFabricRoot $fabricRoot -FabricPort 8766
```

It uses the real upstream `DryRunRobot` and `CommandPump`, but a generated
semantic gesture pulse. `Verify` should report at least one gesture event, one
bounded robot-command event, and one `SUCCEEDED` lifecycle.

The Windows **CIT Classroom Control** button and the robot launcher open the
same dedicated app screen with automatic local sign-in. Reopening replaces the
previous CIT-owned window, so adapter connections do not accumulate browser
tabs. Normal browser windows are untouched, and the adapter is not restarted.

Choose **Gesture-controlled robot**. Confirm the gesture controller and
classroom robot show **Ready**, complete the safety check, and start the lesson.
Use **Stop robot** for a harmless output test before allowing movement.

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
SDK mode advertises the S1's native LED capability, so the G2 assigned-output
menu can set the bounded classroom color. The Windows-app transport does not
advertise LED control because its documented keyboard boundary exposes only
movement.

For a stock S1 using its Windows app, open the live drive view first and select
`-RobotTransport s1-app`. The upstream focus interlock releases W/A/S/D if the
window loses focus; run the app and launcher at the same privilege level.

Use a clear floor area, lift the drive wheels for the first test, keep the
instructor at the computer, and identify the physical power switch before arm.

## Start a live session

```powershell
pnpm hardware:fabric:windows -- -Mode Start -AllowPhysical
$fabricRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"
pnpm hardware:robot:windows -- -Mode Preflight -SharedFabricRoot $fabricRoot -FabricPort 8766 -Live -RobotTransport sdk -Connection sta
pnpm hardware:robot:windows -- -Mode Start -SharedFabricRoot $fabricRoot -FabricPort 8766 -Live -RobotTransport sdk -Connection sta -RobotIp 192.168.2.1 -MaxSpeed 0.10 -MaxYaw 10
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
pnpm hardware:robot:windows -- -Mode Stop -SharedFabricRoot $fabricRoot -FabricPort 8766
```

The UI also has **Test robot stop**. It sends only the allowlisted
`mobility.ground.stop` action and is safe to use as an output-path check.

## Acceptance evidence

After a deliberate low-speed gesture and release:

```powershell
pnpm hardware:robot:windows -- -Mode Verify -SharedFabricRoot $fabricRoot -FabricPort 8766 -Live
```

Record the robot firmware, Leap controller model, Ultraleap software version,
connection mode, measured end-to-end latency, and operator. Do not mark the HIL
gate complete until pinch release, tracking loss, adapter termination, and UI
emergency stop have each produced a physical stop.

Adapter logs and state remain under:

```text
%LOCALAPPDATA%\CITPhysicalXR\robomaster-leap-hardware-test
```

The shared Fabric database and UI logs remain under
`%LOCALAPPDATA%\CITPhysicalXR\interaction-fabric`.

No raw Leap frames are stored.
