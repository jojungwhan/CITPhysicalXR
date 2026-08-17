# Implementation Plan

- Status: Milestones 0, 1, 3, 4, and 6 complete, plus the Milestone 6 follow-up of 2026-08-17 (`docs/MILESTONE_6_FOLLOWUP_REPORT.md`): the command queue is now the dispatch path (FR-072, FR-067, ADR-029), projects autosave and open with their blocks (FR-001, ADR-030), and the audit, replay, and project exports leave as files (FR-084, ADR-031). Every device so far is simulated: M4 built the LEGO adapter, hub agent, and protocol, but no hub was connected (no Bluetooth adapter on the development host). M6 added roles, the instructor console, projects on disk, replay, and a Korean/English interface, and tightened two rules that were previously self-declared by the caller (ADR-027, ADR-028). M2 and M5 are deferred until hardware is available.
- Authoritative product specification: `docs/PRD.md` version 1.0, 2026-08-16

## Delivery rule

Only one milestone is implemented at a time. Each milestone ends with a runnable repository, documented evidence, and owner review. This plan does not authorize later milestones, hardware connections, firmware changes, or edits to the existing S1/Leap and Agent CLI Mesh repositories.

| Milestone | Scope                                   | Primary planned areas                                                                                                               | Exit evidence                                                                               |
| --------- | --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| M0        | Discovery, reuse audit, foundation      | `docs`, `packages/protocol-*`, `packages/device-simulator`, `packages/test-harness`, `packages/safety-core`, `config`, CI scaffolds | Clean install, generation, validation, build, lint, type checks, tests on Windows/Ubuntu    |
| M1        | Runtime core and simulation             | `apps/runtime-py`, `apps/studio-web`, safety/session/device services, simulator/replay                                              | Fake multi-device program and complete M1 fault suite                                       |
| M2        | Existing S1 and Leap adapters           | `adapters/robomaster-s1`, `adapters/leap-motion`, sanitized fixtures                                                                | Owner hardware regression and tracking-loss stop                                            |
| M3        | Blockly and student Python              | `packages/blockly-cit`, `student-sdk-py`, `student-runtime-web`, Studio editor                                                      | Blocks-to-readable-Python simulation and armed S1 flow                                      |
| M4        | LEGO                                    | `adapters/lego-pybricks`, `firmware/lego-hub-agent`                                                                                 | Built and simulated; S1/LEGO coordinated **hardware** program still outstanding             |
| M5        | Quest                                   | `apps/quest-godot`, `adapters/quest-gateway`                                                                                        | One APK on Quest 2/3 and dead-man stop evidence                                             |
| M6        | Unified projects and instructor console | Studio instructor UI, roles, assignment, replay, i18n                                                                               | Two students and an instructor in one runtime; isolation and stop-all observed in a browser |
| M7        | Agent Mesh and existing glasses         | `apps/agent-mesh-bridge` plus changes in separately reviewed Agent Mesh repository                                                  | Status in Quest/G2/Meta; wearable stop but no movement                                      |
| M8        | Advanced Python and optional EV3        | controlled worker, `adapters/mindstorms-ev3`                                                                                        | Approved CPython example through unchanged safety boundary                                  |
| M9        | Hardening and release                   | installers, operations, security/licence review, SBOM/recovery/performance                                                          | Owner hardware release checklist and public-repo readiness                                  |

## Product goals

