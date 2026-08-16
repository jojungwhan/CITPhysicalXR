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

## Deviations from the PRD

None at Milestone 0 start. The local workspace directory is named `CITPhysicalXR`, while the Git product/repository identity remains `cit-physical-xr`; this is a host path detail, not an architecture deviation.

## Open decisions

1. Owner-confirmed path to the working Leap runtime, built bridge DLL, and exact interpreter.
2. Owner licence designation for Agent CLI Mesh, RoboMaster gesture control, and classroom mission source.
3. Tested stable Godot/OpenXR/Godot XR Tools versions at the start of Milestone 5.
4. Exact local secret-store implementation for Quest pairing tokens, decided before pairing code is implemented.
