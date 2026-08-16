# CIT Physical XR Studio

This repository is at **Milestone 0: Discovery, Reuse Audit, and Foundation**. It contains versioned protocol models, validation/configuration contracts, fail-closed safety primitives, four in-memory adapter fakes, buildable application scaffolds, and cross-platform CI. It does not yet provide a local runtime API, student programming environment, browser simulator, production Quest application, or physical-device control.

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

The Studio scaffold can be built with `pnpm --filter @citxr/studio-web build`. It displays foundation status only and has no runtime connection.

## Configuration

`config/default.yaml` is safe, local-only, and keeps physical devices and Agent Mesh disabled. `config/examples/local-foundation.example.yaml` records the Windows checkout paths found during the audit. Copy an example to a location outside the repository before making machine-specific changes; `config/local.yaml`, `config/*.local.yaml`, and environment files are ignored.

Platform paths are stored separately and never translated between Windows and Linux syntax. Missing platform entries fail with an actionable error. Configuration accepts secret-store metadata, not literal credentials.

## Foundation layout

- `packages/protocol-schema`, `protocol-ts`, and `protocol-py`: protocol v1 source and generated bindings
- `packages/safety-core`: command ledger, expiry, leases, and foundation denial policy
- `packages/device-simulator`: non-hardware adapter contract and fake S1, Leap, LEGO, and Quest devices
- `packages/test-harness`: reusable adapter shape assertion
- `apps/runtime-py`: validated configuration helpers only
- `apps/studio-web`: buildable React status scaffold only
- `apps/agent-mesh-bridge`: optional bridge policy only; no transport
- `apps/quest-godot`: text-only Godot scene scaffold; no OpenXR or export setup
- `docs/REUSE_AUDIT.md`: exact external checkout evidence and reuse decisions

## Current limitations

- No hardware was contacted or modified.
- No network listener, local runtime API, arbitrary shell, subprocess bridge, or public endpoint exists.
- Fake-device tests are contract evidence only; they are not Milestone 1 simulation or hardware evidence.
- The working DJI Python environment was found, but the expected built Leap bridge DLL, Leap runtime/service, and owner-designated integrated checkout were not found.
- Linux paths for the audited external repositories remain unresolved.
- Godot is not installed on the discovery host, so only static project structure is checked. No APK or Quest/OpenXR behavior is claimed.
- Agent CLI Mesh and the audited RoboMaster repositories have no owner licence at their inspected top level; none of their original code is copied here.
- A clean Ubuntu 24.04 Docker verification passes on this host. The GitHub Actions matrix is defined but cannot report an external run until the repository is pushed.

See `docs/IMPLEMENTATION_PLAN.md` for requirement traceability and `docs/DECISIONS.md` for architecture decisions. The repository is licensed under Apache-2.0; dependency and external-source status is in `THIRD_PARTY_NOTICES.md` and `docs/LICENSING.md`.
