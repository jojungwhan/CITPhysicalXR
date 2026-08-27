# CIT Physical XR Studio

This repository contains the completed **Milestone 6 classroom foundation**, the
Milestone 4 LEGO adapter, an additive Interaction Fabric compatibility slice,
independent RoboMaster/Leap, Tello, MindWave, and LEGO Fabric adapters,
an independent Wonder Workshop Dash/Dot Bluetooth adapter, and a
cloud-independent Matter smart-plug path. On top of the
Milestone 0 foundation it provides the local runtime,
authoring environment, instructor/student isolation, projects, simulation,
record/replay, safety controls, and a loopback-first HTTP/WebSocket API.

On top of that runtime it adds the authoring half: a versioned project format, a
capability-driven Blockly toolbox, a deterministic blocks-to-readable-Python
generator with source maps, the `citxr` student API shared by generated and
handwritten code, and a Pyodide Web Worker that runs student programs behind a
five-call bridge.

Milestone 4 adds the first hardware adapter: LEGO SPIKE Prime, SPIKE Essential,
and MINDSTORMS Robot Inventor over Pybricks firmware. A bounded framed protocol,
a hub agent that stops itself when the computer goes quiet, capability discovery
from the hub's own port report, and instructor-gated autonomous programs.

**No LEGO hub has been connected during this implementation.** Its existing
adapter is now exposed as an independently supervised Fabric process with
single-UI exact-name/port setup, normalized sensor telemetry, optional bounded
ground mobility, and an in-memory simulator. RoboMaster S1 and Leap run as
separate out-of-process Fabric nodes and have a simulator-backed course flow,
but this host is missing the native Leap runtime artifacts, so physical HIL
remains pending. Tello and MindWave independently wrap the exact latest
Brain2Devices revision described below; their software-only Fabric paths are
tested, but no aircraft or headset was connected.
The Matter controller has passed a Windows/Bluetooth process smoke test. A real
controller-to-adapter-to-Fabric process slice also registered a simulated
`0x010A` outlet, completed a bounded active-session `off` lifecycle, stored its
normalized state event, and shut down cleanly. No physical outlet has been
commissioned yet. There is no Quest application (M5).

## Development setup

Prerequisites:

- Git 2.47 or newer
- Node.js 22.17.x
- pnpm 10.28.2
- uv 0.4.30
- CPython 3.11 or 3.13 (uv can install it)

From the repository root:

```text
pnpm install --frozen-lockfile
uv sync --all-packages --frozen
pnpm generate:check
pnpm schema:check
pnpm quest:check
pnpm format:check
pnpm lint
pnpm typecheck
pnpm build
pnpm test
pnpm license:check
pnpm sbom
```

## Running the runtime

```bash
pnpm --filter @citxr/studio-web build
uv run python -m cit_runtime                      # simulation, fake devices
uv run python -m cit_runtime --config class.yaml  # plus the hubs it names
```

Open <http://127.0.0.1:8791>. The runtime serves the built Studio at `/`, so that
one URL is both the console and the API. From it you can create a session, bind a
fake device, validate, drive it, watch device events stream in, and stop
everything.

## One Interaction Fabric UI for every integration

The Interaction Fabric is one local process, database, and UI for every
registered input, output, or bidirectional node. Leap, glasses, sensors,
robots, simulators, IoT devices, Codex, and Claude all use the same capability
registry; vendor implementations remain isolated behind authenticated adapter
WebSockets.

On the tutor computer, open **CIT Classroom Control** from the Windows Desktop
or Start menu and choose **Start classroom devices**. The native launcher signs
the current Windows user into the local tutor console automatically, uses port
`8766`, preserves or starts the existing Brain2Devices helper on `8765`, and
enables physical adapters while leaving every device and lesson disarmed.

If an older glasses-only Fabric already owns port `8766`, run
`pnpm hardware:glasses:windows -- -Mode Stop` once before this migration.

