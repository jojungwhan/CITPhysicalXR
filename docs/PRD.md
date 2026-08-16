 CIT Physical XR Studio
/3, RoboMaster S1, LEGO SPIKE/MINDSTORMS, and Leap Motion

**Document status:** Implementation-ready
**Version:** 1.0
**Date:** 2026-08-16
**Primary repository:** `cit-physical-xr`
**Related existing system:** `agent-cli-mesh`
**Primary development environment:** Windows 11
**Secondary development and CI environments:** Ubuntu Linux and Windows 11
**Target XR devices:** Meta Quest 2 and Meta Quest 3
**Implementation agents:** Codex and Claude Code
**Recommended licence for original CIT code:** Apache License 2.0

---

# 0. Implementation Directive

Implement this product milestone by milestone. Do not attempt to build the entire system in one uncontrolled pass.

Before writing production code, Codex must:

1. Read this PRD completely.
2. Locate the existing repositories and modules configured by the owner.
3. Inspect the working RoboMaster S1 + Leap Motion Python environment.
4. Inspect the existing Agent CLI Mesh, Even Realities G2, Meta smart-glasses, Android bridge, and CLI communication modules.
5. Create `docs/REUSE_AUDIT.md`.
6. Create `docs/IMPLEMENTATION_PLAN.md`.
7. Create `docs/DECISIONS.md`.
8. Scaffold protocol schemas, fake-device adapters, tests, and CI before modifying hardware integrations.
9. Keep the repository runnable after every milestone.
10. Stop after the milestone requested by the owner.

## Mandatory implementation constraints

* Do not rewrite the working RoboMaster S1 or Leap Motion implementation until it is protected by adapter contract tests.
* Do not upgrade the existing S1 Python environment in place.
* Do not expose arbitrary shell, PowerShell, Bash, SSH, Python `exec`, or unrestricted process-execution endpoints.
* Do not allow student code, AI agents, smart glasses, or Quest applications to bypass the physical-device safety supervisor.
* Do not expose RoboMaster, LEGO, Leap Motion, or Quest control services directly to the public internet.
* Do not store device tokens, API keys, Bluetooth addresses, Wi-Fi credentials, Agent CLI Mesh credentials, or pairing secrets in Git.
* Do not make Agent CLI Mesh a required dependency for local robot or XR operation.
* Do not duplicate a working G2, Meta glasses, wearable, transport, security, or CLI module when a compatible reusable implementation exists.
* Do not copy code from another repository without recording its source, licence, version, and modification status.
* Do not promise automatic conversion of arbitrary Python back into blocks.
* Do not expose the RoboMaster S1 blaster through the default student API.
* Do not permit robot movement solely from unconfirmed voice transcription.
* Do not silently execute expired or previously queued physical commands after reconnection.
* Do not make Quest 3-only functionality mandatory for the core curriculum.
* Treat Quest 2 as the baseline XR capability target.
* Record every architecture deviation from this PRD in `docs/DECISIONS.md`.

---

# 1. Executive Summary

`CIT Physical XR Studio` is a free and open-source educational programming platform through which students can use either **visual blocks or readable Python** to control:

* Virtual objects and digital twins displayed on Meta Quest 2 and Quest 3
* RoboMaster S1
* LEGO SPIKE Prime
* LEGO SPIKE Essential
* LEGO MINDSTORMS Robot Inventor
* Later, LEGO MINDSTORMS EV3
* Leap Motion hand-tracking input
* Multiple physical and virtual devices in one program

The central student experience is a PC-based web application:

```text
Blockly blocks
      ⇅
Generated readable Python
      +
Direct Python mode
      ↓
Local device runtime and safety supervisor
      ├── Existing RoboMaster S1 Python environment
      ├── Existing Leap Motion integration
      ├── LEGO Pybricks adapter
      ├── Meta Quest 2/3 Godot client
      └── Optional Agent CLI Mesh bridge
```

The system must preserve the existing working Leap Motion → RoboMaster S1 solution. That implementation becomes the first production device adapter and a reference integration rather than being replaced.

The Quest application is a reusable, preinstalled **CIT XR Runtime** developed with Godot and OpenXR. Students change blocks or Python on the PC without rebuilding and reinstalling an APK after every edit.

The physical runtime remains local and operational without Agent CLI Mesh. Agent CLI Mesh is connected through a separate optional bridge so that existing G2, Meta glasses, Claude Code, Codex, wearable, device-authentication, normalized-event, and multi-machine communication features can be reused without coupling robot safety to a remote control plane.

## Agent CLI Mesh already defines a centralized Hub/Node architecture, normalized session events, wearable-facing status, G2 and Android bridge applications, scoped device tokens, reconnect handling, and typed command routing. Its current repository plan includes `apps/even-g2`, `apps/android-bridge`, `packages/protocol`, `packages/security`, `packages/config`, `packages/wearable-api`, `packages/observability`, and related infrastructure. These are explicit reuse candidates.

# 2. Validated Technology Baseline

The implementation must pin tested versions rather than depending on unversioned `main`, `latest`, or beta releases.

## 2.1 Godot and Meta Quest

Godot is free and open source under the MIT licence. Godot’s Android/OpenXR deployment path supports Meta Quest export, and current Godot XR documentation identifies both Quest 2 and Quest 3 as supported devices. Godot XR Tools is also MIT-licensed and provides reusable XR interaction scenes and components.

## 2.2 Blockly

Blockly is a free, open-source visual programming editor under Apache License 2.0. The project supports custom blocks, generators, plugins, and code-generation workflows appropriate for a CIT-owned educational interface.

## 2.3 LEGO and Pybricks

Pybricks supports SPIKE and MINDSTORMS hubs. The SPIKE Prime Hub and MINDSTORMS Robot Inventor Hub are effectively identical for Pybricks use. `pybricksdev` is MIT-licensed and supports running and downloading MicroPython programs and communicating with Pybricks firmware through BLE. Its Pybricks GATT protocol includes writing to hub `stdin` and receiving hub `stdout` events.

Pybricks Python is free and open source, while Pybricks’ own hosted block-coding features may require supporter access. Therefore, CIT must use its own Blockly editor rather than depend on Pybricks’ paid block editor.

## 2.4 Leap Motion

Ultraleap provides open-source Python bindings for LeapC under Apache License 2.0. Those bindings still require Ultraleap’s installed hand-tracking service and compatible hardware. The existing working CIT environment remains the compatibility baseline.

## 2.5 Even Realities G2

Even Realities provides the Even Hub SDK and a developer platform for applications running with the Even G2. Existing CIT G2 modules should be inspected before any new G2 implementation is created.

## 2.6 Meaning of “open source”

The CIT-authored application, protocol, editor, adapters, Quest client, project format, examples, and documentation must be open source.

The following unavoidable layers remain proprietary:

* Meta Quest hardware, Horizon OS, firmware, and Meta’s runtime implementation
* DJI RoboMaster S1 hardware and firmware
* LEGO hardware
* Ultraleap’s tracking service and hardware drivers
* Even Realities hardware and firmware
* Meta smart-glasses hardware, firmware, and vendor services

The project requirement is therefore:

> The complete CIT-controlled software and curriculum layer must be free, inspectable, modifiable, self-hostable, and open source, while proprietary hardware drivers remain isolated behind adapters.

---

# 3. Existing Assets and Reuse Strategy

## 3.1 Known existing assets

The owner already has:

1. A working PC-based Python programming environment for RoboMaster S1.
2. Working Leap Motion control of RoboMaster S1.
3. Agent CLI Mesh architecture and PRD.
4. Even Realities G2 communication features.
5. Meta smart-glasses communication features.
6. Claude Code and Codex CLI status and prompt communication features.
7. Multi-machine Windows/Linux development requirements.
8. Wearable-oriented concise status and command APIs.
9. A normalized event and command-envelope design.
10. Existing or planned device identity, scoped-token, reconnect, redaction, audit, and WebSocket modules.

Agent CLI Mesh already specifies a wearable API with snapshots, session status, prompt and interrupt endpoints, event WebSockets, an OpenAI-compatible G2 route, deterministic command resolution, and ambiguity rejection.

## 3.2 Mandatory reuse audit

Codex must create `docs/REUSE_AUDIT.md` before implementing integrations.

The audit must include:

| Field             | Requirement                                                  |
| ----------------- | ------------------------------------------------------------ |
| Source repository | Repository name and local path                               |
| Module            | Package, application, service, class, or file                |
| Purpose           | Current role                                                 |
| Language/runtime  | TypeScript, Python, Android, Godot, etc.                     |
| Licence           | Licence and notice requirements                              |
| Current tests     | Existing automated or manual tests                           |
| Dependencies      | Runtime and vendor dependencies                              |
| Protocol          | HTTP, WebSocket, JSON-RPC, BLE, local socket, etc.           |
| Reusability       | Direct reuse, extraction, wrapper, reference only, or reject |
| Required changes  | Exact changes needed                                         |
| Risk              | Low, medium, high                                            |
| Decision          | Reuse, adapt, extract, replace, defer                        |
| Evidence          | Relevant paths, tests, and symbols                           |

## 3.3 Priority Agent CLI Mesh reuse candidates

Codex must inspect these before creating equivalents:

```text
agent-cli-mesh/
├─ apps/
│  ├─ even-g2/
│  └─ android-bridge/
│
├─ packages/
│  ├─ protocol/
│  ├─ domain/
│  ├─ security/
│  ├─ config/
│  ├─ persistence/
│  ├─ wearable-api/
│  ├─ observability/
│  └─ test-harness/
```

Potential reusable functions include:

* Versioned message envelope
* Message validation
* Correlation IDs
* Idempotency keys
* Expiring commands
* Device identity
* Scoped device tokens
* WebSocket reconnect and replay
* Typed errors
* Redaction
* Append-only audit events
* Concise display text
* Speech text
* OpenAI-compatible G2 route
* Android bridge
* Wearable event subscriptions
* Deterministic command parser
* Ambiguity rejection
* Multi-machine node identity
* Health and diagnostics

