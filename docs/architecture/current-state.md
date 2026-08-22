# Current State

Status: reconciled against upstream `main` commit `b74bb2b`, updated 2026-08-22.

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

The Windows shared launcher owns this single Fabric process. Glasses/agent,
Leap/RoboMaster, and Tuya-compatible smart-plug launchers attach with dedicated
scoped adapter identities while retaining ownership only of their own adapter
processes and sessions. The launcher opens the tutor UI through a one-use
90-second ticket that redeems to an instructor-scoped, page-memory session; the
administrator bootstrap never enters the browser. The UI leads tutors through
lesson choice, device assignment, safety, and teaching. It groups every
registered node by plain-language I/O behavior and keeps protocol identifiers
and capabilities in collapsed technical details. An authenticated discovery
route invokes a fixed read-only Windows host probe and leads the five-stage
tutor flow: find devices, choose lesson, assign devices, safety, and teach.
Candidates remain separate from authenticated nodes.

The same console now has a separate ephemeral media plane and semantic sensor
projection. Camera publishers replace one bounded in-memory JPEG/PNG; the page
shows a latest-frame wall and can run local, tutor-triggered YOLO-World analysis
without storing the image or turning a detection into a command. A one-use
pairing issues the existing Android glasses companion a publish-only site/room
credential. The ordinary event database remains media-free. Latest normalized
`sensor.*`, `telemetry.*`, and `biosignal.*` events become readable sensor
cards without inventing data for merely discovered hardware.

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
- G2 and Meta: the software compatibility path and Windows launcher exist. An
  optional Meta DAT 0.9.0 Android live-frame source (2 FPS), manual snapshot
  fallback, phone pairing, camera wall, and local vision path are implemented.
  The optional APK compile/build and official MockDeviceKit live-frame smoke
  test pass against the SDK artifacts; repeatable technician installation still
  needs `read:packages`, and the owner hardware round trip remains required.
- RoboMaster S1 and Leap: software adapter, semantic course flow, UI controls,
  upstream dry-run process test, and hardware launcher are implemented. The
  native Leap DLL/runtime/service and physical HIL evidence remain absent on
  this host.
- MindWave and Tello: the preserved Brain2Devices process now has a CIT
  launcher, read-only status/discovery cards, and instructor-only connection
  actions. They are not yet canonical Fabric telemetry/flight nodes; no flight
  command is exposed.
- Tuya / Gosund: no prior reusable implementation was discovered. A new
  TinyTuya 1.20.0 LAN adapter, simulator, course role, UI controls, and Windows
  launcher are implemented; no physical outlet has passed HIL yet.
- Quest: upstream contains authoring/runtime placeholders and simulators, not a
  production headset application.

The media UI accepts explicit RoboMaster and Tello publishers, but neither
physical camera publisher is wired yet. The preserved upstream camera readers
remain reusable implementation candidates; source-kind support alone is not
reported as a live physical feed. The sensor UI is contract-tested, while the
physical LEGO Pybricks event bridge and HIL remain open.

No physical pairing, flight, motor movement, camera capture, audio retention,
or biosignal recording was performed during reconciliation. Browser testing
used an explicitly simulated authenticated camera publisher and a disposable
in-memory frame.

## Preserved boundaries

- Vendor SDKs stay in adapters or existing external repositories.
- Agent and wearable credentials never enter course packs or event payloads.
- Raw audio, video, image, EEG, and unredacted CLI data are rejected from
  ordinary Fabric persistence.
- The existing upstream runtime and Agent Mesh legacy behavior remain usable
  when the standalone Fabric service and bridge are stopped.
- Physical replay and unrestricted LLM-to-shell/device execution remain absent.