The button opens **CIT Classroom Control** automatically. Follow the five
on-screen steps: find devices, choose a lesson, assign devices, complete the
safety check, then teach. The discovery cards distinguish **Connected**,
**Found**, **Computer ready**, and **Setup needed** instead of treating a USB/network
match as an authenticated node. Use the same Windows button again to reopen it
without restarting any device. See
`docs/operations/device-discovery.md` and
`docs/operations/unified-fabric-console.md` for the complete workflow.

The same page now includes an authenticated latest-frame camera wall, local
on-demand YOLO object recognition, reviewed smart-plug actions, and normalized
sensor cards. Meta snapshots use the optional existing Android companion;
Brain2Devices Tello feeds and the independent RoboMaster SDK camera publisher
now publish through the same in-memory camera wall. The page also renders a
reduced live Leap hand view while all physical device HIL remains separate
hardware gates. See
`docs/operations/classroom-cameras-and-sensors.md` for the exact support matrix
instead of assuming a discovered device already has a live feed.

Source-checkout maintainers install the Desktop and Start menu shortcut once
with `pnpm hardware:install-button:windows`. This is installation work, not a
tutor startup step. Component-level PowerShell commands remain documented only
for hardware technicians and developers.

For a new Windows computer at a classroom or business site, stay in this same
page: choose **Install another PC**, download the verified Windows setup ZIP and
site template, copy them by USB or a trusted private transfer, extract the ZIP,
and double-click `Install-CIT.cmd`. The four bilingual steps explain new-network
and device pairing. The site template contains names only; tokens, Wi-Fi
passwords, Matter controller state, device credentials, logs, and recordings
are never copied. See
`docs/operations/install-another-windows-pc.md`.

This is a network-assisted installer. Internet is required while it installs
pinned Microsoft/OpenJS/Python/npm/PyPI/Git prerequisites, but no proprietary
smart-plug cloud or account is used for classroom control. The page downloads
through authenticated memory, verifies SHA-256 before saving, and serves only a
prebuilt artifact; an HTTP request can never invoke a shell or build.

Source-checkout technicians can still use the guided business installer
directly. The simplest fallback is to double-click
`install-cit-business-site.cmd`; it installs PowerShell 7 when needed, uses the
initial names `business-site` / `classroom-a`, and opens Classroom Control when
setup finishes.

Technicians can choose different logical names in PowerShell 7:

```powershell
pwsh -NoProfile -STA -File .\tools\hardware\install-business-site.ps1 `
  -SiteId cit-business -RoomId classroom-a -InstallPrerequisites