Agent CLI Mesh’s protocol already includes message IDs, correlation IDs, sequence numbers, timestamps, expiry, idempotency keys, node/device identity, and typed payloads.

## 3.4 Reuse rules

* Reuse through package imports or explicit adapter boundaries.
* Do not establish a circular dependency between `agent-cli-mesh` and `cit-physical-xr`.
* Keep `cit-physical-xr` fully operational when Agent CLI Mesh is absent.
* Where a module is domain-neutral, prefer extracting it into a shared package.
* Where a module is tightly coupled to Claude/Codex sessions, integrate through `agent-mesh-bridge`.
* Do not fork the G2 or Android bridge unless extension through an API is impossible.
* Preserve the existing Agent CLI Mesh security rule prohibiting general remote-shell endpoints.
* Record all copied or modified third-party code in `THIRD_PARTY_NOTICES.md`.

## 3.5 Recommended repository relationship

```text
agent-cli-mesh
     │
     │ optional authenticated API
     ▼
cit-physical-xr/packages/agent-mesh-bridge
     │
     ▼
CIT Local Physical Runtime
```

The physical runtime must not import Claude or Codex vendor adapters directly.

---

# 4. Product Goals

## 4.1 Primary goals

### G-001: One programming environment

Students must use one PC-based interface for blocks and Python rather than separate applications for every robot.

### G-002: Readable block-to-Python progression

Blocks must generate deterministic, readable Python using the same API that advanced students use manually.

### G-003: Quest 2 and Quest 3 compatibility

One Godot/OpenXR client must run on Quest 2 and Quest 3.

### G-004: Preserve the working S1 integration

The existing RoboMaster S1 Python environment must be wrapped, tested, and reused.

### G-005: Generalize Leap Motion input

Leap Motion gestures must become normalized input events that can control S1, LEGO, Quest objects, or multiple targets.

### G-006: LEGO SPIKE and Robot Inventor support

Students must control LEGO motors and sensors from the same block/Python environment.

### G-007: Multi-device orchestration

One program must be able to coordinate physical robots, virtual objects, hand input, Quest controllers, and telemetry.

### G-008: Local-first operation

Core physical control must continue without the internet, Agent CLI Mesh, cloud APIs, or external AI services.

### G-009: Safety independent of student code

A separate safety supervisor must enforce all physical limits and emergency-stop behavior.

### G-010: Open-source ownership

CIT must be able to self-host, modify, extend, teach, and commercially use the software without per-student engine fees.

### G-011: Reuse existing wearable and CLI infrastructure

G2, Meta glasses, Claude Code, Codex, and wearable communication modules must be reused where technically appropriate.

### G-012: Extensible adapter architecture

Additional devices must be addable without changing the IDE, project format, or safety core.

---

# 5. Non-Goals for Version 1

The following are explicitly outside the first production release:

* Building an entire 3D game engine.
* Replacing Godot.
* Building a complete Scratch clone.
* Automatic conversion of unrestricted Python into blocks.
* Running all Python packages directly on Quest.
* Direct Quest-to-S1 or Quest-to-LEGO control without the PC broker.
* Direct wearable-to-motor movement commands.
* Public multi-tenant SaaS hosting.
* Public internet robot control.
* Autonomous physical actions initiated only by an LLM.
* Unrestricted student filesystem or operating-system access.
* Full RoboMaster S1 firmware replacement.
* RoboMaster S1 blaster control in the student toolbox.
* Quest headset-camera computer vision.
* Quest 3-only functionality as a course prerequisite.
* Full MINDSTORMS NXT or RCX support.
* Automatic firmware flashing without explicit instructor action.
* Full EV3 support before SPIKE Prime and Robot Inventor are stable.
* High-fidelity physics simulation of every robot.
* Perfect centimetre-level alignment of physical and virtual robots without calibration.
* Replacement of the existing G2 or Meta smart-glasses applications.
* General remote CLI or shell execution through glasses.
* Dependency on Agent CLI Mesh for local classroom operation.

---

# 6. Users and Operating Modes

## 6.1 Beginner student

Uses blocks, simulation, and preconfigured devices.

Needs:

* Minimal setup
* Clear device names and icons
* Safe speed limits
* Immediate visual feedback
* Generated Python view
* Actionable error messages

## 6.2 Intermediate student

Uses blocks and edits generated Python.

Needs:

* Variables
* Functions
* Events
* Conditions
* Loops
* Sensor values
* Parallel actions
* Device capabilities
* Simple debugging

## 6.3 Advanced student

Uses direct Python and optional advanced packages.

Needs:

* Typed Python API
* Async programming
* Telemetry
* Local AI or computer-vision integration
* Multi-device projects
* Logs and replay
* Unit tests

## 6.4 Instructor

Pairs hardware, assigns devices, selects safety profiles, arms sessions, observes programs, and stops all motion.

## 6.5 Maintainer

Adds adapters, updates compatibility, diagnoses protocol changes, and maintains hardware-specific environments.

## 6.6 Demonstration operator

Runs polished Quest, G2, Meta glasses, Leap Motion, S1, and LEGO demonstrations while monitoring safety and system state.

---

# 7. Core User Journeys

## 7.1 Blocks control a simulated robot

1. Student opens a project.
2. Student selects `Simulation`.
3. Student connects blocks:

   * When program starts
   * Move robot forward
   * Turn right
4. Generated Python appears beside the blocks.
5. Student runs the project.
6. The simulated robot moves in the browser and Quest runtime.
7. No physical device is armed.

## 7.2 Blocks control RoboMaster S1

1. Instructor connects and assigns `s1-main`.
2. Student selects a low-speed safety profile.
3. Instructor arms the device.
4. Student runs a block program.
5. Blocks generate Python.
6. Student runtime sends bounded intents to the local broker.
7. The safety supervisor validates the command.
8. The S1 adapter forwards it to the existing S1 environment.
9. S1 telemetry appears in the IDE and Quest.
10. Program stop or disconnect stops the chassis.

## 7.3 Leap Motion controls S1 and its Quest digital twin

1. Leap Motion adapter emits normalized hand events.
2. Student maps palm direction to S1 velocity.
3. The same event updates the Quest digital twin.
4. Opening the palm triggers `stop_all`.
5. Loss of hand tracking stops movement.

## 7.4 Quest controller controls LEGO

1. Quest pairs with the runtime.
2. Instructor selects `lego-spike-01`.
3. User holds the Quest grip dead-man control.
4. Joystick values generate bounded drive intents.
5. LEGO hub agent executes motor commands.
6. Encoder telemetry returns to Quest.
7. Releasing grip immediately stops motors.

## 7.5 One program coordinates S1 and LEGO

1. Student connects both devices.
2. Student uses a `run in parallel` block.
3. S1 and LEGO start coordinated movement.
4. Each command is routed to its exact device ID.
5. Failure of one device is visible and does not silently retarget the other.

## 7.6 Display Claude/Codex status in Quest and G2

1. Agent CLI Mesh bridge subscribes to normalized session events.
2. The Quest HUD displays a concise coding-agent status card.
3. Existing G2 or Meta smart-glasses clients continue using Agent CLI Mesh.
4. Physical device status is optionally added to the wearable snapshot.
5. No robot movement is initiated from an agent status event.

---

# 8. Key Architectural Decisions

## ADR-001: Separate repository

Create `cit-physical-xr` as a separate repository.

**Rationale:**

* Agent CLI Mesh must remain focused on AI coding-session control.
* Physical safety requires local deterministic behavior.
* Classroom operation must not depend on the Hub.
* Separate release cycles reduce regression risk.
* Shared components can be extracted or imported.

## ADR-002: PC runtime is the physical control authority

The PC-local runtime is the only component authorized to send commands to physical adapters.

```text
IDE / Quest / Leap / Agent Mesh
              ↓
       Local runtime
              ↓
     Safety supervisor
              ↓
       Device adapters
```

## ADR-003: Blockly is the primary block layer

Do not make Godot block plugins the central programming environment.

Use:

* Blockly for student blocks
* Python generation
* Python editing
* Godot only for the Quest rendering and interaction runtime

## ADR-004: Quest is a reusable runtime client

Install one CIT XR Runtime APK on Quest 2 and Quest 3. Student code changes should normally require no APK rebuild.

## ADR-005: Existing S1 and Leap code is wrapped, not rewritten

The existing environment remains isolated behind local adapter processes and contract tests.

## ADR-006: Default student execution uses a browser-contained Python runtime

Use Pyodide in a Web Worker for the default classroom Python execution mode.

Benefits:

* Actual Python syntax
* No unrestricted local filesystem access
* No direct operating-system process access
* Consistent blocks and Python API
* Easier cancellation
* Easier classroom reset

## ADR-007: Advanced CPython is optional and instructor-controlled

Provide a separate local CPython worker for projects requiring:

* OpenCV
* AI libraries
* ROS
* Drone SDKs
* Local files
* Advanced networking

It must not be the beginner default.

## ADR-008: Device APIs are capability-based

The IDE must build the toolbox from device manifests rather than hard-coded assumptions.

## ADR-009: Safety is enforced below student code

No student, Quest, Leap, wearable, or AI module may bypass the safety supervisor.

## ADR-010: Physical movement commands are never replayed after expiry

Telemetry may replay after reconnection. Movement commands may not.

## ADR-011: Quest 2 is the capability baseline

Quest 3 may enable enhanced passthrough and environment features, but every core lesson must operate on Quest 2.

## ADR-012: Protocol schema is language-neutral

Use JSON Schema as the protocol source of truth.

Generate:

* TypeScript types and validators
* Python Pydantic models
* Documentation
* Test fixtures
* Lightweight Godot/GDScript validation helpers

## ADR-013: Agent CLI Mesh is optional and read-only by default

Agent CLI Mesh integration starts with:

* Status
* Events
* Diagnostics
* Project information
* Wearable display
* Stop/pause safety commands

