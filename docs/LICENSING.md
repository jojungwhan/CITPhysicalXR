# Licensing and Provenance

Repository-owned Milestone 0 source is licensed under Apache-2.0. Every npm and Python workspace manifest declares the same licence.

`pnpm license:check` performs three checks:

1. Required root licence/notice files and workspace declarations exist.
2. Installed npm licence groups are within the explicit SPDX allowlist.
3. Registry packages in `uv.lock` have installed metadata that normalizes to an allowlisted licence.

### Optional extras are outside what the gate sees

The gate reads `uv.lock` and skips any package that is not installed, so an optional extra is invisible until someone installs it. That is a real gap, and Milestone 4 measured it rather than leaving it implicit: `adapters/lego-pybricks`'s `hardware` extra installs `asyncssh` (`EPL-2.0 OR GPL-2.0-or-later`) and `mpy-cross` builds with no licence metadata; those remain outside the allowlist. The LEGO decision in ADR-023 of `docs/DECISIONS.md` remains open.

`pnpm sbom` generates a deterministic CycloneDX 1.6 inventory from `pnpm-lock.yaml` and `uv.lock`. The report is a build artifact and is not a substitute for notices or source-provenance review.

The default JavaScript graph pins Open Home Foundation `matter-server` 1.4.0
and its matter.js controller packages for the local Matter boundary. These are
Apache-2.0/MIT-family dependencies recorded in `pnpm-lock.yaml`. The Windows
Bluetooth stack includes explicitly allowlisted native install scripts for the
pinned serial/USB and `@stoprocent` modules; the business installer builds them
locally without a proprietary smart-plug SDK.

The audited Brain2Devices, Agent CLI Mesh, and RoboMaster repositories are
external and have no top-level owner licence at their inspected revisions.
Their code is not included in CIT. Brain2Devices and RoboMaster are invoked only
through exact-pinned external-process boundaries authorized for this setup. Any
source copying, packaging, or broader distribution still requires recording the
exact source, revision, licence, modification state, dependencies, tests,
protocol compatibility, decision, and risk in `REUSE_AUDIT.md` and
`THIRD_PARTY_NOTICES.md`.
