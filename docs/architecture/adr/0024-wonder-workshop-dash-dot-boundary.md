# ADR-0024 — Independent exact-selection Dash and Dot BLE boundary

Status: accepted, 2026-08-23.

## Context

Wonder Workshop's official public APIs describe Dash and Dot commands and
sensors, but the official Python implementation is an alpha Python 2.7/macOS
path and does not provide the required current Windows host boundary. A working
cross-platform Bleak reference exists under an Apache-2.0 notice, but taking it
as an unpinned runtime dependency would also inherit behavior that catches
write failures and selects nearby robots too broadly for a classroom.

Dash and Dot also have different capabilities. Dot has sensors, lights, and
sound but no wheel drive or movable head. Treating both as a generic moving
robot would make the course and safety contracts untruthful.

## Decision

- Implement `cit.wonder-workshop` as an independent out-of-process adapter;
  neither the Fabric core nor Studio imports Bleak or robot protocol code.
- Keep Bleak in the adapter's optional `hardware` extra and include a fake
  transport for CI and course simulation.
- Adapt only the required packet and sensor subset from the exact Apache-2.0
  source pin recorded in `config/external-sources.yaml`.
- Discovery is read-only and returns a one-way hash of model plus BLE address.
  A tutor selects an exact advertised name; connection rescans and resolves
  that exact opaque ID. The nearest anonymous robot is never selected.
- Register one process, credential, node, and role per robot. Dot omits drive
  and head capabilities; Dash includes them.
- Bound Dash to 0.20 m/s linear motion, no strafe, and the canonical angular
  limit. A 350 ms adapter deadman writes stop independently of the Fabric.
- Publish semantic sensor state at no more than the UI path needs. Do not
  publish or persist microphone amplitude; only a semantic clap flag may leave
  the adapter.

## Consequences

The integration can be installed and moved between Windows classrooms without
a Wonder Workshop account or cloud dependency. Tutor setup and control stays
inside the single bilingual Fabric page. Firmware variations and the fixed
on-device sound bank still require physical hardware-in-the-loop evidence; the
UI and documentation must not present software tests as physical validation.
