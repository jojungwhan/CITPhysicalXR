# Architecture Decisions

- Status: initial decisions for Milestone 0
- Date: 2026-08-16

Changes are append-only. Superseded decisions remain in this file with links to their replacements. A decision marked `Proposed` is not implementation authority until accepted.

## ADR-001 — Separate Physical XR repository

Status: Accepted (PRD)

`cit-physical-xr` is a separate repository from Agent CLI Mesh. The physical runtime has its own release cycle and remains usable without Agent Mesh. Shared behavior crosses an explicit package or authenticated API boundary and never creates a circular dependency.

## ADR-002 — PC-local runtime is the physical authority

Status: Accepted (PRD)

Only the PC-local runtime may send commands to physical adapters, and every path passes through the safety supervisor. Studio, Quest, Leap, wearables, and AI integrations produce typed input/events or requests; they do not receive adapter objects or vendor SDK access.

## ADR-003 — Blockly authors programs; Godot renders XR

Status: Accepted (PRD)

Blockly and readable Python are the primary student authoring modes. Godot/OpenXR is the reusable Quest client, not the primary editor or block generator.

## ADR-004 — One reusable Quest runtime

Status: Accepted (PRD)

One CIT XR Runtime is installed on Quest 2 and Quest 3. Ordinary student program edits travel over the local protocol and do not require APK rebuilds.

## ADR-005 — Wrap the existing S1/Leap implementation

Status: Accepted (PRD)

The owner-confirmed working S1/Leap checkout and interpreter are external compatibility assets. They will be wrapped by a subprocess adapter only after fake-adapter and recorded contract tests exist. CIT tooling will not upgrade that environment in place.

## ADR-006 — Browser-contained Python is the classroom default

Status: Accepted (PRD)

Pyodide in a Web Worker is the default student execution environment. It receives a narrow CIT RPC capability and no local filesystem, process, arbitrary socket, environment, adapter, or secret access.

## ADR-007 — Advanced CPython is separate and instructor-controlled

Status: Accepted (PRD)

Advanced CPython is deferred to Milestone 8, disabled by default, and runs as a separately constrained process. It still cannot bypass the same runtime and safety supervisor.

## ADR-008 — Capabilities drive APIs and toolboxes

Status: Accepted (PRD)

Stable device identities expose explicit capability manifests. Unsupported actions are hidden in the editor and rejected at the protocol/runtime boundary. Device family or display-name matching never substitutes for an exact `deviceId`.

## ADR-009 — Safety is below all student and remote code

Status: Accepted (PRD)

Safety, leases, arming, expiry, source policy, dead-man state, watchdogs, and bounds are evaluated below student and remote request layers. Stops have priority and remain available while ordinary motion is denied.

## ADR-010 — Movement is never replayed

Status: Accepted (PRD)

Telemetry and status may be replayed with historical markers. Movement queues are cleared on disconnect/restart, expired commands are rejected, and reconnect requires a new lease, arm state, and live control/dead-man signal.

## ADR-011 — Quest 2 is the XR baseline

Status: Accepted (PRD)

Every core lesson and safety UI must work on Quest 2. Quest 3 enhancements are feature-detected and cannot become hidden prerequisites.

## ADR-012 — JSON Schema is the wire source of truth

Status: Accepted (PRD)

Draft 2020-12 JSON Schema defines protocol wire shapes. Milestone 0 commits deterministic generated TypeScript declarations and Python Pydantic models plus the source schemas and cross-language fixtures. Generated files are checked for drift in CI and are not hand-edited.

## ADR-013 — Agent CLI Mesh is optional and read-only by default

Status: Accepted (PRD)

The initial bridge carries status, events, diagnostics, project information, and typed pause/stop/request operations. It does not carry unconfirmed movement. Claude/Codex vendor types and process adapters remain in Agent Mesh.

## ADR-014 — Original M0 implementation; no copied unlicensed source

Status: Accepted

The audited Agent CLI Mesh and RoboMaster repositories do not currently provide a top-level licence for their original code. Milestone 0 therefore implements original schema/config/fake/safety-foundation code from the PRD and records external behavior as evidence only. Later direct package extraction requires an explicit compatible owner licence and provenance entry.

Consequences:

- Agent Mesh integration is API-based unless licensing changes.
- The S1/Leap adapter wraps an owner-designated external checkout rather than vendoring it.
- No alternate-branch RoboMaster movement code is copied.

## ADR-015 — Python owns adapter contracts and fake devices

Status: Accepted

