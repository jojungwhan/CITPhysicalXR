# ADR 0022 — Separate wearable profiles and Matter-only plug support

- Status: Accepted
- Date: 2026-08-23
- Supersedes: ADR-0011 and ADR-0019

## Context

Even Realities G2 and Meta Ray-Ban use different companion software and expose
different last-mile features. Presenting them as one tutor-facing integration
hides important setup and media differences. Their existing semantic agent path,
however, already has one authenticated Agent Mesh discovery, intent, completion,
and acknowledgement boundary. Running competing consumers against that feed
would create duplicate-delivery and ownership hazards.

The legacy local-key and open-firmware smart-plug slices had no physical HIL
evidence for the owner hardware and added separate credentials, discovery,
launchers, UI forms, dependencies, and protocol-specific failure modes. The
business-site direction now uses the local Matter controller and standard
On/Off Plug-in Unit capability.

## Decision

- Expose `even-realities-g2` and `meta-rayban` as separate integration catalog
  entries, setup cards, and model selectors.
- Project a stable device-specific `metadata.model` and feature profile from
  each wearable node.
- Keep `cit.agent-mesh-bridge` as the single shared out-of-process transport and
  delivery authority. This is infrastructure reuse, not a combined product
  identity.
- Keep Meta media on the independently authenticated ephemeral media companion;
  do not claim camera support through the semantic Agent Mesh capability.
- Remove the legacy proprietary-LAN and open-firmware plug adapters, Python
  packages, browser forms, runtime routes, host discovery, launchers, generated
  outputs, tests, and dependency locks.
- Keep `cit.matter-smart-plug` as the supported physical smart-plug adapter.
  Course logic continues to target the canonical `power.switch.*` capability.
- Do not automatically erase old per-user protected profile directories during
  an upgrade. They are inert after the launchers and routes are removed and can
  be deleted by an administrator under the applicable retention policy.

## Consequences

- Tutors see the two glasses products independently and receive setup guidance
  that matches the selected hardware.
- The working glasses-to-agent path retains one cursor, acknowledgement, and
  process supervisor, avoiding a risky rewrite or competing consumers.
- The runtime no longer accepts local keys, proprietary relay credentials, or
  brand-specific LAN discovery requests.
- Smart-plug deployments require Matter-certified hardware with a printed
  setup code and must pass the existing electrical safety and HIL gates.
- Historical ADRs remain as decision records but no longer describe deployable
  code.
