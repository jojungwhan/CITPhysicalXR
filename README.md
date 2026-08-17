# CIT Physical XR Studio

This repository is at **Milestone 4: LEGO**. On top of the Milestone 0 foundation (versioned protocol models, validation and configuration contracts, fail-closed safety primitives, four in-memory adapter fakes, cross-platform CI) it adds a working local runtime and a Studio console that drives it: program sessions, a device registry, an independent safety supervisor, a single command pipeline, event routing, record and replay, and a loopback-only HTTP/WebSocket API.

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
development host has no Bluetooth adapter. There is still no RoboMaster S1 or
Leap adapter (M2) and no Quest application (M5).

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
- `firmware/lego-hub-agent`: the Pybricks program that runs on a hub
- `packages/test-harness`: reusable adapter shape assertion
- `apps/runtime-py`: the local runtime -- sessions, device registry, safety supervisor, command pipeline, event router, record/replay, audit, and the loopback API
- `apps/studio-web`: the Studio console -- device cards, session controls, drive controls, and a live event stream
- `apps/agent-mesh-bridge`: optional bridge policy only; no transport
- `apps/quest-godot`: text-only Godot scene scaffold; no OpenXR or export setup
- `docs/REUSE_AUDIT.md`: exact external checkout evidence and reuse decisions

## Current limitations

- No hardware was contacted or modified. The LEGO adapter is real code against a simulated hub; `ble.py` has never run.
- Installing the LEGO `hardware` extra breaks `pnpm license:check` on that machine. The decision is open (ADR-023) and blocks hardware bring-up.
- The runtime listens on loopback only. There is no arbitrary shell, subprocess bridge, eval endpoint, or public endpoint.
- Fake-device tests are contract evidence only; they are not Milestone 1 simulation or hardware evidence.
- The working DJI Python environment was found, but the expected built Leap bridge DLL, Leap runtime/service, and owner-designated integrated checkout were not found.
- Linux paths for the audited external repositories remain unresolved.
- Godot is not installed on the discovery host, so only static project structure is checked. No APK or Quest/OpenXR behavior is claimed.
- Agent CLI Mesh and the audited RoboMaster repositories have no owner licence at their inspected top level; none of their original code is copied here.
- A clean Ubuntu 24.04 Docker verification passes on this host. The GitHub Actions matrix is defined but cannot report an external run until the repository is pushed.

See `docs/MILESTONE_4_REPORT.md`, `docs/MILESTONE_3_REPORT.md`, and `docs/MILESTONE_1_REPORT.md` for what each milestone verified and what it deliberately leaves out, `docs/IMPLEMENTATION_PLAN.md` for requirement traceability and `docs/DECISIONS.md` for architecture decisions. The repository is licensed under Apache-2.0; dependency and external-source status is in `THIRD_PARTY_NOTICES.md` and `docs/LICENSING.md`.