The local runtime is Python, so `DeviceAdapter`, fake S1/Leap/LEGO/Quest implementations, leases, command-ledger behavior, and their contract harness are Python packages. TypeScript consumes only the generated wire contract. This avoids maintaining two independent adapter semantics in Milestone 0.

## ADR-016 — M0 safety foundation is fail-closed and non-dispatching

Status: Accepted

Milestone 0 provides public contracts and tests for command expiry/idempotency, exclusive leases, device identity, and denial policy. It does not expose a runtime API or dispatch physical commands. Fake adapters execute only in-memory simulated actions and are never treated as proof of Milestone 1 simulation or hardware behavior.

## ADR-017 — Cross-platform workspace and version isolation

Status: Accepted

The repository uses a pnpm workspace for TypeScript and a uv workspace for Python. CIT development supports maintained CPython versions independently from the legacy Python 3.8 DJI environment. Cross-platform scripts use Node or Python, not Bash-only automation.

Tested Milestone 0 tool baselines on the discovery host:

- Node.js 22.17.0
- pnpm 10.28.2
- Python 3.13.5 for CIT development
- uv 0.4.30
- Git 2.47.1.windows.2

The exact dependency graph is recorded in `pnpm-lock.yaml` and `uv.lock`. The legacy DJI interpreter remains external and unchanged.

## ADR-018 — Configuration and repository paths are non-secret data

Status: Accepted

Committed files contain schemas and examples only. Active runtime configuration lives outside Git. Repository entries carry separate Windows and Linux absolute paths and are selected without translating path syntax. Credentials are accepted only as secret-store references, never literal config values.

## ADR-019 — Existing glasses applications are extended, not replaced

Status: Accepted

Milestone 7 changes the existing Agent Mesh Even G2 and Android/Meta applications through a separately reviewed change. This repository contains only an optional bridge scaffold. The discovered RoboMaster glasses branch is reference-only because its wearable movement behavior conflicts with Physical XR v1.

## ADR-020 — Godot remains a scaffold in Milestone 0

Status: Accepted

Godot is not installed on the current host, and Quest production work belongs to Milestone 5. Milestone 0 creates a parseable project/scene/script scaffold and a static validation gate only. It does not add OpenXR plugins, export templates, APK claims, or Quest hardware tests.

## ADR-021 — SBOM and licence validation are generated locally

Status: Accepted

CI generates a CycloneDX JSON inventory from the committed pnpm and uv locks and validates repository/package licence declarations against an explicit allowlist and notices. Hardware/vendor runtimes are documented separately because they are not distributable application dependencies.

## ADR-022 — Speed is a fraction everywhere; adapters convert to device units

Status: Accepted (Milestone 4)

A student writes `speed=0.3` whether they are driving a RoboMaster S1 or a LEGO motor. The device's own unit -- degrees per second on a Pybricks motor, metres per second on an S1 -- is the adapter's business, not the student's and not the safety supervisor's.

Two reasons this is a rule rather than a preference. A number a student carries from one robot to the next is the point of one programming environment (G-001). And the supervisor's `max_speed` bound (FR-071) has to mean something without knowing which robot it is: clamping `speed` to `0.5` is only a real ceiling if `1.0` means full power on every device. The Milestone 3 LEGO block sent `speed=200` in degrees per second, which the supervisor clamped to `0.5`, i.e. to a quarter of one degree per second. That block is replaced.

## ADR-023 — `pybricksdev` is the hardware transport, and its licence tree is an open owner decision

Status: Accepted 2026-08-17 (owner) — **option 3**. Nothing is implemented yet: the split below is authorized, not built, and `--extra hardware` still installs the contested tree today. Implementing it belongs to LEGO hardware bring-up.

The owner's decision: host-controlled mode runs on `bleak` alone (MIT, clean tree), and `pybricksdev` is kept only for the autonomous download path FR-048 needs. An ordinary classroom therefore never installs `asyncssh`, `cffi`, or an `mpy-cross` build with no licence metadata; the machine that installs a program onto a hub does, deliberately, and the licence gate has to say so rather than be widened. The allowlist is unchanged.

The reasoning that was put to the owner follows, unedited.

The Pybricks BLE service UUIDs, command and event byte codes, and the framing of `WriteStdin`/`WriteStdout` belong to the firmware project and change with the firmware. Hardcoding them would mean CIT silently owning a copy of someone else's wire format. `pybricksdev` is MIT, is maintained by that project, and is what PRD section 2.3 names. It also supplies the `mpy-cross` compile-and-download path that FR-048 needs. It is therefore the transport, behind the injectable boundary FR-052 requires, and it is an **optional** dependency so a machine with no hub never installs a radio stack.

