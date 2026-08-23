# Brain2Devices Tello and MindWave integration

This runbook covers the independent CIT Tello and MindWave adapters, the
separate bounded MindWave demo and ordered-fleet controllers, and the Tello
media publisher that wrap the existing Brain2Devices hardware implementation.
Tutors use only **CIT Classroom Control**; the commands below are technician
diagnostics.

## Pinned source and installation

CIT pins `https://github.com/jojungwhan/brain2devices.git` at
`536a256ef3f4b3182a74891b5971e9124ed051b0`. Local `origin/HEAD` was queried
again on 2026-08-23 and returned that same commit. `config/external-sources.yaml` is the source
of truth; generated Python and PowerShell catalogs must match it.

This is Brain2Devices 0.6.35, including the Windows UDP 11111 video-firewall
fix, local Tello MJPEG feeds, and the one-shot EEG automatic-demo gate. CIT
keeps the MindWave and Tello hardware projections independent. A third plugin
wraps only that exact combined demo as a high-level arm/stop contract. A fourth,
independent `cit.brain2devices-fleet` plugin owns one tutor-armed ordered launch
and never exposes unrestricted flight commands.

On a new Windows 11 computer, double-click `install-cit-business-site.cmd`.
The installer obtains Git and Python 3.12 when necessary, checks out exactly the
pinned commit under the current Windows user's CIT application-data directory,
creates Brain2Devices' independent virtual environment, installs the pinned
Windows dependency set, runs its hardware self-test, and records the exact path
and revision in the local site profile. It does not overwrite, detach, or switch
an existing checkout; technicians must provide a separate clean checkout at the
characterized revision when overriding the managed path. Physical startup
rejects tracked or untracked source changes. No Brain2Devices source is copied
into CIT.

## Tutor workflow

1. Open **CIT Classroom Control** and choose **Start classroom devices**.
2. Choose **Find devices**.
3. For MindWave, pair the headset, start ThinkGear Connector on
   `127.0.0.1:13854`, then choose **Connect headset**.
4. For Tello, remove or guard propellers, keep every aircraft grounded, attach
   one enabled USB Wi-Fi radio per stock access-point-mode aircraft, tick the
   grounded confirmation, then choose **Connect grounded drones**.
5. Wait for each card to say **Connected**. The Classroom readings section now
   shows actual semantic telemetry rather than discovery guesses, and each
   streaming Tello appears in **Live cameras**.
6. For a sequential fleet, connect at least two Tellos. Confirm that each has a
   stable independent route; stock access-point-mode aircraft normally require
   one enabled USB Wi-Fi adapter each. In **Multi-input drone sequence**, arrange
   the launch order and select the permitted trigger nodes.
7. To add Leap, G2, or Meta, choose **Find devices** after the drone fleet is
   connected, then choose the matching **Connect** action. CIT attaches those
   input-only nodes to this same lesson. It does not start RoboMaster or select a
   coding agent for the fleet path.
8. Practice the fleet panel in Simulation. Choose **Arm this sequence once**,
   then **Start now**. The state must progress to **Completed** and the confirmed
   count must reach the selected total in order. The arm is consumed once and
   expires after 60 seconds if no approved trigger arrives.
9. For MindWave flight practice, open the bounded demo panel. Run Simulation
   first. For real hardware, start and arm the physical lesson, choose the
   signal/threshold, complete all three instructor checks, then choose **Arm
   one-shot flight demo**.

The connection actions reconcile the adapter set after every device finishes.
If only one device is connected, only that independent adapter is started. As
soon as both Tello and MindWave are connected, CIT starts the Tello, MindWave,
and bounded-demo adapters together, regardless of which device was connected
first.