It must not provide unconfirmed movement control in v1.

---

# 9. High-Level System Architecture

```text
┌───────────────────────────────────────────────────────────────┐
│                     CIT Studio Web App                        │
│                                                               │
│  Blockly editor   Python editor   Simulator   Device panel    │
│  Project files    Console         Logs        Instructor UI   │
└───────────────┬─────────────────────┬─────────────────────────┘
                │                     │
                │                     │ default student execution
                │                     ▼
                │              Pyodide Web Worker
                │                     │ typed CIT RPC
                ▼                     ▼
┌───────────────────────────────────────────────────────────────┐
│                 CIT Local Runtime on PC                       │
│                                                               │
│  Session manager        Device registry                       │
│  Capability registry   Event router                           │
│  Safety supervisor     Command validator                      │
│  Device leases         Telemetry recorder                     │
│  Quest gateway         Optional CPython worker manager        │
└───────┬─────────┬──────────┬──────────┬───────────┬──────────┘
        │         │          │          │           │
        ▼         ▼          ▼          ▼           ▼
  S1 adapter   Leap       LEGO       Quest       Agent Mesh
  process      adapter    adapter    gateway     bridge
        │         │          │          │           │
        ▼         ▼          ▼          ▼           ▼
 RoboMaster   Leap      SPIKE /     Quest 2/3   G2 / Meta /
    S1        Motion    MINDSTORMS   Godot XR   Claude / Codex
```

---

# 10. Functional Requirements

# 10.1 Project and Workspace

## FR-001: Project lifecycle

Users must be able to:

* Create a project
* Open a project
* Save a project
* Duplicate a project
* Export a project
* Import a project
* Reset to a template
* Run, pause, stop, and restart
* View generated Python
* Switch intentionally from blocks to direct Python mode
* Select simulation or physical mode

## FR-002: Project file format

Each project must use a versioned format:

```json
{
  "schemaVersion": 1,
  "projectId": "uuid",
  "name": "Leap S1 Demo",
  "authoringMode": "blocks",
  "blocksState": {},
  "generatedPython": "",
  "pythonSource": "",
  "targetProfile": "quest-s1-lego",
  "deviceBindings": [],
  "questScene": {},
  "safetyPreset": "student-low-speed",
  "assets": [],
  "createdAt": "",
  "updatedAt": ""
}
```

## FR-003: Source-of-truth rules

* In block mode, `blocksState` is authoritative.
* `generatedPython` is reproducible output.
* Direct edits to generated Python require conversion to Python mode.
* In Python mode, `pythonSource` is authoritative.
* The last block snapshot must be retained.
* The system must not claim that arbitrary Python can be converted back to blocks.
* Project migrations must be explicit and reversible where possible.

---

# 10.2 Device Registry and Discovery

## FR-004: Device registry

The runtime must maintain:

* Stable `deviceId`
* Display name
* Device family
* Model
* Adapter
* Connection transport
* Firmware or SDK version
* Adapter version
* Online/offline state
* Battery where available
* Capabilities
* Safety profile
* Assigned user or class
* Last heartbeat
* Calibration state
* Active lease
* Current program session

## FR-005: Device discovery

Discovery mechanisms may include:

* Configured subprocess adapters
* USB
* Bluetooth Low Energy
* Local Wi-Fi
* WebSocket pairing
* Manual static configuration
* Agent CLI Mesh registry

Discovery must not automatically arm a physical device.

## FR-006: Device assignment

An instructor must assign a device to a program session before student code can control it.

## FR-007: Capability manifests

Example:

```json
{
  "deviceId": "s1-main",
  "deviceType": "robot",
  "model": "robomaster-s1",
  "capabilities": [
    "drive.omnidirectional",
    "drive.velocity",
    "gimbal.pitch_yaw",
    "led.rgb",
    "telemetry.battery",
    "telemetry.attitude",
    "video.camera"
  ],
  "safetyProfile": "s1-student"
}
```

The Blockly toolbox must hide unsupported actions.

---

# 10.3 Block Editor

## FR-008: Blockly workspace

The IDE must provide:

* Toolbox categories
* Search
* Zoom
* Undo/redo
* Copy/paste
* Keyboard navigation
* Block comments
* Collapsible functions
* Variable and function blocks
* Device-specific categories
* Validation warnings
* Disconnected-block warnings
* Korean and English labels
* Persistent workspace state

## FR-009: Core block categories

```text
Events
Control
Logic
Loops
Variables
Functions
Math
Text
Lists
Time
Parallel actions
Devices
Sensors
Quest
Leap Motion
RoboMaster
LEGO
Safety
Display
Logging
AI/CLI integration
```

## FR-010: Dynamic device blocks

The toolbox must update when device capabilities change.

Example:

* S1 connected: show gimbal and omnidirectional-drive blocks.
* LEGO connected: show motor and sensor blocks.
* Quest connected: show controller, hand, HUD, and virtual-object blocks.
* Leap connected: show hand and gesture blocks.

## FR-011: Generated Python

Generated Python must be:

* Deterministic
* Formatted
* Readable
* Stable between equivalent block layouts
* Based on the public CIT Python SDK
* Annotated with source mappings to block IDs
* Suitable for teaching
* Free from hidden generated global state where avoidable

Example generated code:

```python
from citxr import device, when, parallel

s1 = device("s1-main")
lego = device("lego-spike-01")
leap = device("leap-main")


@when(leap.gesture("open_palm"))
async def stop_robots():
    await parallel(
        s1.stop(),
        lego.stop(),
    )
```

## FR-012: Runtime error mapping

When generated Python fails, the IDE must identify:

* Python line
* Block ID
* Block label
* Device involved
* Suggested correction

---

# 10.4 Python Execution

## FR-013: Safe classroom runtime

Default execution must occur in a Pyodide Web Worker.

The student environment must not expose by default:

* Local filesystem
* Operating-system commands
* Environment variables
* Arbitrary sockets
* Device credentials
* Adapter implementation objects
* Agent CLI Mesh credentials

The worker communicates with the local runtime through a constrained RPC bridge.

## FR-014: Student Python API

The same API must work in generated and handwritten Python:

```python
from citxr import device, when, every, parallel, sleep, log

s1 = device("s1-main")
quest = device("quest-main")


@when(quest.controller("right").trigger_pressed)
async def move():
    stick = await quest.controller("right").joystick()
    await s1.drive.velocity(
        forward=stick.y * 0.25,
        strafe=stick.x * 0.25,
        rotation=0.0,
    )
```

## FR-015: Cancellation

Student loops and event handlers must include cancellation checkpoints.

Stopping a session must:

1. Cancel student tasks.
2. Revoke device leases.
3. Send stop commands.
4. Stop recurring timers.
5. Clear queued movement commands.
6. Retain logs.
7. Return devices to a safe idle state.

## FR-016: Advanced CPython mode

Advanced CPython mode must:

* Be disabled by default
* Require instructor permission
* Run in a separate process
* Use a dedicated virtual environment
* Receive a scoped local session token
* Communicate with devices only through the runtime API
* Use an import allowlist or project profile
* Have execution time limits
* Have a constrained working directory
* Avoid inheriting sensitive environment variables
* Terminate on instructor stop
* Clearly state that it is a weaker security boundary than browser mode

---

# 10.5 Program Sessions

## FR-017: Session model

Each run creates a `ProgramSession` containing:

```text
sessionId
projectId
authoringMode
executionMode
userId
instructorId
deviceBindings
questClientId
safetyPolicyId
state
startedAt
lastActivityAt
endedAt
```

## FR-018: Session states

```text
created
validating
waiting_for_devices
waiting_for_arm
ready
running
paused
stopping
stopped
completed
failed
disconnected
emergency_stopped
```

## FR-019: Exact device routing

Every command must target an exact `deviceId`.

No command may be routed based only on:

* Device family
* Display name substring
* “Nearest robot”
* Last-used robot
* Voice interpretation without confirmation

## FR-020: Device leases

Only one physical program session may own a write lease for a device.

Read-only telemetry viewers may coexist.

---

# 10.6 Event and Command Model

## FR-021: Shared envelope

Use a versioned envelope derived from the proven Agent CLI Mesh structure:

```ts
interface CitEnvelope<T> {
  protocolVersion: 1;
  messageId: string;
  type: string;
  runtimeId?: string;
  deviceId?: string;
  clientId?: string;
  sessionId?: string;
  correlationId?: string;
  sequence?: number;
  sentAt: string;
  expiresAt?: string;
  idempotencyKey?: string;
  payload: T;
}
```

## FR-022: Command intent

```ts
interface DeviceCommandIntent {
  commandId: string;
  sessionId: string;
  deviceId: string;
  capability: string;
  action: string;
  arguments: Record<string, unknown>;
  source:
    | "student_blocks"
    | "student_python"
    | "quest"
    | "leap"
    | "instructor"
    | "agent_mesh"
    | "system";
  issuedAt: string;
  expiresAt: string;
  idempotencyKey: string;
  safetyContext: {
    policyId: string;
    armed: boolean;
    deadmanActive?: boolean;
  };
}
```

## FR-023: Device event

```ts
interface DeviceEvent {
  eventId: string;
  deviceId: string;
  sessionId?: string;
  category:
    | "connection"
    | "input"
    | "telemetry"
    | "motion"
    | "sensor"
    | "safety"
    | "program"
    | "diagnostic";
  name: string;
  values: Record<string, unknown>;
  sourceTimestamp?: string;
  receivedAt: string;
}
```

## FR-024: Idempotency and expiry

* Every physical command has an idempotency key.
* Duplicate commands must not execute twice.
* Movement commands must have short expiry.
* Expired commands must be rejected.
* Movement commands must never be replayed after reconnect.
* Stop commands may be repeated safely.
* Telemetry replay must be clearly marked as historical.

---

# 10.7 RoboMaster S1 Adapter

## FR-025: Preserve the existing environment

