# Milestone 4 Verification Report

- Status date: 2026-08-16
- Scope: LEGO SPIKE and MINDSTORMS, over Pybricks
- Host: Ubuntu (Linux 7.0.0-29-generic), CPython 3.11.15, Node 22.22.1, pnpm 10.28.2

## Outcome

A student drags a LEGO block, reads the Python it generates, presses Run, and the
command leaves the runtime as one bounded frame addressed to a hub.

That path was exercised in a real browser. The evidence is the runtime's audit
log and the frame the hub received:

```text
GENERATED PYTHON
    await spike_prime.motor.run(port="A", speed=0.3, durationSeconds=1)

AUDIT   command.accepted | device=lego-spike-01 | cap=motor.run | src=student_blocks | completed
HUB     MOTOR_RUN|A|30|1000
```

**No LEGO hub was connected.** The device in that run is the real
`PybricksHubAdapter` talking to a hub simulated in memory. This machine has no
Bluetooth adapter at all (`/sys/class/bluetooth/` is empty), so nothing here is
hardware evidence, and the one module that would touch a radio has never
executed.

## What was added

| Area                             | Module                                 | Requirements           |
| -------------------------------- | -------------------------------------- | ---------------------- |
| Framed hub protocol              | `cit_lego_pybricks.protocol`           | FR-050                 |
| Hub models and firmware needs    | `cit_lego_pybricks.hubs`               | FR-045, FR-046, FR-054 |
| Capability discovery             | `cit_lego_pybricks.capabilities`       | FR-051                 |
| Host-controlled adapter          | `cit_lego_pybricks.adapter`            | FR-047, FR-053, FR-087 |
| Autonomous programs              | `cit_lego_pybricks.autonomous`         | FR-048                 |
| Injectable Bluetooth boundary    | `cit_lego_pybricks.transport`, `ble`   | FR-052                 |
| Actionable Bluetooth errors      | `cit_lego_pybricks.diagnostics`        | FR-052, UI 11.6        |
| Simulated hub, including faults  | `cit_lego_pybricks.fakes`              | FR-061                 |
| Hub agent                        | `firmware/lego-hub-agent/hub_agent.py` | FR-047, FR-049, FR-050 |
| Named hub binding, config        | `cit_runtime.physical_devices`         | FR-005, FR-052         |
| LEGO blocks and generated Python | `packages/blockly-cit`                 | FR-009, FR-010, FR-011 |

## Verification

All eleven gates pass. Tests: 313 Python, 78 TypeScript (was 204 and 75).

Browser run (Chromium via Playwright) against the real runtime, with the LEGO
device served by `PybricksHubAdapter` over an in-memory hub:

- The toolbox gains a LEGO category with five blocks when the hub is bound.
- Unplugging the motor on port A leaves one motor, and the toolbox loses the
  drive blocks and the Devices category on its own. That is FR-051 feeding
  FR-010 observed, not unit-tested.
- Run produces `MOTOR_RUN|A|30|1000` at the hub: 0.3 became 30 percent, 1 second
  became 1000 ms.

Live HTTP checks against the same running runtime, on a physical session:

```text
unarmed            DEVICE_NOT_ARMED      Physical movement requires an armed safety context
armed 0.9 / 9 s    completed             clamped [speed, durationSeconds] -> MOTOR_RUN|A|50|2000
agent_mesh         SAFETY_POLICY_DENIED  Agent Mesh may propose but may not initiate movement
no dead-man        SAFETY_POLICY_DENIED  Physical movement requires an active dead-man control
empty port         rejected              Port D has no motor in it (the hub reports empty)
sensor.distance    completed             sensor.distance {'value': 320}
instructor stop    stopped               STOP_ALL|end of lesson, motors false
```

The heartbeat is visible in the same trace: `Runtime.tick` sends
`HEARTBEAT|200` five times a second for as long as the hub is connected.

## The parts that are enforced rather than described

