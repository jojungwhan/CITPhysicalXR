# Licensing and Provenance

Repository-owned Milestone 0 source is licensed under Apache-2.0. Every npm and Python workspace manifest declares the same licence.

`pnpm license:check` performs three checks:

1. Required root licence/notice files and workspace declarations exist.
2. Installed npm licence groups are within the explicit SPDX allowlist.
3. Registry packages in `uv.lock` have installed metadata that normalizes to an allowlisted licence.

`pnpm sbom` generates a deterministic CycloneDX 1.6 inventory from `pnpm-lock.yaml` and `uv.lock`. The report is a build artifact and is not a substitute for notices or source-provenance review.

The audited Agent CLI Mesh and RoboMaster repositories are external and owner-private-unlicensed at their inspected revisions. Their code is not included. A future change may reuse source only after recording the exact source, revision, licence, modification state, dependencies, tests, protocol compatibility, decision, and risk in `REUSE_AUDIT.md` and `THIRD_PARTY_NOTICES.md`.