The adapter must use the exact working S1 environment before attempting dependency upgrades.

Configuration must support:

```yaml
devices:
  s1-main:
    adapter: robomaster-s1-subprocess
    executable: "C:\\path\\to\\existing-venv\\python.exe"
    workingDirectory: "C:\\path\\to\\existing-s1-project"
    command:
      - "-m"
      - "cit_s1_bridge"
```

## FR-026: Process isolation

The S1 integration must run as a separate process.

```text
CIT Local Runtime
       ↕ authenticated localhost IPC
S1 Adapter Process
       ↕ existing working S1 code
RoboMaster S1
```

## FR-027: Adapter handshake

The bridge must report:

* Adapter protocol version
* Python version
* Current environment path
* S1 library version where detectable
* Supported capabilities
* Connection status
* Existing Leap integration status
* Camera availability
* Health diagnostics

## FR-028: Minimum S1 capabilities

Where supported by the existing code:

```text
drive.forward
drive.backward
drive.strafe_left
drive.strafe_right
drive.rotate
drive.velocity
drive.stop
gimbal.pitch_yaw
gimbal.stop
led.set
telemetry.battery
telemetry.attitude
telemetry.position
camera.status
```

## FR-029: S1 safety

* Default student speed must be capped.
* Chassis motion must stop on heartbeat timeout.
* Gimbal motion must have angle and velocity limits.
* Blaster control must be unavailable in the default SDK.
* Camera streaming must be opt-in.
* Adapter failure must trigger a stop attempt.
* Existing direct Leap-to-S1 mode must be disabled while CIT runtime owns the S1 lease.

## FR-030: Compatibility tests

Record fixtures for:

* Connect
* Disconnect
* Chassis movement
* Stop
* Gimbal movement
* Telemetry
* Network loss
* Process crash
* Duplicate command
* Expired command
* Emergency stop

---

# 10.8 Leap Motion Adapter

## FR-031: Normalize Leap input

The Leap adapter must produce device-independent events.

Example:

```json
{
  "deviceId": "leap-main",
  "category": "input",
  "name": "gesture.open_palm",
  "values": {
    "hand": "right",
    "confidence": 0.94,
    "palmPosition": [0.1, 0.3, -0.2],
    "palmNormal": [0.0, 1.0, 0.0]
  }
}
```

## FR-032: Supported Leap events

At minimum:

```text
hand.appeared
hand.disappeared
hand.updated
gesture.open_palm
gesture.fist
gesture.pinch_started
gesture.pinch_ended
gesture.point
gesture.swipe
gesture.custom
tracking.lost
```

## FR-033: Raw and derived modes

* Raw hand frames must be available only to advanced projects.
* Beginner projects use normalized gestures.
* High-frequency frames must be throttled.
* Derived events must use configurable thresholds.
* Gesture profiles must be saved per user or class.

## FR-034: Decouple Leap from S1

Leap code must not call the S1 SDK directly after integration.

```text
Leap event
    ↓
Event router
    ↓
Student program
    ↓
Command intent
    ↓
Safety supervisor
    ↓
S1 or LEGO adapter
```

## FR-035: Tracking-loss safety

Any Leap-controlled continuous motion must stop when:

* The tracked hand disappears
* Confidence falls below threshold
* Leap service disconnects
* Event heartbeat expires
* Program session stops

---

# 10.9 Meta Quest 2/3 Client

## FR-036: Generic CIT XR Runtime

Create a Godot/OpenXR application installed once on Quest 2 and Quest 3.

It must provide:

* Runtime pairing
* Device selection
* Virtual scene
* Robot digital twins
* Controller input
* Hand input where supported
* HUD
* Telemetry
* Warnings
* Dead-man control
* Emergency stop
* Connection status
* Simulation mode
* Calibration mode

## FR-037: Quest pairing

Pairing must use:

* Local network discovery where reliable
* Manual IP fallback
* Short-lived pairing code
* Scoped device token
* Token revocation
* Device display name
* No permanent secret displayed in logs

## FR-038: Quest-to-runtime events

At minimum:

```text
quest.connected
quest.disconnected
head.pose
controller.left.pose
controller.right.pose
controller.trigger
controller.grip
controller.joystick
controller.button
hand.left.pose
hand.right.pose
hand.gesture
ui.button
emergency_stop
```

## FR-039: Runtime-to-Quest commands

At minimum:

```text
scene.load
object.spawn
object.update
object.remove
digital_twin.update
hud.status
hud.warning
hud.clear
controller.haptic
calibration.start
calibration.result
session.state
```

## FR-040: Quest 2 baseline

The following must work on Quest 2:

* VR scene
* Controllers
* Basic hand input where available through the selected OpenXR stack
* HUD
* Robot telemetry
* Digital twins
* Local Wi-Fi communication
* Simulation
* Dead-man control
* Emergency stop

## FR-041: Quest 3 enhancements

Quest 3 may additionally enable:

* Higher-quality passthrough
* Improved mixed-reality presentation
* More detailed environment interaction
* Higher model and rendering budgets
* Optional spatial calibration enhancements

The application must feature-detect these capabilities.

## FR-042: Quest safety controls

Continuous physical control requires:

* Active local runtime connection
* Armed session
* Exact selected device
* Held dead-man grip or equivalent
* Fresh input heartbeat
* Valid safety profile

Releasing the dead-man control must stop physical motion.

## FR-043: Quest performance

* Quest 2 is the performance baseline.
* Target 72 Hz rendering.
* Avoid per-frame network allocations.
* Throttle network pose events independently from rendering.
* Use interpolation for digital twins.
* High-frequency telemetry must be coalesced.
* Visual degradation must not disable safety warnings.

## FR-044: Physical-to-virtual calibration

Support:

1. Manual origin placement
2. Heading calibration
3. Scale verification
4. Floor-height correction
5. Saved calibration profiles
6. Visible uncertainty indicator

Initial release does not require automatic computer-vision alignment.

---

# 10.10 LEGO SPIKE and MINDSTORMS Adapter

## FR-045: Primary supported hubs

Version 1 must support:

* LEGO SPIKE Prime
* LEGO SPIKE Essential
* LEGO MINDSTORMS Robot Inventor

## FR-046: Firmware strategy

Use Pybricks firmware for the primary implementation.

Firmware installation must be:

* Explicit
* Instructor-controlled
* Documented
* Reversible
* Never performed automatically when a class project starts

## FR-047: Host-controlled mode

The PC student program controls a persistent hub agent.

```text
Student program
      ↓
CIT runtime
      ↓ BLE
Pybricks hub agent
      ↓
Motors and sensors
```

Best for:

* Leap Motion
* Quest control
* S1 and LEGO coordination
* AI integration
* Telemetry
* Computer vision
* Live debugging

## FR-048: Autonomous mode

Blocks or Python generate Pybricks-compatible MicroPython that is compiled and downloaded to the hub.

Best for:

* Line following
* Embedded sensor loops
* Competition programs
* Operation without the PC
* Teaching embedded systems

## FR-049: Hybrid mode

The hub performs low-level control while the PC performs high-level planning.

```text
Hub:
- motor control
- sensor sampling
- local watchdog
- stop behavior

PC:
- Quest interface
- Leap gestures
- mission planning
- AI
- coordination
```

## FR-050: Hub agent protocol

Use a small, versioned, framed protocol suitable for constrained MicroPython.

Illustrative frame:

```text
C1|<sequence>|<operation>|<argument1>|<argument2>\n
```

Required operations:

```text
HELLO
HEARTBEAT
ACK
ERROR
MOTOR_RUN
MOTOR_RUN_ANGLE
MOTOR_STOP
DRIVE
TURN
SENSOR_READ
SENSOR_SUBSCRIBE
DISPLAY
SOUND
STOP_ALL
TELEMETRY
```

Requirements:

* Short messages
* Sequence numbers
* Bounded payload
* Explicit ACK
* Heartbeat
* Stop on heartbeat loss
* Version negotiation
* No arbitrary Python evaluation

## FR-051: LEGO capabilities

At minimum:

```text
motor.run
motor.run_time
motor.run_angle
motor.run_target
motor.stop
drive.straight
drive.turn
drive.velocity
sensor.distance
sensor.color
sensor.force
sensor.reflection
sensor.gyro
sensor.imu
hub.display
hub.sound
hub.button
hub.battery
```

Capabilities must reflect actual connected ports and hub support.

## FR-052: BLE handling

The adapter must provide:

* Discovery
* Pairing
* Reconnect
* Named device binding
* Firmware/protocol detection
* Connection health
* Packet retry where safe
* Telemetry throttling
* Explicit disconnection
* Actionable Bluetooth diagnostics

## FR-053: LEGO safety

* Motor power and speed caps
* Maximum command duration
* Stop on disconnect
* Stop on hub-agent heartbeat loss
* Port validation
* No simultaneous host and autonomous ownership
* Instructor arming for physical motion
* Physical hub button stop support where practical

---

# 10.11 Legacy MINDSTORMS Support

## FR-054: Robot Inventor

Robot Inventor is included in version 1 through the same Pybricks path as SPIKE Prime.

## FR-055: EV3

EV3 is a later adapter using one of:

* ev3dev over local network
* Pybricks EV3
* USB/network bridge

EV3 must not delay the Quest 2/3, S1, Leap, SPIKE, and Robot Inventor release.

## FR-056: NXT and RCX

NXT and RCX are out of scope for version 1.

---

# 10.12 Multi-Device Orchestration

## FR-057: Parallel actions

Provide an explicit parallel primitive:

```python
await parallel(
    s1.drive.forward(speed=0.2, duration=1.0),
    lego.drive.forward(speed=150, duration=1.0),
    quest.hud.show("Moving both robots"),
)
```

## FR-058: Device-specific failure

If one device fails:

* Report the exact failed device.
* Do not silently send its command to another device.
* Apply the project’s failure policy.
* Default physical policy is to stop coordinated movement.
* Preserve logs and telemetry.