**The protocol cannot carry code.** `Operation` is a closed enum with a declared
argument count each; the alphabet excludes `|` and newline so an argument cannot
smuggle a frame; a frame is 96 characters. Tests assert no operation named
`EVAL`, `EXEC`, `RUN_PYTHON`, `IMPORT`, `COMPILE`, or `SHELL` exists, and that
none of `eval(`, `exec(`, `__import__(`, `compile(` appears in the hub agent
source or in a generated autonomous program.

**The two codecs cannot drift.** The host encoder is Python with dataclasses; the
hub's is MicroPython-safe. A test encodes with each and decodes with the other,
and asserts both agree on every operation, its arity, and the frame bounds.

**The hub stops itself.** With motors running and no frame for 500 ms, the agent
stops them and reports `WATCHDOG` — tested on CPython with a machine object that
records instead of driving. The centre button stops everything too, and arrives
at the runtime as a safety event rather than a sensor reading.

**Capabilities are what is plugged in.** Two motors produce drive capabilities;
one motor does not. No distance sensor, no `sensor.distance`. The hub's own port
report on connect overrides what the configuration guessed, and a reconnect
re-reads it (FR-087).

**A hub cannot be owned twice.** Autonomous mode requires an instructor id; while
it holds, host commands are refused rather than queued; installing a program
stops the motors first. A test asserts that running a lesson downloads nothing.

**No Bluetooth address can be committed.** The configuration schema has no field
for one. Hubs are bound by advertised name.

## Bugs found by running it, not by unit tests

1. **A reply batch was thrown away after the first match.** A hub answers
   `SENSOR_READ` with an `ACK` and then the reading, both in one notification.
   The adapter returned at the `ACK` and dropped the rest of the batch, so the
   student's sensor value silently never arrived. The batch is now processed to
   the end.

2. **A device refusal reached the student as silence.** The runtime only
   surfaced `code`/`message` when _it_ refused a command. When the runtime
   allowed it and the _device_ refused — a port with nothing plugged into it —
   the student bridge returned `accepted: true, status: rejected` and the
   program carried on. Now the reason travels, mapped to line 9 and block
   `cit_motor_run`: "Port A has no motor in it (the hub reports empty). Plug the
   motor in, then reconnect the hub." This is the M3 lesson again, one layer
   further down.

3. **The M3 LEGO block was unusable in practice.** `cit_motor_speed` sent
   `speed=200` in degrees per second, and the safety supervisor clamps `speed`
   to the policy ceiling of `0.5` — a quarter of one degree per second. Speed is
   now a fraction on every device and the adapter converts (ADR-022).

4. **One dead hub took the classroom with it.** `connect_all` let a failed
   connection propagate, so a flat hub stopped every other device from coming
   up. A failure is now recorded on the device and the room starts.

## What Milestone 4 does not include

- **No hardware. AC-12 and AC-13 are not met.** Both need a hub. Everything here
  is a simulated peer, and the LEGO rows in `docs/COMPATIBILITY.md` are declared
  requirements, not measurements.
- **`ble.py` has never run.** Four vendor-API assumptions are listed in
  `docs/LEGO_SETUP.md`; if any is wrong, only that file changes.
- **The licence gate does not cover the hardware extra, and the extra fails it.**
  Installing `--extra hardware` brings `asyncssh` (EPL-2.0 OR GPL-2.0-or-later),
  `cffi` (MIT-0), and `mpy-cross` builds with no licence metadata.
  `pnpm license:check` passes here only because none of them is installed. This is
  ADR-023 and it is **open**: it blocks hardware bring-up and needs an owner
  decision, not a widened allowlist.
- **Autonomous mode has no block path.** `build_program` takes a step list, and
  nothing yet turns a Blockly workspace into one. The download is instructor-only
  and manual.
- **Sensor subscriptions are hub-side only.** The agent honours
  `SENSOR_SUBSCRIBE` and reports on its interval; the adapter never sends one,
  so a lesson polls.
- **Drive-base geometry is a default, not a measurement.** 56 mm wheels and a
  114 mm axle track are the standard SPIKE build; a different robot drives the
  wrong distance until this becomes per-device configuration.
- **The simulated hub is a protocol peer, not physics.** It never stops a motor
  when a duration elapses, because nothing above it should depend on that.