| Goal                             | Milestone(s)                     | Planned implementation and proof                                                            |
| -------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------- |
| G-001 one environment            | M3–M6                            | Studio web app, dynamic device registry/toolbox, shared project format, end-to-end examples |
| G-002 readable blocks to Python  | M3                               | `packages/blockly-cit`, deterministic golden tests, `student-sdk-py`                        |
| G-003 Quest 2 and 3              | M5                               | One Godot/OpenXR project; Quest 2 baseline profile and Quest 3 feature detection            |
| G-004 preserve S1                | M0, M2                           | Reuse audit and owner-confirmed subprocess wrapper guarded by adapter/regression tests      |
| G-005 generalized Leap events    | M2, M5                           | Normalized `DeviceEvent` stream routed independently to fake/physical/Quest targets         |
| G-006 LEGO hubs                  | M4                               | Pybricks BLE adapter, hub agent, exact capability detection, hardware matrix                |
| G-007 multi-device orchestration | M1, M4, M6                       | Exact routing, parallel primitive, independent failures, integration tests                  |
| G-008 local-first                | M1–M6                            | Local runtime and browser execution with Agent Mesh disabled in CI/e2e tests                |
| G-009 independent safety         | M0, M1, every hardware milestone | Fail-closed foundation, separate service, fault injection, no adapter bypass                |
| G-010 open-source ownership      | M0, M9                           | Apache-2.0 original code, notices, licence gate, SBOM, public-release audit                 |
| G-011 reuse wearables/CLI        | M0, M7                           | Exact reuse audit and optional bridge to existing G2/Meta/Claude/Codex paths                |
| G-012 extensible adapters        | M0 onward                        | Shared `DeviceAdapter` contract, capability manifests, contract suite for every adapter     |

## Functional requirements traceability

### Project, registry, editor, and execution

| Requirement                     | Milestone      | Planned files / evidence                                                      |
| ------------------------------- | -------------- | ----------------------------------------------------------------------------- |
| FR-001 project lifecycle        | M3             | `packages/project-format`, Studio project store/actions, lifecycle e2e tests  |
| FR-002 versioned project format | M3             | `packages/project-format/schema`, generated types, migration fixtures         |
| FR-003 source-of-truth rules    | M3             | project reducer/migrations and blocks-vs-Python transition tests              |
| FR-004 device registry          | M1             | runtime device repository/service and fake registry tests                     |
| FR-005 device discovery         | M1, M2, M4, M5 | discovery provider interface; configured/fake first, hardware providers later |
| FR-006 device assignment        | M1, M6         | session assignment API and instructor authorization tests                     |
| FR-007 capability manifests     | M0, M1         | protocol schema now; registry and dynamic capability refresh in M1            |
| FR-008 Blockly workspace        | M3             | `apps/studio-web` and `packages/blockly-cit`; accessibility/i18n UI tests     |
| FR-009 block categories         | M3–M7          | versioned block catalogs added only with supported capabilities               |
| FR-010 dynamic device blocks    | M3, M6         | capability-driven toolbox service and hide/reject tests                       |
| FR-011 generated Python         | M3             | deterministic generator, formatter, source-map fixtures, golden output        |
| FR-012 runtime error mapping    | M3             | worker error protocol, source maps, Korean/English recovery messages          |
| FR-013 safe classroom runtime   | M3             | Pyodide Web Worker and constrained typed RPC; escape-negative tests           |
| FR-014 shared student API       | M3             | `packages/student-sdk-py`; generated and handwritten conformance tests        |
| FR-015 cancellation             | M1, M3         | session cancellation choreography and browser-close fault injection           |
| FR-016 advanced CPython         | M8             | instructor-only worker, profile/import/resource policies, security tests      |

### Sessions, commands, and events

| Requirement                   | Milestone | Planned files / evidence                                                |
| ----------------------------- | --------- | ----------------------------------------------------------------------- |
| FR-017 session model          | M1        | protocol/domain models and runtime session repository                   |
| FR-018 session states         | M1        | explicit state machine with transition/property tests                   |
| FR-019 exact device routing   | M0, M1    | command schema requires `deviceId`; router rejects aliases/fallbacks    |
| FR-020 device leases          | M0, M1    | foundation lease contract/tests now; persistent runtime ownership in M1 |
| FR-021 shared envelope        | M0        | JSON Schema source, generated TypeScript/Python models and fixtures     |
| FR-022 command intent         | M0        | schema/model proof and validation tests; execution begins M1            |
| FR-023 device event           | M0        | schema/model proof; event router begins M1                              |
| FR-024 idempotency and expiry | M0, M1    | command ledger tests now; persistence/reconnect invariants in M1        |

### RoboMaster S1 and Leap Motion