Connection joins or creates one shared **Device monitoring** session.
MindWave, every grounded Tello, and independently connected LEGO sensor hubs
therefore appear together in the same Classroom readings view. Physical
monitoring may start without arming only because all bound requirements are
informational and the one fleet flow is dormant behind the complete
`target_is_armed` safety guard set. The normal command gate independently
rejects physical flight while unarmed. The Tello panel exposes
only **Land** and a separately confirmed **Emergency motor stop**; that adapter
does not advertise takeoff or movement. MindWave consumes no commands. The
independent demo controller exposes only `mobility.flight.brain_demo.arm` and
`mobility.flight.brain_demo.stop`; arming requires instructor priority, an
active and armed physical session, three explicit confirmations, and all
upstream signal-quality, freshness, and landed checks.

The fleet controller exposes only `mobility.flight.fleet_sequence.arm`,
`.start`, and `.stop`. Physical arm requires instructor priority, an active and
armed session, two to eight selected aircraft, four confirmations, a 20–100%
battery floor, and a 1–15 second interval. The controller confirms each aircraft
reports `flying` before proceeding. A rejection, disconnect, timeout, stop, or
shutdown cancels later launches and requests landing for every confirmed or
possibly launched aircraft. Its one-shot arm expires independently after 60
seconds, even if the enclosing lesson session remains armed.

Approved remote triggers are deliberately narrow:

- Leap: make an open-hand gesture, then enter the tracked pinch/`DRIVING`
  state. Only the rising transition emits one intent; holding the pinch does not
  emit repeats.
- G2 or Meta English: say exactly **Start drone sequence**, **Launch drone
  sequence**, or **Take off drones**.
- G2 or Meta Korean: say exactly **드론 순차 이륙** or **드론 이륙 시작**.

These triggers only consume the tutor's current one-shot arm. They cannot select
aircraft, change bounds, arm the session, or send a low-level flight command.

## Technician simulation

Start the shared Fabric first, then run the independent adapters without hardware:

```powershell
$fabricRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"
pnpm hardware:brain:fabric:windows -- -Mode Preflight -Device All -Simulation -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:brain:fabric:windows -- -Mode Start -Device All -Simulation -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:brain:fabric:windows -- -Mode Status -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:brain:fabric:windows -- -Mode Stop -SharedFabricRoot $fabricRoot -FabricPort 8766
```

Each Tello, MindWave, bounded-demo, and fleet controller has separate credentials,
plugin IDs, node IDs, logs, and processes. The ordinary Tello worker imports
only the Brain2Devices Tello port, while the MindWave worker imports only its
headset port. The third compatibility node talks only to the characterized
loopback service because the preserved legacy demo intentionally coordinates
both devices. Shared CIT code is limited to canonical capability data and
Fabric transport/lifecycle mechanics. Simulation creates three Tello nodes and
one fleet controller so the same page can exercise order, arm, start, cancel,
and status without hardware.

To validate that topology together with a simulated MindWave one-shot demo,
three-aircraft fleet, and sensor-only LEGO node in one disposable Fabric, run
`pnpm test:device-slice:windows`. The script drives both bounded controller
contracts through the public Fabric API, uses a dedicated random directory under
the Windows temporary directory, never enables physical dispatch, stops only the
exact processes it started, and cleans up.

## Physical preflight

```powershell
$fabricRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"
pnpm hardware:brain:windows -- -Mode Preflight
pnpm hardware:brain:fabric:windows -- -Mode Preflight -Device All -SharedFabricRoot $fabricRoot -FabricPort 8766
```

Preflight verifies the Fabric health endpoint, external Python, required
Brain2Devices hardware ports, exact Git revision, independent process shape,
and Tello's reduced capability set. It does not connect or actuate hardware.
The simulator also publishes a visible Tello camera tile and completes a fake
one-shot trigger without issuing any physical command.

## First real-hardware validation

Use a cleared indoor flight cage or other approved area. Keep students outside
it and have a second adult observe the stop controls. Validate one aircraft at a
time before attempting a fleet. For an ordered fleet, every selected Tello must
remain reachable through its own stable route for takeoff confirmation and
landing; do not use rapid single-radio Wi-Fi handoff as the fleet control path.
Power off every aircraft that is not intentionally part of the test.

1. With propellers removed, use **Find devices**, confirm every aircraft is
   grounded, and choose **Connect grounded drones** and **Connect headset**.
   Verify Tello telemetry, changing eSense readings, signal quality, and blink
   strength on the unified page. Do not arm the lesson.
