# ADR-0027: Authenticated versioned Windows transfer installer

Status: Accepted

Date: 2026-08-24

## Context

Tutors need to reproduce the classroom on another Windows computer and network
without checking out a developer repository or typing hardware launcher
commands. Copying the active `%LOCALAPPDATA%` directory would also copy scoped
tokens, Matter operational credentials, device history, and machine-specific
paths. Serving an installer by a public/static link would either lose local
authorization or put a bearer credential in a URL. Letting an HTTP request run
the build would create a shell and supply-chain execution boundary inside the
orchestrator.

The repository contains polyglot, native, and exact-pinned dependencies. A
genuinely offline redistributable image would require a separately licensed and
maintained cache of Microsoft, Node, Python, npm, PyPI, Git, compiler, driver,
and external-source artifacts.

## Decision

- Add a Windows transfer package builder as a release step, never as an HTTP
  request handler.
- Require a clean Git revision for ordinary bundles. A source bundle carries
  immutable release metadata so an installed copy can build the next package
  without `.git`.
- Package only explicit repository source roots and root manifests. Reject
  reparse points and exclude secrets, databases, state, caches, external
  checkouts, build output, and generated artifacts.
- Serve only a prebuilt artifact from the loopback Fabric. Validate manifest,
  path, size, and SHA-256 at startup; require `fabric.installation.read`; audit
  each download; never accept artifact paths from the browser.
- Download through an authenticated browser request and object URL so the token
  never enters a URL or history. Verify SHA-256 in the browser before saving.
- Verify the inner payload again in the bootstrap before extracting into a
  versioned `%LOCALAPPDATA%\CITPhysicalXR\app\<revision>` directory. Fail closed
  on mismatched existing metadata and use a strictly bounded temporary path.
- Export site/room as a separate non-secret JSON template. Prompt for the new
  Wi-Fi secret locally. Never transfer Matter controller state or previously
  remembered connections.
- State plainly that this is a USB-transferable, network-assisted installer.
  Pinned prerequisites still require Internet during installation; classroom
  device operation remains local-first and independent of proprietary plug
  clouds.

## Consequences

Tutors get one bilingual page, two obvious downloads, and a double-click setup
path. Installations remain attributable to an exact source revision, and each
new computer can prepare the next handoff. The runtime gains only a bounded
read/audit permission and immutable file response—not build or shell authority.

The first install on a network still needs Internet and administrator approval
for prerequisites. Hardware is not magically portable: Matter devices must be
reset/recommissioned, and each USB/BLE/Wi-Fi/Android integration keeps its own
pairing and HIL procedure. A fully offline enterprise image remains a separate
future distribution and licensing project.
