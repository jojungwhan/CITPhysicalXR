# ADR-0009: Wrap the pinned RoboMaster/Leap implementation with two workers

- Status: accepted
- Date: 2026-08-21

## Context

The working RoboMaster gesture repository combines a Python/C Leap source,
gesture state machine, DJI SDK and stock-S1 transports, a command watchdog, and
operator tooling. Its supported DJI environment is Python 3.8, while CIT uses
Python 3.11–3.13. Rewriting those working modules would discard characterized
safety behavior and introduce native dependency conflicts. Treating the whole
program as one permanent Leap-to-S1 integration would also defeat capability
substitution.

The owner selected the current upstream main revision
`3c213c110b0cdf2912985bfcde442d67092b98f0` for private, noncommercial use.

## Decision

CIT wraps the exact checkout without copying its implementation.

- A Python 3.8 Leap worker imports `LeapSource` and `GestureController` and
  emits bounded semantic velocity signals. It imports no robot module.
- A separate Python 3.8 robot worker imports the existing `DryRunRobot`,
  `DjiRobotAdapter` or `S1AppKeyboardAdapter`, and `CommandPump`. It receives
  only allowlisted JSON-lines velocity and stop requests.
- A Python 3.11+ Fabric adapter supervises both workers and registers separate
  Leap and RoboMaster nodes through the authenticated adapter WebSocket.
- Fabric owns session authorization, role resolution, arbitration, arm state,
  TTL, and physical-execution policy. The robot worker repeats device bounds,
  idempotency, stale-input stop, and safe shutdown.
- The adapter refuses any upstream revision other than the characterized pin.
- Capture remains inactive until the hardware launcher has assigned roles and
  armed and started the session.

## Consequences

Vendor SDKs do not enter the orchestration core, and either node can be replaced
independently by another capability-compatible implementation. A Python 3.8
environment and native Leap runtime remain explicit deployment prerequisites.
Physical evidence is a separate manual gate; simulation and process-contract
tests cannot satisfy it. Updating upstream requires a new pin, refreshed
fixtures, its full test suite, and this adapter's contract suite.