The problem, measured rather than assumed: installing `--extra hardware` puts these in the environment.

| Package                | Licence                       | Allowlisted                                  |
| ---------------------- | ----------------------------- | -------------------------------------------- |
| `pybricksdev`, `bleak` | `MIT`                         | yes                                          |
| `asyncssh`             | `EPL-2.0 OR GPL-2.0-or-later` | **no**                                       |
| `cffi`                 | `MIT-0`                       | **no**                                       |
| `mpy-cross-v5`, `-v6`  | no licence metadata           | **no**                                       |
| `aioserial`, `tqdm`    | `MPL-2.0`, `MPL-2.0 AND MIT`  | allowed, but the metadata does not normalize |

`pnpm license:check` passes today only because the extra is not installed here; it fails on a machine where it is. Milestone 3 met the same question with `jsdom` and answered it by dropping the dependency rather than widening the allowlist, and NFR 12.1 says to reject dependencies without a clear licence.

The options, none of which are taken unilaterally:

1. Accept the extra as a **tool** rather than a distributed dependency, and teach the licence gate to treat the `hardware` extra separately.
2. Replace it with `bleak` alone (MIT, clean tree) and hand-write the Pybricks GATT layer, accepting an unverifiable copy of someone else's wire protocol and losing FR-048's compiler.
3. Ship host-controlled mode on `bleak` and keep `pybricksdev` only for the autonomous download path, so an ordinary classroom never installs the contested tree.

## ADR-024 — A hub is never owned by the host and by its own program at once

Status: Accepted (Milestone 4)

FR-053 forbids simultaneous host and autonomous ownership, and the reason is specific to LEGO: a downloaded program keeps running after the runtime stops talking, so "the runtime is idle" stops meaning "the robot is idle". Ownership is an explicit adapter state. Moving to autonomous requires an instructor id; while it holds, host commands are refused rather than queued; installing a program stops the motors first.

## ADR-025 — Hubs are bound by advertised name, never by Bluetooth address

Status: Accepted (Milestone 4)

The PRD forbids committing Bluetooth addresses. Rather than adding a field and a rule about not filling it in, the configuration schema has no address field at all: a hub is bound by the name it advertises, which an instructor sets in the Pybricks app. There is then nothing device-secret in a class configuration, and FR-052's "named device binding" is the only binding that exists.

## ADR-026 — Adapter keep-alive runs on the runtime tick, not on a task of its own

Status: Accepted (Milestone 4)

The LEGO hub stops on its own after 500 ms of silence (FR-049), so something has to speak to it several times a second. That heartbeat is emitted from `Runtime.tick()`, the same loop that drives the safety watchdogs, and never from a background task owned by the adapter. A task of its own would keep feeding a hub after the loop that was supposed to supervise it had died -- the exact failure the watchdog exists to prevent.

## ADR-027 — A role is a token the runtime issued, never a field in the request

Status: Accepted (Milestone 6)

Before Milestone 6 the runtime believed whatever a request body said about who was asking. `POST /api/commands` took its `source` from the body, so a student page could send `source: "instructor"` and receive `INSTRUCTOR_STOP_ALL` priority; `POST /api/safety/arm` took `instructor_id` from the body, so any caller could name themselves the instructor who armed a robot. FR-068 is a list of things a student cannot do, and none of it can be enforced while identity is self-declared.

Every mutating route now requires a token the runtime issued. `POST /api/auth/join` returns one; the instructor role additionally requires a passcode, which the runtime generates at startup and prints once to its own log. Tokens are held as SHA-256 digests, so the runtime cannot leak a working token from memory or a crash dump, and they expire.

The passcode is deliberately weak security and strong enough for what it defends. The runtime already refuses to bind anything but loopback (ADR-002 and the M1 report), so the attacker this stops is the other browser tab on the same machine, not the network. A password store would be a bigger promise than a classroom runtime can keep.

Authorization is a runtime concern, not an HTTP concern: `cit_runtime.roles` names each privileged action and answers yes or no, and `api.py` only maps the refusal to a 403. A test can therefore prove that a student cannot arm a device without going through a web server.

## ADR-028 — A dead-man control is attested by a heartbeat, not asserted by a caller

Status: Accepted (Milestone 6)

FR-068 says a student cannot bypass the dead-man control, and until now `deadmanActive` was a boolean in the request body that the student's own page filled in. The Studio filled it with `true` unconditionally. The rule was therefore enforced against nobody.

