# Licensing and Provenance

Repository-owned Milestone 0 source is licensed under Apache-2.0. Every npm and Python workspace manifest declares the same licence.

`pnpm license:check` performs three checks:

1. Required root licence/notice files and workspace declarations exist.
2. Installed npm licence groups are within the explicit SPDX allowlist.
3. Registry packages in `uv.lock` have installed metadata that normalizes to an allowlisted licence.

### Optional extras are outside what the gate sees

The gate reads `uv.lock` and skips any package that is not installed, so an optional extra is invisible until someone installs it. That is a real gap, and Milestone 4 measured it rather than leaving it implicit: `adapters/lego-pybricks`'s `hardware` extra installs `asyncssh` (`EPL-2.0 OR GPL-2.0-or-later`), `cffi` (`MIT-0`), and `mpy-cross` builds with no licence metadata, none of which are allowlisted. `pnpm license:check` passes here and fails on a machine with the extra installed. ADR-023 in `docs/DECISIONS.md` holds the decision; it is open.

`pnpm sbom` generates a deterministic CycloneDX 1.6 inventory from `pnpm-lock.yaml` and `uv.lock`. The report is a build artifact and is not a substitute for notices or source-provenance review.

The Tuya-compatible adapter pins TinyTuya 1.20.0 (`MIT`) in the explicit
`smart-plug-lan` hardware extra. TinyTuya remains isolated inside the adapter;
the orchestration core imports neither it nor any vendor SDK. Like the LEGO
hardware extra, installing it introduces `cffi` (`MIT-0`) outside the default
allowlist, so ordinary CI and simulation leave it uninstalled while the lock and
SBOM retain the resolved provenance.

The audited Agent CLI Mesh and RoboMaster repositories are external and owner-private-unlicensed at their inspected revisions. Their code is not included. A future change may reuse source only after recording the exact source, revision, licence, modification state, dependencies, tests, protocol compatibility, decision, and risk in `REUSE_AUDIT.md` and `THIRD_PARTY_NOTICES.md`.
