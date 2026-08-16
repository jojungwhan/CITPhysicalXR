# Milestone 0 Verification Report

- Status date: 2026-08-16
- Scope: Discovery, Reuse Audit, and Foundation only

## Outcome

The repository installs from its committed locks and passes the complete foundation gate sequence on the Windows discovery host and in a clean Ubuntu 24.04 container. No hardware connection, external-repository edit, production adapter, local runtime API, or Milestone 1 orchestration was performed.

## Delivered areas

- Complete PRD copy, requirement/milestone traceability, reuse audit, and 21 initial ADRs
- Apache-2.0 licence, third-party notices, installed-dependency licence gate, and CycloneDX generator
- Draft 2020-12 protocol v1 schema, four shared fixtures, and deterministic TypeScript/Python generation
- Command idempotency/expiry, exclusive write leases, source/arming denial, and stop allowance
- `DeviceAdapter` protocol, reusable shape harness, and in-memory S1/Leap/LEGO/Quest fakes
- Strict configuration schema, packaged runtime copy, safe defaults, discovered Windows paths, and platform-selection tests
- Buildable React Studio status scaffold, non-transport Agent Mesh policy scaffold, Python configuration package, and static Godot scaffold
- Exact-commit Windows/Ubuntu CI matrix, secret scan, format/lint/type/build/test gates, and Python package builds
- Deferred adapter/package/firmware directories containing scope notices rather than placeholder implementations

## Test results

| Environment                                           | TypeScript | Python | Result    |
| ----------------------------------------------------- | ---------: | -----: | --------- |
| Windows, Node 22.17.0 / CPython 3.13.0                |          4 |     66 | 70 passed |
| Ubuntu 24.04 container, Node 22.17.0 / CPython 3.13.0 |          4 |     66 | 70 passed |

Python coverage includes 52 fake-adapter cases plus protocol, config/path, ledger/expiry, lease, and safety-denial tests. Counts are test cases, not hardware scenarios.

## Commands verified

```text
pnpm install --frozen-lockfile
uv sync --all-packages --frozen
pnpm generate:check
pnpm schema:check
pnpm quest:check
pnpm secret:check
pnpm format:check
pnpm lint
pnpm typecheck
pnpm build
pnpm test
pnpm license:check
pnpm sbom
uv build --package cit-protocol
uv build --package cit-safety-core
uv build --package cit-device-simulator
uv build --package cit-test-harness
uv build --package cit-runtime
```

Windows licence evidence: 5 npm workspace manifests, 185 installed npm packages in 8 licence groups, 6 Python workspace manifests, and 58 installed Python registry packages. Ubuntu evidence: 184 npm packages, 57 installed Python registry packages, and one correctly skipped Windows-conditional lock entry. The current lock inventory produces 322 CycloneDX components.

## Reuse candidates found

The detailed evidence and decisions are in `REUSE_AUDIT.md`. Principal candidates are:

- Agent Mesh envelope/session/event structures, scoped identity/token approach, secret storage/redaction, config loader, persistence/audit, observability, wearable API, G2 client, Android/Meta bridge, and reconnect/replay logic
- Existing RoboMaster SDK interpreter and external S1/Leap behavior as a future subprocess-wrapping target
- Ultraleap native bridge structure and the Even Hub SDK dependency where their independent licences permit use

No original source from an owner-private-unlicensed checkout was copied.

## Unresolved paths and evidence

- Linux paths for Agent Mesh, RoboMaster gesture control, the classroom checkout, and the DJI interpreter
- Owner-designated integrated S1/Leap checkout if different from the audited repositories
- Built Leap bridge DLL, LeapC DLL, and installed/running Ultraleap service/runtime
- Hardware IDs, firmware versions, network/BLE details, Quest developer setup, and Godot/OpenXR versions
- Owner licence designation for the three audited owner repositories

## Architectural decisions

The foundation keeps the physical authority PC-local, Agent Mesh optional, safety below every caller, adapter contracts in Python, JSON Schema as the wire source, device identity exact, configuration external/non-secret, and fake devices explicitly non-physical. Existing S1/Leap behavior will be wrapped rather than rewritten after owner path confirmation and recorded tests.

## Deviations

None. Cross-platform generation required two implementation corrections during verification—LF normalization for generated Python and semantic comparison for source/packaged config schemas. Both preserve the PRD architecture and are now covered by the clean Ubuntu gate.

## Remaining work

All product/runtime behavior remains milestone-gated. Milestone 1 may begin only after owner review and includes the local API, registries, session state machine, persistent/runtime lease integration, safety service, event router, validator pipeline, full fake-device simulation, stop-all, and replay. Hardware, production Quest/LEGO, Blockly/Pyodide, instructor UI, and Agent Mesh transport remain in their later milestones.