The supervisor now derives it: a device's dead-man is active only if a heartbeat for that device arrived within its watchdog timeout (FR-070, 300 ms). The request field is gone from the physical path. Holding the control in the Studio starts that heartbeat and releasing it stops it, so letting go and losing the browser look identical to the runtime -- which is the property the control exists to have.

This tightens physical mode only. Simulation never required a dead-man and still does not, because FR-062 has to work with nobody in the room.

## ADR-029 — The command queue is the dispatch path, and a device drains its own

Status: Accepted (Milestone 6 follow-up)

`CommandQueue` implemented FR-072 priority ordering and FR-067 clearing since Milestone 1, and `submit()` dispatched straight to the adapter. The queue was therefore a structure beside the runtime rather than in it: a stop could not overtake a command that was already waiting, and clearing a queue cleared something no command had ever been in. Both requirements were enforced against nobody, in the same sense ADR-027 and ADR-028 mean.

Every command now enters the queue, and the outcome is still returned to the caller that submitted it. What changed is that while that caller waits, the runtime may run somebody else's higher-priority command for that device first.

Draining is **per device**, not per runtime. A robot executes one command at a time and a lease is per device, so serializing a device is physics; serializing the room would make one student's slow command the reason another student's robot stood still (FR-057). Each device has a lane, and whoever submits does the draining — there is no background worker to supervise, nothing to leak when a runtime stops, and no command left in a queue because its task was never started.

Two consequences are deliberate. A cleared queue is a refusal, not a silence: every discarded command is answered with the reason it never ran and recorded as denied, so a student whose robot did nothing after a stop-all can be told why instead of watching a page wait forever. And the emergency paths — `stop_device`, `stop_all`, watchdogs — do not queue behind a lane, because a stop that waits for the command it is meant to interrupt is not a stop.

## ADR-030 — A project is autosaved only once it exists on disk, and opening one loads its blocks

Status: Accepted (Milestone 6 follow-up)

The project store has been built for autosave since Milestone 6 — atomic write, retained previous version — and nothing called it, so a lesson's work depended on a child remembering a button. Editing now writes about a second and a half after the edits stop.

It does not autosave a project the Studio invented at page load. That project's id is a fixed constant, so every tab in the classroom has the same one, and autosaving it would have two students writing one file. A project is autosaved once the runtime has it: opened from the Projects list, or saved once by hand.

Turning autosave on made a Milestone 6 bug automatic and silent, so it is fixed here: opening a project set the document in memory and left the editor showing the previous program, and the editor's next change event wrote its own blocks over the ones that had just been loaded. Opening now loads the stored blocks into the workspace first. The translation back into Blockly's load format lives in `packages/blockly-cit`, with the catalog it needs and away from Blockly itself, because Blockly's Node entry point needs `jsdom` and Milestone 3 dropped `jsdom` rather than widen the licence allowlist. It is exact only while a catalog block has at most one value input and at most one statement input, and a test asserts that property rather than trusting it.

## ADR-031 — An export is a file the page builds, not a link the browser follows

Status: Accepted (Milestone 6 follow-up)

The audit log, a replay package, and a project are fetched with the runtime token in an `Authorization` header. A plain link carries no header, and putting a token in a query string writes it into browser history, so an export cannot be a download URL: the document is already in memory by the time anybody wants it saved. The Studio therefore builds a blob and asks the browser to save it, revoking the object URL afterwards so a lesson's exports do not accumulate in the tab.

Everything that touches the DOM is injected, so the naming and the lifetime are tested in Node without a DOM.

## Deviations from the PRD

None at Milestone 0 start. The local workspace directory is named `CITPhysicalXR`, while the Git product/repository identity remains `cit-physical-xr`; this is a host path detail, not an architecture deviation.

## Open decisions

1. Owner-confirmed path to the working Leap runtime, built bridge DLL, and exact interpreter.
2. Owner licence designation for Agent CLI Mesh, RoboMaster gesture control, and classroom mission source.
3. Tested stable Godot/OpenXR/Godot XR Tools versions at the start of Milestone 5.
4. Exact local secret-store implementation for Quest pairing tokens, decided before pairing code is implemented.
5. ~~ADR-023: whether the `hardware` extra's licence tree is acceptable~~ — decided 2026-08-17, option 3. What remains is engineering, not a decision: splitting the transport so host-controlled mode needs `bleak` alone, and teaching `license:check` to say which extra a package came from.
6. Whether the LEGO drive-base geometry (56 mm wheels, 114 mm axle track) should be per-device configuration rather than a default, decided when a real build is measured.