## FR-059: Event routing

One input event may trigger multiple virtual and physical actions.

One device event must not be duplicated unintentionally.

## FR-060: Clock and ordering

* Use monotonic local timestamps where possible.
* Preserve source timestamps.
* Record runtime receipt time.
* Sequence events per device.
* Do not claim hard real-time synchronization.
* Expose measured latency in diagnostics.

---

# 10.13 Simulation and Digital Twins

## FR-061: Fake adapters

Provide fake adapters for:

* RoboMaster S1
* Leap Motion
* LEGO SPIKE
* Quest
* Agent CLI Mesh
* Network failure
* Battery warnings
* Sensor events

## FR-062: Simulation-first default

New projects must start in simulation unless an instructor deliberately selects physical mode.

## FR-063: Robot models

Provide simplified digital twins:

* S1 omnidirectional base and gimbal
* LEGO differential-drive base
* Generic LEGO motor and sensor visualization
* Leap hand representation
* Quest controller representation

## FR-064: Record and replay

Record normalized events and telemetry for:

* Debugging
* Student reflection
* Hardware-free lesson replay
* Regression tests
* Demonstration preparation

Replay must never send physical commands unless explicitly converted into a newly armed live session.

---

# 10.14 Instructor Console

## FR-065: Device overview

Show:

* Connected devices
* Battery
* Adapter status
* Firmware
* Active student
* Active session
* Safety profile
* Last command
* Last telemetry
* Heartbeat age
* Lease state
* Warning state

## FR-066: Arming workflow

Physical devices require:

1. Device selection
2. Safety-profile selection
3. Program validation
4. Instructor arm action
5. Visible armed indicator
6. Automatic arm expiry
7. Automatic disarm after stop or disconnect

## FR-067: Emergency controls

Provide:

* Stop selected device
* Stop program
* Stop all physical devices
* Revoke device lease
* Disconnect Quest control
* Disable Leap input
* Disarm class
* Clear command queues

## FR-068: Student and instructor roles

Students cannot:

* Change speed ceilings
* Enable advanced Python mode
* Enable S1 blaster
* Bypass dead-man control
* Change pairing permissions
* Approve AI-originated physical execution
* Modify adapter commands

---

# 10.15 Physical Safety Supervisor

## FR-069: Independent service

The safety supervisor must remain active even if:

* Student program crashes
* Browser closes
* Quest disconnects
* Leap tracking fails
* Agent Mesh disconnects
* Adapter process restarts

## FR-070: Watchdogs

Configurable defaults:

| Device/control            | Default timeout |
| ------------------------- | --------------: |
| S1 continuous motion      |      300–500 ms |
| LEGO continuous motion    |          500 ms |
| Quest dead-man heartbeat  |          300 ms |
| Leap continuous input     |          300 ms |
| Adapter process heartbeat |        1 second |

Timeout must trigger stop or disarm.

## FR-071: Bounded commands

Every physical movement command must be limited by:

* Maximum speed
* Maximum acceleration where supported
* Maximum duration
* Allowed capability
* Workspace or geofence where configured
* Session ownership
* Fresh heartbeat
* Arm state
* Input confidence where applicable

## FR-072: Command priorities

Priority order:

```text
1. Physical emergency stop
2. Instructor stop-all
3. Runtime safety stop
4. Device-local watchdog
5. Program stop
6. Student command
7. AI or wearable proposal
```

## FR-073: Safe voice and wearable policy

Authenticated wearables may perform:

* Status
* Pause program
* Stop selected device
* Emergency stop all
* Show diagnostics
* Request local arming

Wearables may not directly initiate physical movement in version 1.

## FR-074: AI-agent policy

Claude, Codex, or another LLM may:

* Suggest code
* Modify project files through normal reviewed development workflows
* Analyze telemetry
* Propose a mission
* Start simulation after permission

An AI agent may not:

* Arm physical devices
* Bypass instructor confirmation
* Increase speed limits
* Control the S1 blaster
* Execute unbounded movement
* Approve its own physical actions

---

# 10.16 Agent CLI Mesh, G2, and Meta Glasses Integration

## FR-075: Optional bridge

Create `packages/agent-mesh-bridge`.

It must connect to Agent CLI Mesh through authenticated documented APIs rather than importing vendor-specific Claude or Codex adapters.

## FR-076: Reusable Agent Mesh capabilities

Reuse where available:

* Device authentication
* Scoped tokens
* WebSocket events
* Reconnect
* Idempotency
* Audit
* G2 concise cards
* Meta glasses speech summaries
* Deterministic command routing
* Node and session status
* OpenAI-compatible G2 route

## FR-077: Agent status in CIT Studio

Display:

* Agent
* Node
* Workspace
* State
* Current meaningful action
* Last update
* Approval required
* Test result summary

## FR-078: Physical status in Agent CLI Mesh

Optional extension:

```text
PHYSICAL · classroom-pc
RUNNING · Leap controls S1
S1 battery: 71%
Quest: connected
LEGO: idle
```

## FR-079: Command boundary

Agent CLI Mesh may send only typed physical-studio commands:

```text
physical.status
physical.pause_program
physical.stop_program
physical.stop_device
physical.stop_all
physical.request_simulation
physical.request_arm
physical.open_project
```

No endpoint may accept arbitrary local Python or shell commands.

## FR-080: Existing G2 and Meta apps

Do not create a second G2 or Meta smart-glasses application unless the reuse audit proves extension is impossible.

Prefer extending:

* Existing physical-status cards
* Existing concise display format
* Existing speech summaries
* Existing device token model
* Existing event subscription
* Existing CLI-session selection

---

# 10.17 Logging, Telemetry, and Audit

## FR-081: Structured logs

Logs must include:

* Timestamp
* Session
* User
* Device
* Adapter
* Event type
* Command type
* Result
* Latency
* Safety decision
* Error code
* Correlation ID

## FR-082: Data minimization

Do not persist by default:

* Raw Leap hand frames
* Raw Quest hand frames
* Robot camera video
* Audio
* Full G2 or Meta conversations
* Device credentials
* Student Python environment variables

## FR-083: Audit events

Audit:

* Device arm/disarm
* Safety-profile changes
* Emergency stops
* Advanced Python activation
* Agent-originated requests
* Pairing and token revocation
* Device lease acquisition
* Physical program start
* Physical program completion
* Firmware operation
* Instructor overrides

## FR-084: Local retention

Retention must be configurable.

Provide:

* Session export
* Telemetry CSV/JSON export
* Event replay package
* Redacted diagnostic bundle

---

# 10.18 Offline and Reconnection Behaviour

## FR-085: Offline core

The following must work without internet:

* IDE
* Blocks
* Generated Python
* Pyodide execution
* Local runtime
* S1
* Leap Motion
* LEGO
* Quest local connection
* Simulation
* Logs

## FR-086: Quest reconnect

On Quest reconnect:

* Reauthenticate device
* Reconcile session
* Send latest state snapshot
* Do not resume motion automatically
* Require dead-man control again
* Display disarmed status

## FR-087: Adapter reconnect

On S1 or LEGO reconnect:

* Re-detect capabilities
* Revalidate firmware/SDK compatibility
* Clear stale movement queues
* Leave device disarmed
* Require new lease and arm action

## FR-088: Agent Mesh reconnect

Agent Mesh events may replay. Physical commands may not replay after expiry.

---

# 11. User Interface Requirements

## 11.1 Main navigation

```text
Projects
Program
Devices
XR
Simulation
Instructor
Logs
Settings
```

## 11.2 Program view

Must show:

* Blockly or Python editor
* Generated Python toggle
* Run controls
* Target mode
* Connected devices
* Safety state
* Console
* Telemetry
* Current event
* Current command
* Errors mapped to source

## 11.3 Device view

Each card shows:

```text
ROBOTMASTER S1 · s1-main
CONNECTED · ARMED
Battery 71%
Adapter healthy
Lease: Student A
Last command: drive.velocity · 120 ms ago
```

## 11.4 Safety visibility

`SIMULATION`, `PHYSICAL DISARMED`, `PHYSICAL ARMED`, and `EMERGENCY STOPPED` must be visually unmistakable.

## 11.5 Language

The interface must support:

* Korean
* English
* Technical identifiers remaining stable across languages

## 11.6 Error quality

Errors must be actionable.

Bad:

```text
Connection failed.
```

Good:

```text
LEGO SPIKE connection failed.

The hub was discovered but did not expose the expected Pybricks protocol.
Detected name: Pybricks Hub
Expected protocol: 1.3+
Suggested action: restart the hub, verify Pybricks firmware, then reconnect.
```

---

# 12. Non-Functional Requirements

# 12.1 Open-source and licensing

* Original CIT code: Apache License 2.0.
* Retain required MIT, Apache, MPL, PSF, and other notices.
* Generate an SBOM in CI.
* Maintain `THIRD_PARTY_NOTICES.md`.
* Reject dependencies lacking a clear licence.
* Document proprietary runtime dependencies separately.
* Do not require paid Unity, Unreal, Delightex, or Pybricks block-editor licences.

# 12.2 Supported systems

## Required

* Windows 11 runtime and development
* Windows 11 CI
* Ubuntu Linux CI
* Meta Quest 2
* Meta Quest 3
* Chromium-based browser for the studio
* RoboMaster S1 through the existing environment
* Leap Motion through the existing environment
* SPIKE Prime
* SPIKE Essential
* MINDSTORMS Robot Inventor

## Best effort

* Ubuntu hardware runtime
* Other OpenXR devices
* EV3
* Additional Pybricks hubs

# 12.3 Performance targets

On a healthy local network:

| Metric                                   |                                Target |
| ---------------------------------------- | ------------------------------------: |
| IDE to local-runtime acknowledgement     |                   under 100 ms median |
| Runtime command validation               |                           under 20 ms |
| Runtime-to-Quest telemetry update        |                      under 150 ms p95 |
| Quest input-to-runtime delivery          |                      under 100 ms p95 |
| Safety stop after control heartbeat loss |                          under 500 ms |
| Device-list initial load                 |                       under 2 seconds |
| Project load                             | under 2 seconds for ordinary projects |
| Quest target rendering                   |               72 Hz target on Quest 2 |
| Emergency-stop local acknowledgement     |                          under 100 ms |

