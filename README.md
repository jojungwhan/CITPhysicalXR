# CIT Physical XR Studio

This repository contains the completed **Milestone 6 classroom foundation**, the
Milestone 4 LEGO adapter, an additive Interaction Fabric compatibility slice,
the first RoboMaster/Leap ground-robot slice, and a Tuya-compatible smart-plug
slice. On top of the Milestone 0 foundation it provides the local runtime,
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

**No LEGO hub has been connected.** The adapter is written behind an injectable
Bluetooth boundary and every test runs against a hub simulated in memory; the
development host has no Bluetooth adapter. RoboMaster S1 and Leap now have an
out-of-process Fabric adapter and simulator-backed course flow, but this host is
missing the native Leap runtime artifacts, so physical HIL remains pending.
The smart-plug adapter has simulator evidence but has not contacted a physical
outlet. There is no Quest application (M5).

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
RoboMaster/Tello camera publishers and physical LEGO telemetry are still
separate hardware gates. See
`docs/operations/classroom-cameras-and-sensors.md` for the exact support matrix
instead of assuming a discovered device already has a live feed.

Source-checkout maintainers install the Desktop and Start menu shortcut once
with `pnpm hardware:install-button:windows`. This is installation work, not a
tutor startup step. Component-level PowerShell commands remain documented only
for hardware technicians and developers.

The device scan reuses Brain2Devices' Windows multi-radio Tello scanner, checks
MindWave/TGC, Ultraleap USB/service state, incoming RoboMaster STA broadcasts,
Agent Mesh, coding-agent executables, configured encrypted smart-plug profiles,
and paired LEGO candidates. It sends no actuator, flight, power, agent, media,
or SDK command. Instructor-only Tello and MindWave connection buttons use a
closed Brain2Devices allowlist; Tello additionally requires a grounded-aircraft
confirmation and still sends no flight command.

Real G2/Meta acceptance still requires the owner hardware procedure in
`docs/operations/agent-mesh-bridge.md`; simulator and software tests are not
reported as physical evidence.

## Tuya and Gosund smart plugs

The smart-plug adapter exposes only `power.switch.set { on: boolean }` and
`power.switch.state`. It uses local Tuya LAN control through pinned TinyTuya
1.20.0; vendor cloud commands and arbitrary datapoint writes are absent.
Gosund is supported only for a specific model that passes the Tuya-LAN
preflight—not by brand name alone.

Run the simulator in the shared UI first:

```powershell
pnpm hardware:plug:windows -- -Mode Preflight -SharedFabricRoot $fabricRoot
pnpm hardware:plug:windows -- -Mode Start -SharedFabricRoot $fabricRoot
pnpm hardware:plug:windows -- -Mode Verify -SharedFabricRoot $fabricRoot
pnpm hardware:plug:windows -- -Mode Stop -SharedFabricRoot $fabricRoot
```

Physical setup uses a DPAPI-protected local profile, an exact private IPv4
address, explicit `-Live`, a physical Fabric session, and the UI's Arm/Start
safety state. The adapter starts and shuts down in **off** state; it never
automatically turns a load on. Follow
`docs/operations/tuya-smart-plug-hardware.md` before connecting a real outlet.

## Tello and MindWave discovery

The preserved `brain2devices` implementation now has a CIT service launcher
and appears in the single classroom discovery screen:

```powershell
pnpm hardware:brain:windows -- -Mode Preflight
pnpm hardware:brain:windows -- -Mode Start
pnpm hardware:devices:windows -- -Mode Scan
```

Two or more stock Tellos require one physical USB Wi-Fi adapter per aircraft;
the screen lists radios separately from currently visible `TELLO-*`/`RMTT-*`
networks. The connection action performs only radio setup and SDK handshakes.
Canonical Fabric flight nodes and flight controls remain behind the later drone
safety slice. MindWave connection continues through ThinkGear Connector and no
raw biosignal is recorded by discovery.

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
- `adapters/lego-pybricks`: the LEGO hub adapter, framed protocol, capability discovery, and injectable Bluetooth boundary
- `adapters/robomaster-leap`: authenticated Fabric wrapper plus isolated Python 3.8 Leap and S1 workers
- `adapters/tuya-smart-plug`: authenticated Tuya-LAN adapter, simulator, exact boolean command, and safe-off boundary
- `firmware/lego-hub-agent`: the Pybricks program that runs on a hub
- `packages/test-harness`: reusable adapter shape assertion
- `apps/runtime-py`: the local runtime -- sessions, device registry, safety supervisor, command pipeline, event router, record/replay, audit, and the loopback API
- `apps/studio-web`: the Studio console -- device cards, session controls, drive controls, and a live event stream
- `apps/agent-mesh-bridge`: authenticated Agent Mesh compatibility adapter with a durable local outbox
- `course-packs/glasses-agent-control`: capability-based glasses/agent reference lesson
- `course-packs/gesture-ground-robot`: Leap semantic velocity to interchangeable ground-mobility role
- `course-packs/smart-plug-control`: approved electrical output assigned through the `classroom_plug` role
- `apps/quest-godot`: text-only Godot scene scaffold; no OpenXR or export setup
- `docs/REUSE_AUDIT.md`: exact external checkout evidence and reuse decisions

## Current limitations

- Read-only host discovery was exercised on Windows, but no physical actuator,
  headset, smart plug, or aircraft was connected or commanded. LEGO,
  RoboMaster/Leap, and smart-plug control paths still have simulator evidence
  only.
- Installing the current LEGO `hardware` extra breaks `pnpm license:check`; ADR-023 selected a transport split, which is not implemented yet and still blocks hardware bring-up.
- The runtime listens on loopback only. The new subprocess bridge executes one fixed worker path with an allowlisted JSON-lines contract; there is no arbitrary shell, eval endpoint, or public endpoint.
- Fake-device tests are contract evidence only; they are not Milestone 1 simulation or hardware evidence.
- The working DJI Python environment and pinned upstream checkout are integrated, but the built Leap bridge DLL, adjacent LeapC runtime, and tracking service are still absent on this host.
- Linux paths for the audited external repositories remain unresolved.
- Godot is not installed on the discovery host, so only static project structure is checked. No APK or Quest/OpenXR behavior is claimed.
- Agent CLI Mesh and the audited RoboMaster repositories have no owner licence at their inspected top level; none of their original code is copied here. The RoboMaster wrapper follows the owner's private noncommercial authorization.
- The GitHub Actions matrix covers Windows and Ubuntu with Python 3.11 and 3.13.

See `docs/MILESTONE_4_REPORT.md`, `docs/MILESTONE_3_REPORT.md`, and `docs/MILESTONE_1_REPORT.md` for what each milestone verified and what it deliberately leaves out, `docs/IMPLEMENTATION_PLAN.md` for requirement traceability and `docs/DECISIONS.md` for architecture decisions. The repository is licensed under Apache-2.0; dependency and external-source status is in `THIRD_PARTY_NOTICES.md` and `docs/LICENSING.md`.