| Requirement                    | Milestone | Planned files / evidence                                                            |
| ------------------------------ | --------- | ----------------------------------------------------------------------------------- |
| FR-025 preserve S1 environment | M0, M2    | `REUSE_AUDIT`, external path config, compatibility diagnostics; no in-place upgrade |
| FR-026 process isolation       | M2        | authenticated localhost subprocess bridge and lifecycle tests                       |
| FR-027 adapter handshake       | M2        | handshake schema, version/capability/health diagnostics fixtures                    |
| FR-028 S1 capabilities         | M2        | capability manifest derived from tested owner environment; no blaster               |
| FR-029 S1 safety               | M1, M2    | safety policies, speed/gimbal bounds, watchdogs, lease exclusivity                  |
| FR-030 S1 compatibility tests  | M2        | sanitized recorded fixtures plus owner hardware checklist                           |
| FR-031 normalized Leap input   | M0, M2    | base event schema now; Leap mapping adapter and fixtures later                      |
| FR-032 supported Leap events   | M2        | normalized event catalog and contract fixtures                                      |
| FR-033 raw/derived modes       | M2, M3    | capability/profile policy, throttling, stored threshold profiles                    |
| FR-034 decouple Leap from S1   | M2        | subprocess output to event router only; architecture/import-boundary test           |
| FR-035 tracking-loss safety    | M1, M2    | watchdog policy and loss/service-crash/heartbeat fault tests                        |

### Quest

| Requirement                  | Milestone | Planned files / evidence                                          |
| ---------------------------- | --------- | ----------------------------------------------------------------- |
| FR-036 reusable XR runtime   | M5        | `apps/quest-godot` OpenXR app and reusable runtime scenes         |
| FR-037 pairing               | M5        | local pairing service, short code, scoped token/revocation tests  |
| FR-038 Quest input events    | M5        | GDScript/runtime schemas and controller/hand event tests          |
| FR-039 Quest commands        | M5        | typed scene/HUD/digital-twin command handlers                     |
| FR-040 Quest 2 baseline      | M5        | baseline feature/performance checklist on Quest 2                 |
| FR-041 Quest 3 enhancements  | M5        | capability detection and conditional enhancement tests            |
| FR-042 Quest safety controls | M1, M5    | arm/lease/dead-man/heartbeat gate and disconnect tests            |
| FR-043 Quest performance     | M5, M9    | throttling/interpolation profiles and measured performance report |
| FR-044 calibration           | M5        | versioned calibration profiles and manual workflow tests          |

### LEGO and legacy hubs

| Requirement                 | Milestone  | Planned files / evidence                                                                               |
| --------------------------- | ---------- | ------------------------------------------------------------------------------------------------------ |
| FR-045 primary LEGO hubs    | M4         | `hubs.py` model registry; `docs/COMPATIBILITY.md` LEGO table (declared, not hardware-verified)         |
| FR-046 firmware strategy    | M4         | `docs/LEGO_SETUP.md`; test asserts running a lesson downloads nothing                                  |
| FR-047 host-controlled mode | M4         | `PybricksHubAdapter` + `firmware/lego-hub-agent`; browser-verified against a simulated hub             |
| FR-048 autonomous mode      | M4         | `autonomous.py` step-list programs; instructor-gated `install_program`; golden output test             |
| FR-049 hybrid mode          | M4         | hub-side 500 ms watchdog test; host heartbeat driven by `Runtime.tick`                                 |
| FR-050 framed hub protocol  | M4         | `protocol.py` + hub codec; cross-decode test both ways; no-eval tests on both sides                    |
| FR-051 LEGO capabilities    | M4         | `capabilities_for()` derived from the hub's own port report; toolbox follows it                        |
| FR-052 BLE handling         | M4         | `HubTransport` boundary + diagnostics; **real radio (`ble.py`) unverified**                            |
| FR-053 LEGO safety          | M1, M4     | percent/duration caps, port validation, stop on disconnect, host-vs-autonomous exclusivity, hub button |
| FR-054 Robot Inventor       | M4         | same path as SPIKE Prime; capability-parity test; no hardware record yet                               |
| FR-055 EV3                  | M8         | optional adapter proof that cannot block v1 core                                                       |
| FR-056 NXT/RCX out of scope | None in v1 | documented non-goal and no adapter/toolbox entries                                                     |