```

The installer adds the local Matter controller, exact-pinned Brain2Devices,
the LEGO, Sphero BOLT, and Dash/Dot Bluetooth transports, asks once for
classroom Wi-Fi, creates the same tutor button, and builds the authenticated
handoff ZIP for the next computer. See
`docs/operations/matter-smart-plug-windows.md`.
Brain2Devices is cloned into CIT's per-user application-data directory and that
managed path is saved in the site profile, so moving the CIT repository does
not repoint tutors at a developer checkout.

The device scan reuses Brain2Devices' Windows multi-radio Tello scanner, checks
MindWave/TGC, Ultraleap USB/service state, incoming RoboMaster STA broadcasts,
exact Sphero BOLT `SB-XXXX` and Dash/Dot BLE advertisements,
Agent Mesh, coding-agent
executables, commissioned Matter plug endpoints, and exact-name LEGO profiles. It sends no actuator, flight, power, agent, media,
or SDK command. Instructor-only Tello and MindWave connection buttons use a
closed Brain2Devices allowlist and then register separate canonical Fabric
nodes; Tello additionally requires a grounded-aircraft confirmation. It
exposes telemetry, land, and emergency stop only—never takeoff or movement.

Even R1, Even G2, and Meta Ray-Ban have separate setup and status cards because their
companion and media features differ. They intentionally share the authenticated
Agent Mesh transport. R1 is input-only and publishes structured touch gestures;
see `docs/operations/even-r1-smart-ring.md`. Real wearable acceptance still
requires the owner hardware procedure in `docs/operations/agent-mesh-bridge.md`;
simulator and software tests are not reported as physical evidence.

## Cloud-free Matter smart plugs

New sites should use a Wi-Fi plug that explicitly carries the Matter logo and a
Matter setup code. The **Matter smart plugs** card in Classroom Control
commissions it into the CIT-owned
local fabric and exposes `power.switch.set { on: boolean }` and
`power.switch.state`. Tapo P110M is explicitly guided in the UI and needs no
Tapo app or TP-Link account for this direct route. If its firmware exposes the
standard Matter 1.3 electrical-measurement clusters, the same generic adapter
also publishes `telemetry.power.electrical`; otherwise on/off remains fully
available. This path uses no proprietary vendor app, account, API, cloud,
device ID, or local key.

The plug must actually run Matter firmware; branding alone is not enough. See
`docs/operations/matter-smart-plug-windows.md` for installation, real-hardware
testing, and moving the setup to another Windows computer.

## Tello and MindWave through the latest Brain2Devices

The external source is pinned once in `config/external-sources.yaml` to
`jojungwhan/brain2devices` commit
`536a256ef3f4b3182a74891b5971e9124ed051b0`, verified as the latest
`origin/main` revision on 2026-08-23. The business installer checks out exactly
that revision into its own Python 3.12 environment; every launcher fails closed
if the revision drifts or the checkout has local/untracked changes. The source
stays outside this repository and vendor imports stay in a child process.

That v0.6.35 revision adds upstream blink feedback, Tello video with the Windows
UDP 11111 firewall fix, and an optional EEG-triggered Tello demo. MindWave stays
a vendor-labelled, publish-only node and Tello stays a telemetry/land/emergency
node. A third independent compatibility plugin exposes only the upstream
one-shot demo arm/stop/status contract through deterministic Fabric safety,
explicit lesson arming, instructor priority, and the on-screen flight checks.

Tutors do not run the commands below. Open **CIT Classroom Control**, choose
**Start classroom devices**, then **Find devices**. Use the Tello or MindWave
card's connect button. The software-only technician equivalent is:

```powershell
pnpm hardware:brain:fabric:windows -- -Mode Preflight -Device All -Simulation
pnpm hardware:brain:fabric:windows -- -Mode Start -Device All -Simulation
pnpm hardware:brain:fabric:windows -- -Mode Stop -Device All
```

Two or more stock Tellos require one physical USB Wi-Fi adapter per aircraft;
the screen lists radios separately from currently visible `TELLO-*`/`RMTT-*`
networks. The Tello action performs radio setup and SDK handshakes, registers
one node per connected aircraft, and joins one shared unarmed monitoring
session used by the MindWave and LEGO sensor adapters as well.
Only land and emergency stop can dispatch while unarmed; takeoff and movement
are neither advertised nor accepted. MindWave uses ThinkGear Connector and
publishes only explicitly vendor-labelled eSense/signal/blink values. Raw EEG
is never emitted or recorded. See
`docs/operations/brain2devices-fabric.md` for installation, simulation, and the
physical evidence checklist.

## LEGO hub setup in the same UI

Install Pybricks firmware once using the normal Pybricks tooling and give every
hub a unique classroom Bluetooth name. In **Find devices**, open the LEGO card,
enter that exact name, select the model, and describe each connected port. A
sensor-only hub is valid. CIT never connects to the nearest anonymous hub and
joins only the shared unarmed monitoring session; it advertises ground mobility
only when at least two ports are motors. No motor command is issued during
setup. Do not pair a Pybricks hub in Windows Settings; remove an existing
Windows pairing and connect it through CIT/Pybricks by its exact advertised
name.

## Sphero BOLT in the same UI

Charge BOLT, remove it from its cradle to wake it, close Sphero apps, and choose
**Find devices**. Select the exact `SB-XXXX` name and choose **Connect selected
BOLT robots**. Do not pair BOLT in Windows Settings. CIT connects directly over
local BLE and uses no Sphero account or cloud service.

Connection starts sensor monitoring with controls locked. After enabling
physical controls on a clear floor, point the blue tail light toward the tutor
and choose **Set this direction as forward**. The arrows request 0.10 m/s short
nudges, the adapter rejects angular velocity and any vector above 0.20 m/s, and
it stops locally after 350 ms. RGB/off and sensor information use the same
unified page. See `docs/operations/sphero-bolt-windows.md`. Real firmware HIL is
still pending and must pass that checklist before classroom movement is claimed.

## Wonder Workshop Dash and Dot in the same UI

Switch on the robots, close any Wonder/Blockly app that is connected to them,
then choose **Find devices**. The Dash and Dot card lists exact visible names
and signal levels. Select up to four robots and choose **Connect selected
robots**; no shell command, vendor account, or cloud service is required.

Dot shows lights, three fixed sound cues, and sensors. Dash additionally shows
short movement nudges, an always-visible stop, and bounded head controls. The
first direct output command prepares the local control session automatically;
every Dash movement expires at the adapter after 350 ms. See
`docs/operations/wonder-workshop-dash-dot.md` for real-hardware checks.

## RoboMaster S1 and Leap Motion

The latest owner-selected
`jojungwhan/robomaster-gesture-control` revision is pinned at
`3c213c110b0cdf2912985bfcde442d67092b98f0`. CIT launches its gesture, LeapC,
DJI, stock-S1, and command-pump code under the existing Python 3.8 environment
and exposes independent Leap and S1 capability nodes. Vendor SDKs never enter
the orchestration process.

Run the complete software-only route through the shared console first (using
`$fabricRoot` from above):

```powershell
pnpm hardware:robot:windows -- -Mode Preflight -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:robot:windows -- -Mode Start -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:robot:windows -- -Mode Verify -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:robot:windows -- -Mode Stop -SharedFabricRoot $fabricRoot -FabricPort 8766
```

Physical execution requires starting the shared console with `-AllowPhysical`,
passing the explicit `-Live` flag to the adapter, and completing the Fabric
**Arm** and **Start** transitions. See
`docs/operations/robomaster-leap-hardware.md` before connecting wheels to the
floor.

The runtime binds the loopback interface and refuses to bind a routable one
without an explicit override. Its CORS allowlist contains no remote origin, so a
Studio copy served from another host resolves the API to its own origin, finds
nothing there, and reports the runtime unreachable. That is deliberate: a page on
a public website must not be able to drive a robot on someone's desk.

A runtime can be published behind a proxy that its owner configured, under a
path: `--url-prefix /citxr` serves everything under that path and refuses
anything outside it, for a proxy that forwards the path rather than rewriting
it. `docs/HOSTING.md` describes the one deployment that exists — a
simulation-only runtime behind Cloudflare Access — and, more importantly, why a
hub does not go behind it.

## Configuration

`config/default.yaml` is safe, local-only, and keeps physical devices and Agent Mesh disabled. `config/examples/local-foundation.example.yaml` records the Windows checkout paths found during the audit, and `config/examples/lego-classroom.example.yaml` shows a room with one LEGO hub. A configuration that names physical devices while `physicalDevicesEnabled` is false is refused at startup rather than ignored. Copy an example to a location outside the repository before making machine-specific changes; `config/local.yaml`, `config/*.local.yaml`, and environment files are ignored.

Platform paths are stored separately and never translated between Windows and Linux syntax. Missing platform entries fail with an actionable error. Configuration accepts secret-store metadata, not literal credentials.

## Foundation layout

- `packages/protocol-schema`, `protocol-ts`, and `protocol-py`: protocol v1 source and generated bindings
- `packages/safety-core`: command ledger, expiry, leases, and foundation denial policy
- `packages/device-simulator`: non-hardware adapter contract and fake S1, Leap, LEGO, and Quest devices
- `packages/integration-sdk-py`: adapter transport/lifecycle helpers plus generated capability/source catalogs
- `adapters/lego-pybricks`: the LEGO hub adapter, framed protocol, capability discovery, and injectable Bluetooth boundary
- `adapters/robomaster-leap`: independently supervised Leap and S1 Fabric processes plus isolated Python 3.8 vendor workers
- `adapters/tello`: safe Tello telemetry/land/emergency adapter around Brain2Devices
- `adapters/mindwave-mobile2`: publish-only, vendor-labelled Brain2Devices MindWave adapter
- `apps/matter-controller`: pinned loopback-only Open Home Foundation Matter controller
- `adapters/matter-smart-plug`: cloud-independent Matter `0x010A` plug adapter and safe-off boundary
- `adapters/sphero-bolt`: exact-selection BOLT BLE adapter, simulator, sensors, bounded directional roll, and aim control
- `adapters/wonder-workshop`: exact-selection Dash/Dot BLE adapter, simulator, sensors, and model-specific bounded controls
- `firmware/lego-hub-agent`: the Pybricks program that runs on a hub
- `packages/test-harness`: reusable adapter shape assertion
- `apps/runtime-py`: the local runtime -- sessions, device registry, safety supervisor, command pipeline, event router, record/replay, audit, and the loopback API
- `apps/studio-web`: the Studio console -- device cards, session controls, drive controls, and a live event stream
- `apps/agent-mesh-bridge`: authenticated Agent Mesh compatibility adapter with a durable local outbox
- `course-packs/glasses-agent-control`: capability-based glasses/agent reference lesson
- `course-packs/glasses-device-control`: confirmed G2/Meta controls to assigned ground robots, local Matter smart plugs, and the independently armed Tello fleet
- `course-packs/gesture-ground-robot`: Leap semantic velocity to interchangeable ground-mobility role
- `course-packs/smart-ring-device-control`: Even R1 semantic gestures to assigned ground outputs and an independently armed Tello sequence
- `course-packs/smart-plug-control`: approved electrical output assigned through the `classroom_plug` role
- `apps/quest-godot`: text-only Godot scene scaffold; no OpenXR or export setup
- `docs/REUSE_AUDIT.md`: exact external checkout evidence and reuse decisions

## Current limitations

- Read-only host discovery was exercised on Windows, but no physical actuator,
  headset, smart plug, or aircraft was connected or commanded in this change.
  Tello, MindWave, LEGO, Sphero BOLT, RoboMaster/Leap, and smart-plug paths therefore still
  have software/simulator evidence only.
- The business installer places Pybricks Bluetooth dependencies in the local
  hardware environment. Their optional transitive licence metadata remains a
  documented distribution concern; it does not weaken the runtime boundary or
  justify claiming physical HIL.
- The runtime listens on loopback only. The new subprocess bridge executes one fixed worker path with an allowlisted JSON-lines contract; there is no arbitrary shell, eval endpoint, or public endpoint.
- Fake-device tests are contract evidence only; they are not Milestone 1 simulation or hardware evidence.
- The working DJI Python environment and pinned upstream checkout are integrated, but the built Leap bridge DLL, adjacent LeapC runtime, and tracking service are still absent on this host.
- Linux paths for the audited external repositories remain unresolved.
- Godot is not installed on the discovery host, so only static project structure is checked. No APK or Quest/OpenXR behavior is claimed.
- Agent CLI Mesh and the audited RoboMaster repositories have no owner licence at their inspected top level; none of their original code is copied here. The RoboMaster wrapper follows the owner's private noncommercial authorization.
- The GitHub Actions matrix covers Windows and Ubuntu with Python 3.11 and 3.13.

See `docs/MILESTONE_4_REPORT.md`, `docs/MILESTONE_3_REPORT.md`, and `docs/MILESTONE_1_REPORT.md` for what each milestone verified and what it deliberately leaves out, `docs/IMPLEMENTATION_PLAN.md` for requirement traceability and `docs/DECISIONS.md` for architecture decisions. The repository is licensed under Apache-2.0; dependency and external-source status is in `THIRD_PARTY_NOTICES.md` and `docs/LICENSING.md`.
