# Current State

Status: reconciled against upstream `main` commit `b74bb2b`, 2026-08-21.

This document supersedes the pre-reconciliation working-tree description. The
full pre-upstream implementation remains recoverable at local commit `db29f15`
on `backup/cit-fabric-pre-upstream-20260821`.

## CITPhysicalXR

The upstream repository already contains the stable Milestone 0, 1, 3, 4, and
6 work:

- versioned protocol and configuration schemas, generated Python/TypeScript
  bindings, safety primitives, CI, licensing, and secret gates;
- a local FastAPI classroom runtime with exact device routing, sessions,
  arbitration, watchdogs, authorization, audit, record/replay, and stop-all;
- Blockly and readable student Python authoring with a constrained browser
  runtime;
- a Pybricks LEGO adapter, framed hub protocol, hub watchdog, and simulated BLE
  boundary;
- instructor/student isolation, projects, autosave, exports, and a bilingual
  Studio;
- path-prefixed simulation hosting protected by independent join and instructor
  passcodes.

The clean upstream baseline passed all repository gates before reconciliation:
`393` Python tests and `124` TypeScript tests.

## Additive Interaction Fabric slice

The glasses/coding-agent slice is layered alongside the classroom runtime. It
does not replace or import the upstream runtime internals.

```text
G2 / Meta / Codex / Claude in Agent Mesh
        |
        | authenticated compatibility API
        v
Agent Mesh bridge (Node.js)
        |
        | versioned authenticated adapter WebSocket
        v
Shared CIT Interaction Fabric (one FastAPI process + SQLite + UI)
        |
        +-- capability/node registry
        +-- logical lesson roles and bounded flow mapping
        +-- command lifecycle, arbitration, health, audit
        +-- same-origin /fabric instructor console
```

The Windows shared launcher owns this single Fabric process. Glasses/agent and
Leap/RoboMaster launchers attach with the protected shared credential while
retaining ownership only of their own adapter processes and sessions. The UI
groups every registered node as input-only, output-only, or bidirectional and
shows both its published and consumed capabilities.

The service starts through
`cit_runtime.fabric_service:create_persistent_fabric_app`. It defaults to
simulation/informational behavior. Its authenticated adapter dispatcher can
reach physical nodes only when the local process was explicitly started with
physical Fabric enabled; the persistent default remains fail closed.
Credentials are independently scoped and stored only as domain-separated
hashes. Agent Mesh remains responsible for the existing Codex, Claude, G2, and
Meta implementations; no private Agent Mesh source is copied into this
Apache-2.0 repository.

Compatibility mode deliberately observes the prompt already delivered by
Agent Mesh and reports `AGENT_MESH_ALREADY_DISPATCHED`; it never submits the
prompt a second time. Native pre-dispatch agent selection remains a later
cross-repository cutover.

## Other repositories inspected

- `D:\dev\glasses2CLI`: existing Agent Mesh implementation for G2, Meta,
  Codex, Claude, durable commands, completions, process supervision, and scoped
  wearable credentials. Reuse through an authenticated boundary only.
- `D:\dev\brain2devices`: MindWave Mobile 2 and Tello integrations with
  simulators and safety gates. Retain as an out-of-process candidate because
  of its Python and hardware dependencies.
- `D:\dev\robomaster-gesture-control-reference`: Leap/Ultraleap gesture and
  RoboMaster behavior implementation, pinned at `3c213c1...` and wrapped by
  separate Python 3.8 JSON-lines workers; original source remains external.
- `D:\dev\robomasterCITCourse`: additional RoboMaster classroom and mission
  behavior reference, also without a selected reusable source license.

## Physical-hardware status

- LEGO: production adapter and hub firmware exist upstream, but no real hub has
  been connected and the optional transport dependency/licensing split remains
  outstanding.
- G2 and Meta: the software compatibility path and Windows launcher exist; the
  owner hardware round trip is still required.
- RoboMaster S1 and Leap: software adapter, semantic course flow, UI controls,
  upstream dry-run process test, and hardware launcher are implemented. The
  native Leap DLL/runtime/service and physical HIL evidence remain absent on
  this host.
- MindWave and Tello: working external implementations were discovered but are
  not yet Fabric adapters.
- Tuya: no reusable production implementation was discovered.
- Quest: upstream contains authoring/runtime placeholders and simulators, not a
  production headset application.

No physical pairing, flight, motor movement, camera capture, audio retention,
or biosignal recording was performed during reconciliation.

## Preserved boundaries

- Vendor SDKs stay in adapters or existing external repositories.
- Agent and wearable credentials never enter course packs or event payloads.
- Raw audio, video, image, EEG, and unredacted CLI data are rejected from
  ordinary Fabric persistence.
- The existing upstream runtime and Agent Mesh legacy behavior remain usable
  when the standalone Fabric service and bridge are stopped.
- Physical replay and unrestricted LLM-to-shell/device execution remain absent.