### Orchestration, simulation, instructor, and safety

| Requirement                       | Milestone      | Planned files / evidence                                             |
| --------------------------------- | -------------- | -------------------------------------------------------------------- |
| FR-057 parallel actions           | M3, M6         | student SDK primitive and coordinated integration tests              |
| FR-058 device-specific failure    | M1, M6         | exact error context and configurable/default stop policy tests       |
| FR-059 event routing              | M1             | event router with fan-out and deduplication tests                    |
| FR-060 clock and ordering         | M0, M1         | timestamp/sequence schemas; monotonic receipt/order diagnostics      |
| FR-061 fake adapters              | M0             | fake S1, Leap, LEGO, and Quest plus failure/battery/sensor controls  |
| FR-062 simulation-first           | M1, M3         | default config/project preset and physical-mode opt-in tests         |
| FR-063 robot models               | M1, M5         | browser simplified models first; Godot twins later                   |
| FR-064 record/replay              | M1             | normalized recorder/replayer with physical-output prohibition tests  |
| FR-065 device overview            | M6             | instructor dashboard and live status/lease/warning cards             |
| FR-066 arming workflow            | M1, M6         | expiring arm state, instructor action, automatic disarm tests        |
| FR-067 emergency controls         | M1, M6         | safety API/service, queue clearing, adapter stop-all fault tests     |
| FR-068 roles                      | M6             | student/instructor authorization policy and negative UI/API tests    |
| FR-069 independent safety service | M1             | separately owned supervisor lifecycle and crash/disconnect tests     |
| FR-070 watchdogs                  | M1, M2, M4, M5 | injectable monotonic clock and per-control timeout fault suite       |
| FR-071 bounded commands           | M1 onward      | capability/policy/lease/arm/dead-man/confidence bounds               |
| FR-072 command priorities         | M1             | priority enum/queue and emergency preemption tests                   |
| FR-073 voice/wearable policy      | M0, M7         | fail-closed source policy; only status/pause/stop/request-arm routes |
| FR-074 AI policy                  | M0, M1, M7     | source field, no self-arm/movement policy, audit and negative tests  |

### Agent Mesh, logging, and reconnect

| Requirement                          | Milestone  | Planned files / evidence                                                |
| ------------------------------------ | ---------- | ----------------------------------------------------------------------- |
| FR-075 optional bridge               | M0, M7     | scaffold now; authenticated API implementation later; core-offline test |
| FR-076 reusable Agent Mesh features  | M0, M7     | exact reuse audit now; status/token/event/audit integration later       |
| FR-077 agent status in Studio        | M7         | bridge projection and Studio status cards                               |
| FR-078 physical status in Agent Mesh | M7         | separately reviewed Agent Mesh API/client extension                     |
| FR-079 typed command boundary        | M7         | allowlisted status/pause/stop/request routes; forbidden endpoint tests  |
| FR-080 existing G2/Meta apps         | M0, M7     | reuse audit and extension proof; no duplicate apps                      |
| FR-081 structured logs               | M1         | redacted structured logger with required context and tests              |
| FR-082 data minimization             | M1 onward  | persistence allowlist and biometric/video/audio negative tests          |
| FR-083 audit events                  | M1, M6, M7 | append-only audit model and complete action coverage tests              |
| FR-084 local retention               | M6, M9     | configurable retention, redacted exports, replay package                |
| FR-085 offline core                  | M1–M6      | CI/e2e with network/Agent Mesh disabled                                 |
| FR-086 Quest reconnect               | M5         | reauthentication/snapshot/disarmed/dead-man reset tests                 |
| FR-087 adapter reconnect             | M1, M2, M4 | capability refresh, stale queue clear, new lease/arm tests              |
| FR-088 Agent Mesh reconnect          | M7         | event replay only; expired/physical command non-replay tests            |

