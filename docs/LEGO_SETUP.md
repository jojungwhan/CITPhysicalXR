# Setting up a LEGO hub

Status date: 2026-08-16 · Milestone 4

This is the instructor procedure for putting a LEGO SPIKE Prime, SPIKE
Essential, or MINDSTORMS Robot Inventor hub under CIT Physical XR. Nothing in
the software does any of it for you: FR-046 requires firmware installation to be
explicit, instructor-controlled, documented, and reversible, so there is no
automatic-flash code path anywhere in this repository, and a class starting is
never a reason a hub's firmware changes.

**No step below has been performed against hardware by the people who wrote
this.** The machine this milestone was built on has no Bluetooth adapter at all.
Treat this file as a bring-up checklist to be corrected on first contact with a
real hub, not as a procedure that has been walked once.

## 0. Before anything: read the hub revision

Recent SPIKE Prime and Robot Inventor hubs use the **STM32H5** microcontroller
instead of the original STM32F4. Pybricks builds firmware for them separately,
and at the time of writing the STM32H5 build is the **Pybricks 4.1 beta**.

Check which hub you have before installing anything. An H5 hub given the older
build refuses it; that is not a brick, but it is a confusing half hour if nobody
looked first.

## 1. Install Pybricks firmware (instructor, once per hub)

1. Open <https://code.pybricks.com> in Chrome or Edge (Web Bluetooth is
   required; Firefox and Safari will not work).
2. Follow its firmware installation flow for your exact hub and revision.
3. **This replaces the LEGO firmware.** It is reversible: the same tool, or the
   official LEGO SPIKE / MINDSTORMS app, restores the original firmware and the
   hub returns to its shipped behaviour.
4. Rename the hub while you are there. Every hub advertises the same default
   name, and the class configuration binds by name, so give each one the name it
   will carry in the configuration (`cit-hub-1`, `cit-hub-2`, …).
5. Do **not** pair the hub in Windows Bluetooth Settings. Pybricks/CIT connects
   directly to its advertised name. If it is already paired in Windows, remove
   that pairing before using the CIT connection flow.

Minimum versions this adapter is written against: Pybricks firmware `3.3.0`,
Pybricks BLE profile `1.2.0`. Both are declared requirements; neither has been
verified against a hub.

## 2. Install the CIT hub agent (instructor, once per hub)

The hub agent is `firmware/lego-hub-agent/hub_agent.py`. It is an ordinary
Pybricks program: it reads framed lines from `stdin`, drives motors and sensors
within bounds, and stops everything on its own if the computer goes quiet.

Install it the same way as any Pybricks program — through
<https://code.pybricks.com> — and leave it running. The runtime expects to find
it running when it connects; a hub that answers the Bluetooth connection but
never answers `HELLO` produces exactly that diagnostic.

## 3. Describe the hub to the class

Copy `config/examples/lego-classroom.example.yaml` **outside this repository**
and edit it. Two rules the schema enforces for you:

- There is no field for a Bluetooth address. Hubs are bound by advertised name,
  so nothing device-secret ends up in a file anyone might commit.
- `physicalDevicesEnabled: false` with a `devices:` section is a startup error,
  not a silent skip.

Then start the runtime with it:

```bash
uv run python -m cit_runtime --config /path/to/lego-classroom.yaml
```

Without `--config`, the runtime starts in simulation with the fake devices and
touches no hardware at all. That is still the default.

## 4. Install the Bluetooth transport on that machine

The radio is an optional dependency, so a laptop with no hub in front of it does
not have to carry a Bluetooth stack:

```bash
uv sync --extra hardware
```

> **Read `docs/LICENSING.md` before running this in a classroom.** The
> `pybricksdev` package is MIT, but its dependency tree currently pulls in
> `asyncssh` (EPL-2.0 OR GPL-2.0-or-later), `cffi` (MIT-0), and `mpy-cross`
> builds with no licence metadata at all. Those are outside the repository's
> SPDX allowlist, so `pnpm license:check` **fails on a machine where the extra
> is installed**. This is an open decision for the owner, not an oversight — see
> ADR-023.

## 5. First connection

1. Press the hub's Bluetooth button until the light pulses blue. A hub only
   advertises while it is pulsing.
2. Start the runtime with the class configuration.
3. Open <http://127.0.0.1:8791/>. The hub appears as a device card with its
   model, battery, and the ports it reported.
4. The ports the hub reports win over the ports in the configuration. If they
   disagree, something is unplugged — the configuration is what the class
   expected to find, not what is true.

## 6. Bring-up checklist (unverified assumptions)

Confirm each of these on first hardware contact and correct the file named:

| Assumption                                                                 | Where it lives                         |
| -------------------------------------------------------------------------- | -------------------------------------- |
| `pybricksdev.ble.find_device(name, timeout=…)` resolves a hub by name      | `adapters/lego-pybricks/…/ble.py`      |
| `PybricksHub.write(bytes)` reaches the running program's `stdin`           | `adapters/lego-pybricks/…/ble.py`      |
| The hub's `print()` output arrives through `PybricksHub.line_handler`      | `adapters/lego-pybricks/…/ble.py`      |
| `PybricksHub.run(path, wait=False)` compiles and installs a program        | `adapters/lego-pybricks/…/ble.py`      |
| `uselect.poll()` on `usys.stdin` reads a line without blocking the loop    | `firmware/lego-hub-agent/hub_agent.py` |
| `Motor(Port.X)` raising `OSError` is how an empty port is detected         | `firmware/lego-hub-agent/hub_agent.py` |
| `hub.battery.voltage()` scaled to a percentage is close enough to be shown | `firmware/lego-hub-agent/hub_agent.py` |
| A 500 ms watchdog is fast enough to stop a driving base safely             | `firmware/lego-hub-agent/hub_agent.py` |
| The frame rate the BLE link sustains is above the 5 Hz heartbeat           | `adapters/lego-pybricks/…/adapter.py`  |

Everything above this line is host-side and tested. Everything in this table
needs a hub.

## Autonomous mode

A downloaded program keeps running with the computer closed, so it is not
something a lesson does by accident:

- The hub must be handed to autonomous mode by an instructor
  (`take_autonomous_ownership(instructor_id=…)`).
- While it is in autonomous mode, host commands are refused rather than queued.
- Installing a program stops the motors first.
- Programs are built from a closed set of steps, never from student text.

Take the hub back with `take_host_ownership()`.

## Reverting a hub

Install the original LEGO firmware from <https://code.pybricks.com> or the
official LEGO app. The hub returns to shipped behaviour and stops answering CIT
entirely. No CIT data lives on the hub.