These are product targets rather than guarantees of mechanical response.

# 12.4 Reliability

* Bounded queues
* Exponential reconnect backoff
* Duplicate suppression
* Capability refresh after reconnect
* Device process supervision
* Runtime crash recovery
* No stale movement replay
* Safe state after sleep/resume
* Project autosave
* Corruption-resistant project backups

# 12.5 Security

* Bind runtime to localhost or private interface by default.
* Require authentication for non-local clients.
* Use scoped tokens.
* Store secrets outside Git.
* Use OS-protected storage where practical.
* Reject expired commands.
* Reject replayed sensitive commands.
* Validate JSON schemas.
* Rate-limit commands.
* Restrict advanced CPython.
* No general shell API.
* No raw vendor SDK objects exposed to students.
* No public-internet listener by default.

# 12.6 Privacy

* Do not record video or audio by default.
* Do not persist biometric hand data by default.
* Display a clear recording indicator.
* Provide deletion and export.
* Separate student identity from raw device telemetry where possible.
* Do not send student telemetry to AI APIs without explicit action.

# 12.7 Maintainability

* Typed interfaces
* Versioned protocol
* Adapter contract tests
* Recorded sanitized fixtures
* Feature detection
* Compatibility matrix
* Dependency pinning
* Architecture decision records
* No vendor-specific types outside adapters

---

# 13. Domain Model

Minimum entities:

```text
RuntimeHost
ClientDevice
PhysicalDevice
VirtualDevice
DeviceAdapter
DeviceCapability
DeviceConnection
DeviceLease
SafetyPolicy
SafetyDecision
ProgramProject
ProgramSession
StudentExecution
CommandIntent
CommandResult
DeviceEvent
TelemetryFrame
CalibrationProfile
PairingToken
AuditRecord
AgentMeshConnection
ReplayRecording
```

## 13.1 PhysicalDevice

```text
id
display_name
device_type
model
adapter_id
transport
firmware_version
status
battery
capabilities_json
safety_policy_id
calibration_profile_id
last_seen_at
created_at
```

## 13.2 ProgramSession

```text
id
project_id
user_id
instructor_id
authoring_mode
execution_mode
state
safety_policy_id
armed_at
started_at
last_activity_at
ended_at
```

## 13.3 DeviceLease

```text
id
device_id
session_id
mode
acquired_at
expires_at
released_at
release_reason
```

## 13.4 CommandIntent

```text
id
session_id
device_id
source
capability
action
arguments_json
issued_at
expires_at
idempotency_key
safety_policy_id
state
result_json
completed_at
```

## 13.5 DeviceEvent

```text
id
device_id
session_id
sequence
category
name
values_json
source_timestamp
received_at
```

## 13.6 SafetyDecision

```text
id
command_id
policy_id
decision
reason_code
bounded_arguments_json
created_at
```

---

# 14. API Requirements

## 14.1 Runtime REST API

```http
GET    /api/v1/healthz
GET    /api/v1/readyz
GET    /api/v1/version
GET    /api/v1/diagnostics

GET    /api/v1/devices
GET    /api/v1/devices/{deviceId}
POST   /api/v1/devices/{deviceId}/connect
POST   /api/v1/devices/{deviceId}/disconnect
POST   /api/v1/devices/{deviceId}/calibrate
POST   /api/v1/devices/{deviceId}/stop

GET    /api/v1/projects
POST   /api/v1/projects
GET    /api/v1/projects/{projectId}
PUT    /api/v1/projects/{projectId}
POST   /api/v1/projects/{projectId}/validate

POST   /api/v1/sessions
GET    /api/v1/sessions/{sessionId}
POST   /api/v1/sessions/{sessionId}/arm
POST   /api/v1/sessions/{sessionId}/disarm
POST   /api/v1/sessions/{sessionId}/run
POST   /api/v1/sessions/{sessionId}/pause
POST   /api/v1/sessions/{sessionId}/stop
GET    /api/v1/sessions/{sessionId}/events
GET    /api/v1/sessions/{sessionId}/telemetry

POST   /api/v1/safety/stop-all
GET    /api/v1/safety/status
GET    /api/v1/safety/policies

POST   /api/v1/quest/pairing-codes
POST   /api/v1/quest/pair
POST   /api/v1/quest/revoke

GET    /api/v1/logs
POST   /api/v1/diagnostic-bundles
```

## 14.2 WebSockets

```text
WS /api/v1/events
WS /api/v1/student-runtime
WS /api/v1/quest
WS /api/v1/adapters
```

## 14.3 Forbidden APIs

The following must not exist:

```text
POST /exec
POST /shell
POST /powershell
POST /bash
POST /python-eval
POST /run-arbitrary-command
POST /device/raw-sdk-call
```

---

# 15. Error Codes

Minimum typed errors:

```text
DEVICE_NOT_FOUND
DEVICE_OFFLINE
DEVICE_NOT_ASSIGNED
DEVICE_LEASE_CONFLICT
DEVICE_NOT_ARMED
DEVICE_CAPABILITY_UNSUPPORTED
ADAPTER_NOT_FOUND
ADAPTER_UNHEALTHY
ADAPTER_VERSION_UNSUPPORTED
ADAPTER_PROCESS_LOST
COMMAND_EXPIRED
COMMAND_DUPLICATE
COMMAND_RATE_LIMITED
SAFETY_POLICY_DENIED
DEADMAN_REQUIRED
TRACKING_LOST
QUEST_DISCONNECTED
LEAP_DISCONNECTED
S1_CONNECTION_FAILED
LEGO_BLE_FAILED
LEGO_FIRMWARE_UNSUPPORTED
LEGO_PORT_INVALID
PROGRAM_VALIDATION_FAILED
PROGRAM_RUNTIME_FAILED
PYTHON_IMPORT_DENIED
ADVANCED_MODE_NOT_APPROVED
PAIRING_CODE_EXPIRED
AUTHENTICATION_FAILED
PROTOCOL_VERSION_UNSUPPORTED
AGENT_MESH_OFFLINE
```

Every error must contain:

* Code
* Human-readable message
* Device/session context
* Recovery suggestion
* Correlation ID
* Safe diagnostic details

---

# 16. Repository Structure

```text
cit-physical-xr/
├─ apps/
│  ├─ studio-web/                    # React, Blockly, Python editor
│  ├─ runtime-py/                    # FastAPI, session and device runtime
│  ├─ quest-godot/                   # Quest 2/3 OpenXR client
│  ├─ agent-mesh-bridge/             # Optional Agent CLI Mesh integration
│  └─ diagnostic-cli/                # Local administration and diagnostics
│
├─ packages/
│  ├─ protocol-schema/               # JSON Schema SSOT
│  ├─ protocol-ts/                   # Generated TS types/validators
│  ├─ protocol-py/                   # Generated Pydantic models
│  ├─ blockly-cit/                   # Custom blocks and Python generators
│  ├─ project-format/                # Project schema and migrations
│  ├─ student-sdk-py/                # citxr Python API
│  ├─ student-runtime-web/           # Pyodide and JS bridge
│  ├─ safety-core/                   # Policies and command bounding
│  ├─ device-simulator/              # Fake devices and replay
│  ├─ ui-components/                 # Shared interface components
│  └─ test-harness/                  # Adapter contract test framework
│
├─ adapters/
│  ├─ robomaster-s1/                 # Wrapper around existing S1 environment
│  ├─ leap-motion/                   # Wrapper around existing Leap environment
│  ├─ lego-pybricks/                 # SPIKE and Robot Inventor BLE adapter
│  ├─ mindstorms-ev3/                # Later EV3 adapter
│  ├─ quest-gateway/                 # Runtime-side Quest session handling
│  └─ agent-mesh/                    # Agent CLI Mesh protocol adapter
│
├─ firmware/
│  └─ lego-hub-agent/                # Pybricks MicroPython hub agent
│
├─ examples/
│  ├─ blocks-to-python/
│  ├─ leap-controls-s1/
│  ├─ leap-controls-lego/
│  ├─ quest-controls-s1/
│  ├─ quest-controls-lego/
│  ├─ synchronized-robots/
│  ├─ sensor-hud/
│  └─ agent-status-in-quest/
│
├─ tools/
│  ├─ reuse-audit/
│  ├─ protocol-codegen/
│  ├─ fixture-recorder/
│  ├─ project-migration/
│  └─ license-check/
│
├─ config/
│  ├─ default.yaml
│  ├─ schema.json
│  └─ examples/
│
├─ docs/
│  ├─ PRD.md
│  ├─ IMPLEMENTATION_PLAN.md
│  ├─ DECISIONS.md
│  ├─ REUSE_AUDIT.md
│  ├─ ARCHITECTURE.md
│  ├─ PROTOCOL.md
│  ├─ SAFETY.md
│  ├─ SECURITY.md
│  ├─ LICENSING.md
│  ├─ PROJECT_FORMAT.md
│  ├─ BLOCK_API.md
│  ├─ PYTHON_API.md
│  ├─ QUEST_SETUP.md
│  ├─ S1_SETUP.md
│  ├─ LEAP_SETUP.md
│  ├─ LEGO_SETUP.md
│  ├─ AGENT_MESH_INTEGRATION.md
│  ├─ CLASSROOM_OPERATIONS.md
│  ├─ TROUBLESHOOTING.md
│  └─ COMPATIBILITY.md
│
├─ tests/
│  ├─ contract/
│  ├─ integration/
│  ├─ e2e/
│  ├─ hardware/
│  ├─ safety/
│  └─ fixtures/
│
├─ .github/workflows/
├─ pyproject.toml
├─ uv.lock
├─ package.json
├─ pnpm-lock.yaml
├─ pnpm-workspace.yaml
├─ LICENSE
├─ THIRD_PARTY_NOTICES.md
└─ README.md
```