## UI and non-functional requirements

| Requirement group                  | Milestone(s)    | Planned evidence                                                                                 |
| ---------------------------------- | --------------- | ------------------------------------------------------------------------------------------------ |
| UI 11.1 navigation                 | M3–M6           | route/component tests for Projects, Program, Devices, XR, Simulation, Instructor, Logs, Settings |
| UI 11.2 program view               | M3, M6          | editor/run/safety/console/telemetry/error UI e2e                                                 |
| UI 11.3 device cards               | M1, M6          | typed status projection and visual/e2e tests                                                     |
| UI 11.4 unmistakable safety states | M3, M6          | semantic text/icon/color combinations and accessibility tests                                    |
| UI 11.5 Korean/English             | M3 onward       | stable identifiers, message catalogs, missing-key and locale tests                               |
| UI 11.6 actionable errors          | M0 onward       | typed error schema now; recovery suggestions and context tests per feature                       |
| NFR 12.1 licensing                 | M0, M9          | Apache-2.0, notices, allowlisted licence gate, SBOM, final review                                |
| NFR 12.2 supported systems         | Every milestone | Windows/Ubuntu CI; device-specific compatibility evidence at hardware milestones                 |
| NFR 12.3 performance               | M1, M5, M9      | benchmarks and measured target report without mechanical guarantees                              |
| NFR 12.4 reliability               | M1 onward       | bounded queues, reconnect, dedupe, supervision, recovery fault tests                             |
| NFR 12.5 security                  | M0 onward       | local/private bind, schema validation, scoped auth, expiry/replay limits, forbidden-API checks   |
| NFR 12.6 privacy                   | M1 onward       | collection defaults, indicators, export/delete, no implicit AI telemetry                         |
| NFR 12.7 maintainability           | M0 onward       | generated types, adapter contracts, sanitized fixtures, ADRs, compatibility matrix               |

## Acceptance-criteria traceability

| AC                                    | Milestone                       | Required evidence before acceptance                                        |
| ------------------------------------- | ------------------------------- | -------------------------------------------------------------------------- |
| 1 Apache-2.0 licensable               | M0, M9                          | licence and dependency/source audit                                        |
| 2 Windows/Ubuntu build/test           | M0 onward                       | green CI matrix at each milestone                                          |
| 3 complete reuse audit                | M0, update M7                   | exact module/path/licence/evidence entries                                 |
| 4 S1 environment preserved            | M0, M2                          | no in-place changes; diagnostics name exact executable                     |
| 5 Leap to S1 through adapters         | M2                              | regression plus hardware record                                            |
| 6 Leap to Quest object                | M5                              | fake then hardware integration test                                        |
| 7 tracking loss stops motion          | M2                              | fault injection and measured owner test                                    |
| 8 readable generated Python           | M3                              | reviewed golden fixtures                                                   |
| 9 same public API                     | M3                              | blocks/handwritten conformance suite                                       |
| 10 block project simulates S1         | M3                              | browser/runtime e2e                                                        |
| 11 blocks control armed S1            | M3                              | hardware checklist after instructor arm                                    |
| 12 blocks control LEGO                | M4                              | Blocks reach a simulated hub in a browser; **hardware record outstanding** |
| 13 one program coordinates S1/LEGO    | M4                              | Exact-routing integration test passes; **hardware test outstanding**       |
| 14 unsupported blocks hidden/rejected | M3, M6                          | dynamic toolbox/API tests; observed in a browser at M4                     |
| 15 Quest 2 runtime                    | M5                              | signed test record                                                         |
| 16 same runtime on Quest 3            | M5                              | same artifact hash/package record                                          |
| 17 Quest S1/LEGO telemetry            | M5                              | integration/hardware capture                                               |
| 18 Quest controls assigned robot      | M5                              | armed exact-device hardware test                                           |
| 19 dead-man release stops             | M5                              | measured fault test                                                        |
| 20 Quest disconnect stops             | M5                              | Wi-Fi-loss fault test                                                      |
| 21 no safety bypass                   | Every milestone                 | architecture/import/API negative tests and review                          |
| 22 no expired replay                  | M0, M1, hardware milestones     | ledger/reconnect/fault tests                                               |
| 23 exclusive physical lease           | M0, M1                          | concurrency and persistence tests; revoke path added at M6                 |
| 24 instructor stop-all                | M1, M6                          | adapter failure-injection suite; instructor-only and observed at M6        |
| 25 no default S1 blaster              | M2, M3                          | capability/toolbox/API search and tests                                    |
| 26 works without Agent Mesh           | M1 onward                       | offline CI/e2e profile                                                     |
| 27 Agent Mesh status display          | M7                              | bridge/UI integration test                                                 |
| 28 extend G2/Meta                     | M0, M7                          | reuse audit and changes in existing app repository                         |
| 29 wearable stop, no movement         | M0, M7                          | allowlist and movement-denial tests                                        |
| 30 no credentials                     | M0 onward                       | secret scan, redaction tests, sanitized fixtures/bundles                   |
| 31 licences documented                | M0 onward                       | notice/SBOM/licence gate                                                   |
| 32 tested hardware versions           | M2, M4, M5, M9                  | `docs/COMPATIBILITY.md` records                                            |
| 33 complete README/setup docs         | M9                              | documentation checklist; interim README remains honest                     |
| 34 all safety faults pass             | M1 then each hardware milestone | complete fault matrix, not a narrow unit suite                             |
| 35 examples include output/safety     | M3–M9                           | example manifest/documentation tests                                       |