2. Verify a Tello camera tile appears. The first physical start may show one
   Windows UAC prompt so Brain2Devices can create an exact-program inbound UDP
   11111 rule limited to local-subnet traffic. Rejecting it may disable video,
   but must not enable or block flight controls. Confirm frames stop when the
   adapter stops and no image file is written to the Fabric data directory.
3. Run the panel in **Simulation** and confirm one selected threshold completes
   once, status reaches **Simulated completed**, and no networked aircraft
   changes state.
4. Power down, reinstall and inspect propellers only for the approved flight
   test, then place the intended aircraft in the cleared area. Restart physical
   devices, verify fresh battery and landed state, and keep **Land** and **Stop
   all devices** visible.
5. Select a 2-second dwell and a deliberately reachable but supervised
   threshold. Choose **Enable physical controls**, complete all three checks in
   the demo panel, and choose **Arm one-shot flight demo**. Arming alone must not
   take off. A value equal to the threshold must not qualify; only a value
   strictly above it qualifies.
6. Confirm the trigger disarms before the demo begins, MindWave disconnects
   before the Wi-Fi handoff, the workflow starts at most once, and status plus
   camera/telemetry remain truthful. Land using the dedicated control. Use
   **Emergency motor stop** only when an immediate fall is safer than continued
   flight.
7. Repeat failure checks with no fresh reading, poor signal quality, a non-landed
   aircraft, a cleared confirmation, loss of the headset, and adapter stop.
   Every case must reject or stop without retrying takeoff.

For the first multi-aircraft test, use exactly two aircraft and the maximum
15-second interval. Verify both are listed as connected and landed with fresh
battery data, enable physical controls, complete all four fleet confirmations,
and arm once. First use **Start now**; confirm aircraft 1 reports flying before
aircraft 2 receives takeoff. Use **Stop & land selected fleet** and verify both
land. Trigger within 60 seconds of arming. Repeat separately with Leap, G2, and
Meta. Finally inject a second-aircraft
rejection, input retry, adapter stop, and one route loss; no later takeoff may be
sent and every possibly airborne aircraft must receive a landing request.

Do not perform controlled hardware replay during this validation. Fabric replay
remains dry-run by default.

## Evidence still required

Software contract, simulator, API-projection, launcher, static-analysis, and
isolated process tests are automated. Before classroom use, record physical
evidence for:

- headset pairing, TGC loss/recovery, bad signal, disconnect, and absence of
  raw EEG persistence;
- each Wi-Fi radio/aircraft mapping, telemetry rate, delayed/out-of-order data,
  link loss, grounded land, emergency stop, inbound UDP 11111 firewall rule,
  live-video recovery, and adapter/process crash;
- the one-shot gate's exact threshold behavior, signal-quality/freshness gate,
  automatic disarm, headset disconnect, flight-area procedure, cancellation,
  and instructor emergency response;
- observed command lifecycle semantics, since the preserved compatibility API
  can acknowledge receipt before an aircraft finishes an action;
- local p95 dispatch and UI feedback latency.
- two-to-eight-aircraft ordering, per-aircraft airborne confirmation, route
  loss, partial rejection, cancellation, one-shot consumption, and landing;
- physical Leap open-hand-to-pinch, exact G2 phrase, and exact Meta phrase
  round trips in the shared session, including disconnect and duplicate input.

Never add generic takeoff or continuous movement to the Tello, MindWave, or
wearable adapters as a shortcut. The two compatibility controllers are limited
to their characterized one-shot workflows and must not become generic flight
passthroughs.

## Moving to another business location

Install CIT with the business installer on the new Windows operator account;
do not copy DPAPI credential files. Use the new site's logical site/room names,
pair MindWave in Windows, install/start TGC, and attach the classroom USB Wi-Fi
radios. The installer reproduces the exact Brain2Devices code/dependencies.
Device Bluetooth pairing and Windows network-interface identities are
machine-local and must be established again.