---

# 17. Recommended Implementation Stack

## Web and blocks

* TypeScript
* React
* Vite
* Blockly
* Monaco or CodeMirror
* Pyodide
* Web Workers
* IndexedDB for local drafts
* WebSocket client
* Vitest
* Playwright

## Local runtime

* Python 3
* FastAPI
* Pydantic
* WebSockets
* SQLite
* Structured logging
* `asyncio`
* `bleak`
* `pybricksdev`
* `pytest`
* Ruff
* Mypy or Pyright-compatible typing

## Quest

* Stable Godot 4 release pinned in compatibility documentation
* OpenXR
* Godot XR Tools
* GDScript
* Android export
* Godot unit/integration test approach where practical

## Build and dependency management

* `pnpm` for TypeScript workspaces
* `uv` for Python environments and lockfile
* Cross-platform Python or Node scripts rather than Bash-only tooling
* GitHub Actions on Windows and Ubuntu
* No Docker requirement for hardware runtime

---

# 18. Configuration

Local runtime configuration must live outside Git.

Example:

```yaml
runtime:
  id: classroom-pc
  bindHost: 127.0.0.1
  port: 8740
  dataDirectory: "C:\\Users\\Owner\\.cit-physical-xr"

devices:
  s1-main:
    adapter: robomaster-s1
    enabled: true
    executable: "C:\\s1-env\\Scripts\\python.exe"
    workingDirectory: "C:\\projects\\s1-leap"
    safetyPolicy: s1-student

  leap-main:
    adapter: leap-motion
    enabled: true
    executable: "C:\\s1-env\\Scripts\\python.exe"
    workingDirectory: "C:\\projects\\s1-leap"

  lego-spike-01:
    adapter: lego-pybricks
    enabled: true
    hubName: "CIT SPIKE 01"
    safetyPolicy: lego-student

quest:
  enabled: true
  pairingCodeTtlSeconds: 120
  tokenTtlDays: 30

agentMesh:
  enabled: false
  baseUrl: "https://private-agent-mesh-host"
  tokenRef: "secret://agent-mesh-device-token"

safety:
  defaultPhysicalMode: disarmed
  stopAllShortcut: "Ctrl+Shift+Escape"
  armTtlSeconds: 600
```

Secrets must use a secret-store reference rather than literal values.

---

# 19. Testing Requirements

## 19.1 Unit tests

Required coverage:

* Protocol validation
* Schema generation
* Block generation
* Deterministic Python output
* Project migrations
* Device capability filtering
* Event routing
* Idempotency
* Command expiry
* Safety bounding
* Speed caps
* Dead-man logic
* Device leases
* Tracking loss
* Pairing expiry
* Error mapping
* Korean/English labels

## 19.2 Adapter contract tests

Every adapter must pass a shared contract:

```python
describe_device_adapter(create_fake_s1_adapter)
describe_device_adapter(create_fake_leap_adapter)
describe_device_adapter(create_fake_lego_adapter)
describe_device_adapter(create_fake_quest_adapter)
```

Contract behaviours:

* Detect
* Describe
* Connect
* Disconnect
* Report capabilities
* Execute valid command
* Reject unsupported command
* Reject expired command
* Suppress duplicate command
* Emit telemetry
* Stop
* Recover from process or network failure
* Reconcile after reconnect

## 19.3 Safety tests

Fault-injection scenarios:

* Browser closed during movement
* Quest Wi-Fi disconnected
* Quest dead-man released
* Leap hand lost
* Leap process crash
* S1 process crash
* LEGO hub powered off
* Bluetooth interruption
* Runtime restarted
* Duplicate command
* Delayed command
* Expired command
* Two students request one robot
* AI-originated movement request
* Wearable-originated movement request
* Instructor stop-all

## 19.4 Integration tests

Use fake adapters to test:

* One block program controlling S1 and LEGO
* Leap event updating Quest and S1
* Quest input controlling LEGO
* Device capability changes updating toolbox
* Generated Python producing expected commands
* Agent Mesh status displayed in Quest
* Agent Mesh disconnect without physical-session failure

## 19.5 Hardware-in-the-loop tests

Required on actual hardware:

* RoboMaster S1
* Leap Motion
* SPIKE Prime or Robot Inventor
* Quest 2
* Quest 3

Record:

* Hardware model
* Firmware
* SDK/runtime version
* OS
* Adapter version
* Pass/fail
* Known limitations

## 19.6 CI

Required matrix:

```text
windows-latest
ubuntu-latest
```

CI must run:

* Licence validation
* Schema validation
* Code generation consistency
* Type checks
* Lint
* Unit tests
* Fake-adapter integration tests
* Web build
* Python package build
* Godot project validation where feasible
* SBOM generation

Hardware tests remain a documented release checklist.

---

# 20. Milestones

# Milestone 0: Discovery, Reuse Audit, and Foundation

## Deliver

* `docs/REUSE_AUDIT.md`
* `docs/IMPLEMENTATION_PLAN.md`
* `docs/DECISIONS.md`
* Repository scaffold
* Apache 2.0 licence
* Third-party notice structure
* Protocol-schema package
* Generated TS/Python protocol proof
* Fake adapter interfaces
* Basic CI
* Configuration schema
* Compatibility matrix skeleton
* Existing-repository path configuration

## Restrictions

* Do not modify existing S1 or Leap code.
* Do not connect to physical devices.
* Do not begin Quest or LEGO production implementation.

## Exit criterion

A clean clone installs, validates, builds, and tests on Windows and Ubuntu. Reuse decisions are documented with exact source paths and evidence.

---

# Milestone 1: Protocol, Runtime Core, and Simulation

## Deliver

* Local runtime API
* Device registry
* Capability registry
* Program-session state machine
* Device leases
* Safety-core first implementation
* Event router
* Command validator
* Fake S1
* Fake Leap
* Fake LEGO
* Fake Quest
* Browser simulator
* Stop-all implementation
* Recorded-event replay

## Exit criterion

A simulated block/Python program controls fake S1 and fake LEGO while fake Leap and fake Quest provide inputs. All safety fault tests pass.

---

# Milestone 2: Existing RoboMaster S1 and Leap Motion Integration

## Deliver

* S1 subprocess bridge
* Leap subprocess bridge
* Handshake and health protocol
* Existing-environment compatibility diagnostics
* Adapter contract tests
* Normalized Leap events
* S1 capabilities
* Watchdog and emergency stop
* Working Leap → event router → student program → S1 flow
* Regression comparison with the current direct Leap → S1 behaviour

## Exit criterion

The existing Leap-controlled S1 demonstration works through the new adapter architecture without losing required behaviour, and tracking loss stops the S1.

---

# Milestone 3: Blockly, Generated Python, and Safe Student Runtime

## Deliver

* Blockly workspace
* Core block categories
* S1 blocks
* Leap blocks
* Simulation blocks
* Deterministic Python generator
* Pyodide Web Worker
* `citxr` student SDK
* Run/pause/stop
* Source-map errors
* Project save/load
* Blocks-to-Python transition

## Exit criterion

A student can create a block program, inspect generated Python, run it in simulation, and control the actual S1 through an instructor-armed session.

---

# Milestone 4: LEGO SPIKE and Robot Inventor

## Deliver

* Pybricks setup documentation
* BLE discovery
* Hub capability detection
* Persistent hub agent
* Framed hub protocol
* Motor and sensor capabilities
* LEGO blocks
* Generated Python API
* Host-controlled mode
* Stop-on-disconnect
* Autonomous program download proof
* SPIKE Prime and Robot Inventor compatibility tests

## Exit criterion

One block/Python program coordinates RoboMaster S1 and a LEGO robot, with exact device routing and independent emergency stop.

---

# Milestone 5: Quest 2 and Quest 3 Runtime

## Deliver

* Godot/OpenXR project
* Quest pairing
* Quest authentication
* Controller events
* Hand events where supported
* HUD
* Virtual S1
* Virtual LEGO robot
* Runtime telemetry
* Dead-man control
* Emergency stop
* Quest 2 performance profile
* Quest 3 enhancement detection
* Manual calibration

## Exit criterion

The same APK runs on Quest 2 and Quest 3. Quest controls a simulated robot and then an instructor-armed LEGO or S1 device. Releasing dead-man control stops movement.

---

# Milestone 6: Unified Multi-Device Projects and Instructor Console

## Deliver

* Dynamic toolbox
* Parallel actions
* Coordinated-failure policies
* Instructor device dashboard
* Arm/disarm workflow
* Class stop-all
* Device assignment
* Session replay
* Student/instructor roles
* Korean/English UI
* Demonstration mode

## Exit criterion

An instructor can manage S1, LEGO, Leap, and two Quest clients while students run isolated projects without device-lease conflicts.

---

# Milestone 7: Agent CLI Mesh, G2, and Meta Glasses Reuse

## Deliver

* Agent Mesh bridge
* Reused protocol/security packages or documented adapter
* CLI-agent status in CIT Studio
* CLI-agent status in Quest HUD
* Physical status extension for existing G2/Meta clients
* Stop/pause commands from trusted wearable
* Scoped tokens
* Audit integration
* Agent Mesh disconnect isolation
* Documentation of reused modules

## Exit criterion

Claude/Codex status can appear in Quest and the existing G2/Meta workflow. A trusted wearable can stop a physical session but cannot initiate movement.

---

# Milestone 8: Advanced Python and Optional EV3

## Deliver

* Instructor-controlled CPython worker
* Advanced project profiles
* Import policy
* Local file workspace
* OpenCV or AI integration example
* EV3 proof-of-concept adapter
* Advanced diagnostics
* Resource limits
* Security documentation

## Exit criterion

An approved advanced project uses standard CPython for an AI or computer-vision workflow while all physical commands still pass through the same safety supervisor.

