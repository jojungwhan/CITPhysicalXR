# ADR-0032: Keep Sphero Ollie independent from the BOLT adapter

Status: Accepted

Date: 2026-08-25

## Context

Sphero BOLT and Ollie share a reverse-engineered protocol library and the same
canonical classroom concepts: directional roll, stop, aim reset, LED output,
and semantic sensor state. They are not interchangeable vendor transports.
Ollie advertises as `2B-XXXX`, uses the legacy Sphero protocol, has no BOLT LED
matrix, and has materially different speed behavior.

Making the BOLT adapter accept Ollie would mix discovery identity, device
constraints, telemetry claims, hardware evidence, logs, remembered profiles,
and failure recovery. It would also make a BOLT regression capable of changing
Ollie behavior and vice versa.

## Decision

Implement `cit.sphero-ollie` as an independent out-of-process plugin with its
own package, exact opaque candidate namespace, process, state directory,
credential, manifest, policy, simulator, tests, API route, and catalog entry.

The integrations may share only stable outer mechanisms: the Fabric SDK,
canonical capabilities, the pinned optional `spherov2` library, the Windows
process-supervision launcher, and reusable React presentation. Neither adapter
imports the other.

Ollie exposes no raw motor command. Before physical calibration it maps a
0.10 m/s semantic classroom bound to a conservative raw speed-value ceiling of
20 and stops locally after 750 ms without a renewed approved command. Discovery
accepts only exact `2B-XXXX` advertisements and never exposes a BLE address.

## Consequences

- BOLT and Ollie can be installed, discovered, connected, restarted, tested,
  and removed independently.
- The common dashboard can render both through capability-based controls.
- BOLT-only matrix behavior is not falsely advertised for Ollie.
- Some small adapter-boundary code remains intentionally duplicated. A shared
  vendor-family package should be extracted only if a third stable integration
  proves the semantics are genuinely common.
- Ollie remains marked physical-HIL pending until the checklist in the Windows
  operations guide is completed on the classroom hardware.