## Milestone 0 file plan

| Deliverable                         | Files                                                                                                                                   |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Product and architecture records    | `docs/PRD.md`, `REUSE_AUDIT.md`, `IMPLEMENTATION_PLAN.md`, `DECISIONS.md`, `ARCHITECTURE.md`, `PROTOCOL.md`, `SAFETY.md`, `SECURITY.md` |
| Protocol SSOT                       | `packages/protocol-schema/schemas/*.schema.json` and sanitized fixtures                                                                 |
| Generated TypeScript proof          | `packages/protocol-ts/src/generated`, validators, Vitest tests                                                                          |
| Generated Python proof              | `packages/protocol-py/src/cit_protocol/generated.py`, Pydantic tests                                                                    |
| Adapter foundation                  | `packages/device-simulator/src/cit_device_simulator`, `packages/test-harness/src/cit_test_harness`                                      |
| Safety/lease/idempotency foundation | `packages/safety-core/src/cit_safety` with public-boundary pytest tests                                                                 |
| Web/runtime/bridge/Quest scaffolds  | `apps/studio-web`, `apps/runtime-py`, `apps/agent-mesh-bridge`, `apps/quest-godot`                                                      |
| Configuration                       | `config/schema.json`, safe examples, external-repository path selection tests                                                           |
| Open-source/CI                      | `LICENSE`, `THIRD_PARTY_NOTICES.md`, licence checker, Windows/Ubuntu workflow, SBOM scripts                                             |
| Compatibility and setup truth       | `README.md`, `docs/COMPATIBILITY.md`, `.gitignore`                                                                                      |

## Milestone 0 verification gates

A clean clone must run the documented equivalents of:

```text
pnpm install --frozen-lockfile
uv sync --frozen --all-packages
pnpm generate:check
pnpm schema:check
pnpm format:check
pnpm lint
pnpm typecheck
pnpm build
pnpm test
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build --package cit-protocol
uv build --package cit-runtime
pnpm license:check
pnpm sbom
```

Godot is not installed on the current Windows host. Milestone 0 therefore validates the text project/scene scaffold without claiming an APK or OpenXR runtime. Production Godot/OpenXR dependencies begin only in Milestone 5.

## Change control

- Every deviation from the PRD is appended to `docs/DECISIONS.md` before implementation.
- Requirement status is updated only from authoritative test/build/hardware evidence.
- Existing hardware repositories remain external and read-only until their milestone is approved.
- Hardware-in-the-loop evidence can never be replaced by fake-adapter success.