---

# Milestone 9: Hardening and Release

## Deliver

* Installer/startup scripts
* Windows runtime launcher
* Compatibility diagnostics
* Upgrade and rollback plan
* Full classroom operations guide
* Security review
* Licence review
* SBOM
* Hardware release checklist
* Recovery tests
* Performance report
* Complete example projects
* Public open-source repository preparation

## Exit criterion

The owner can install and operate the system on the actual classroom PC, Quest 2, Quest 3, RoboMaster S1, Leap Motion, and LEGO hardware using documented procedures.

---

# 21. Acceptance Criteria

Version 1 is accepted only when all requirements below are met.

1. The repository is publicly licensable under Apache 2.0.
2. The project builds and tests on Windows 11 and Ubuntu CI.
3. `docs/REUSE_AUDIT.md` identifies all reused Agent CLI Mesh, G2, Meta glasses, CLI, S1, and Leap modules.
4. The existing S1 Python environment is not silently replaced.
5. Existing Leap → S1 functionality works through adapters.
6. Leap input can control a virtual Quest object.
7. Leap tracking loss stops continuous physical motion.
8. Blockly generates readable Python.
9. The generated Python uses the same public API as handwritten Python.
10. A blocks project can control a simulated S1.
11. A blocks project can control the physical S1 after instructor arming.
12. A blocks project can control SPIKE Prime or Robot Inventor.
13. One program can coordinate S1 and LEGO.
14. Unsupported device blocks are hidden or rejected.
15. Quest 2 runs the CIT XR Runtime.
16. Quest 3 runs the same CIT XR Runtime.
17. Quest telemetry shows S1 and LEGO state.
18. Quest controller input can control an assigned robot.
19. Releasing dead-man control stops movement.
20. Quest disconnection stops continuous movement.
21. No student or wearable command bypasses the safety supervisor.
22. No expired movement command executes after reconnection.
23. Two program sessions cannot control one physical device simultaneously.
24. Instructor stop-all works regardless of student program state.
25. S1 blaster control is absent from the default student interface.
26. Physical runtime works without Agent CLI Mesh.
27. Agent CLI Mesh status can be displayed when the bridge is enabled.
28. Existing G2 or Meta clients are extended rather than duplicated where possible.
29. Wearables can stop but cannot initiate physical movement in version 1.
30. No credentials are present in source, logs, fixtures, or diagnostic bundles.
31. All third-party licences are documented.
32. Hardware compatibility is recorded with tested versions.
33. README and setup documentation are complete.
34. All safety fault-injection tests pass.
35. All example projects include expected output and safety instructions.

---

# 22. Risks and Mitigations

## Risk: Existing S1 environment is fragile

**Mitigation:**

* Preserve exact Python executable and dependencies
* Run as subprocess
* Record working environment
* Add compatibility diagnostics
* Use fixtures
* Avoid in-place upgrade
* Maintain rollback

## Risk: Leap bindings or tracking service change

**Mitigation:**

* Adapter isolation
* Feature detection
* Version pinning
* Recorded event fixtures
* Normalized event contract
* Existing implementation fallback

## Risk: LEGO BLE instability

**Mitigation:**

* Named device bindings
* Reconnect diagnostics
* Heartbeat
* Hub-local stop
* Short commands
* Packet limits
* Simulation fallback
* Tested USB Bluetooth adapters documented

## Risk: Quest Wi-Fi latency or disconnect

**Mitigation:**

* Dead-man heartbeat
* Local device watchdogs
* No motion replay
* State interpolation
* Automatic disarm
* Visible connection indicator

## Risk: Quest 2 performance limitations

**Mitigation:**

* Quest 2 baseline
* Simplified shaders and models
* Throttled telemetry
* Interpolation
* Separate render and network rates
* Performance profiles

## Risk: Student Python escapes restrictions

**Mitigation:**

* Pyodide default
* No direct hardware SDK
* RPC capability boundary
* Advanced CPython instructor-only
* Separate process
* No inherited secrets
* Runtime safety validation

## Risk: Voice or AI sends unsafe command

**Mitigation:**

* Typed commands
* No movement from wearables
* AI proposals only
* Local instructor arming
* Expiry
* Exact device selection
* Audit
* Safety supervisor

## Risk: Agent CLI Mesh creates coupling

**Mitigation:**

* Optional bridge
* Core works offline
* No Claude/Codex types in physical runtime
* Shared package extraction only when justified
* Contract tests
* No circular dependency

## Risk: Licence conflict

**Mitigation:**

* Reuse audit
* SPDX headers
* SBOM
* Third-party notices
* CI licence checks
* Reject unclear dependencies

## Risk: Physical and virtual coordinates diverge

**Mitigation:**

* Manual calibration
* Visible uncertainty
* Digital-twin smoothing
* Recalibration action
* No safety reliance on virtual alignment in v1

---

# 23. Required Documentation

Implementation is incomplete until these documents exist:

```text
README.md
LICENSE
THIRD_PARTY_NOTICES.md
docs/PRD.md
docs/IMPLEMENTATION_PLAN.md
docs/DECISIONS.md
docs/REUSE_AUDIT.md
docs/ARCHITECTURE.md
docs/PROTOCOL.md
docs/SAFETY.md
docs/SECURITY.md
docs/LICENSING.md
docs/PROJECT_FORMAT.md
docs/BLOCK_API.md
docs/PYTHON_API.md
docs/QUEST_SETUP.md
docs/S1_SETUP.md
docs/LEAP_SETUP.md
docs/LEGO_SETUP.md
docs/AGENT_MESH_INTEGRATION.md
docs/CLASSROOM_OPERATIONS.md
docs/TROUBLESHOOTING.md
docs/COMPATIBILITY.md
```

README must include:

* What the system does
* Open-source status
* Supported devices
* Quick simulation start
* Hardware safety warning
* Development setup
* Project structure
* Current milestone status
* Explicit list of incomplete features
* No unsupported claims

---

# 24. Definition of Done

A feature is done only when:

* Domain behaviour is implemented.
* Protocol schema is updated.
* TypeScript and Python types are regenerated.
* Unit tests pass.
* Adapter contract tests pass.
* Relevant safety tests pass.
* Errors are actionable.
* UI state is updated.
* Logs and audit events are emitted.
* No secret is logged.
* Korean and English labels are covered where relevant.
* Documentation is updated.
* Compatibility information is updated.
* CI passes on Windows and Ubuntu.
* Hardware behaviour is verified where the feature touches hardware.
* The repository remains runnable.
* No physical command bypasses the safety supervisor.
* The feature does not create a new general-purpose execution endpoint.

---

# 25. Master Prompt for Codex

Place this PRD at `docs/PRD.md`, then use the following prompt from the root of `cit-physical-xr`:

```text
Implement the CIT Physical XR Studio described in docs/PRD.md.

Read the entire PRD before changing files.

Important existing context:
- There is already a working PC-based Python environment for RoboMaster S1.
- Leap Motion already controls the RoboMaster S1 in that environment.
- There are existing Agent CLI Mesh, Even Realities G2, Meta smart-glasses, Claude Code, Codex CLI, wearable, and multi-machine communication modules that may be reusable.
- The existing S1 and Leap implementation must be wrapped and preserved rather than rewritten before it is covered by tests.
- Core physical control must work locally without Agent CLI Mesh.
- Agent CLI Mesh must be integrated only through an optional bridge.
- Quest 2 is the baseline XR device; Quest 3 enhancements must be conditional.
- Blockly and readable Python are the primary student authoring modes.
- Godot/OpenXR is the Quest runtime, not the primary code editor.
- No student, Quest, Leap, wearable, or AI module may bypass the physical safety supervisor.
- Do not implement a general shell or arbitrary execution endpoint.
- Do not expose physical-device services publicly.
- Do not store credentials in Git.

Your first deliverable is Milestone 0 only.

Milestone 0 tasks:
1. Read docs/PRD.md completely.
2. Locate the existing local repositories and integrations from owner-provided paths or configuration.
3. Create docs/REUSE_AUDIT.md.
4. The reuse audit must inspect:
   - Agent CLI Mesh protocol
   - security and scoped-device-token code
   - configuration
   - persistence
   - observability
   - wearable API
   - Even G2 client
   - Android/Meta glasses bridge
   - WebSocket reconnect and replay
   - normalized event envelope
   - existing RoboMaster S1 Python environment
   - existing Leap Motion integration
5. Do not modify those existing repositories during the audit.
6. Create docs/IMPLEMENTATION_PLAN.md mapping every PRD requirement to milestones and planned files.
7. Create docs/DECISIONS.md with initial ADRs.
8. Scaffold the repository structure needed for:
   - TypeScript web application
   - Python local runtime
   - protocol schemas and generated language bindings
   - Godot Quest application
   - device adapters
   - fake-device test harness
9. Implement the versioned protocol envelope and base schemas.
10. Generate and test TypeScript and Python protocol models.
11. Define the DeviceAdapter contract.
12. Create fake S1, Leap, LEGO, and Quest adapters.
13. Add Windows and Ubuntu CI.
14. Add licence checks and a THIRD_PARTY_NOTICES.md structure.
15. Add configuration-schema validation.
16. Add tests for:
   - protocol validation
   - command idempotency
   - command expiry
   - device identity
   - device leases
   - safety denial
   - duplicate suppression
   - Windows/Linux path handling
17. Add a README describing development setup and current limitations only.
18. Run all available builds, tests, lint, type checks, schema generation, and licence checks.
19. Report:
   - files created
   - commands run
   - tests passed or failed
   - reuse candidates found
   - unresolved repository paths
   - architectural decisions
   - deviations from the PRD
   - remaining work

Do not begin Milestone 1.
Do not connect to physical hardware.
Do not modify the existing S1 or Leap environment.
Do not claim the product works beyond what Milestone 0 verifies.
Keep the repository runnable at the end of the milestone.
```

After Milestone 0 is reviewed, continue exactly one milestone at a time.
