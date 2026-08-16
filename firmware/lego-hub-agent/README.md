# CIT LEGO hub agent

`hub_agent.py` is the program that runs **on** a LEGO hub under Pybricks
firmware. The runtime never imports it. Installing it is an instructor's
deliberate act, once per hub: [`docs/LEGO_SETUP.md`](../../docs/LEGO_SETUP.md).

**It has never run on a hub.** The logic below is tested on CPython with a
machine object that records instead of driving
(`tests/firmware/test_hub_agent.py`), because a firmware watchdog that is only
ever checked by plugging in a robot is how a stop that does not stop ships. The
hardware half — `build_machine()` and `main()` — needs a hub and is untested.

## What it does

It reads framed lines from `stdin`, performs one bounded action per frame, and
prints framed replies to `stdout` (FR-047, FR-050):

```text
C1|<sequence>|<OPERATION>|<argument1>|<argument2>
```

Three properties matter more than the rest:

- **No evaluation.** No `eval`, no `exec`, no operation that carries code. A
  test asserts none of those strings appear in the file at all.
- **It stops itself.** If no frame arrives for 500 ms while motors are running,
  it stops them and reports `WATCHDOG` (FR-049, FR-053). Losing Bluetooth must
  not mean a robot that keeps driving.
- **It clamps again.** The runtime already bounded the command. The hub bounds
  it a second time, because the hub is the last thing between a number and a
  motor.

The centre button stops everything and reports itself, so a child can end a
lesson without the computer's cooperation.

## MicroPython constraints

No `typing`, no dataclasses, no f-string tricks, no comprehension the hub cannot
afford. Every Pybricks import happens inside `build_machine()`, which is what
lets CPython import the file for testing.

## Keeping the two halves in step

The host encoder and parser live in
`adapters/lego-pybricks/src/cit_lego_pybricks/protocol.py`. A test encodes with
each side and decodes with the other, and asserts both agree on every operation,
its argument count, and the frame bounds. Change one and the test fails.
