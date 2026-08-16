# LEGO Pybricks adapter

LEGO SPIKE Prime, SPIKE Essential, and MINDSTORMS Robot Inventor, over Pybricks
firmware (FR-045 – FR-054). Setup and firmware installation:
[`docs/LEGO_SETUP.md`](../../docs/LEGO_SETUP.md).

**No hardware has been connected.** Everything here is tested against a hub
simulated in memory; the machine this was written on has no Bluetooth adapter.
The one module that touches a radio is `ble.py`, and it has never run.

## Shape

```text
PybricksHubAdapter          the DeviceAdapter the runtime sees
        │
        │ framed lines (protocol.py)
        ▼
HubTransport                the injectable BLE boundary (FR-052)
   ├── FakeHubTransport      an in-memory hub; every test runs on this
   └── PybricksdevTransport  the real radio; optional dependency, untested
        │
        ▼
firmware/lego-hub-agent     the program running on the hub
```

| Module            | What it owns                                                       |
| ----------------- | ------------------------------------------------------------------ |
| `protocol.py`     | The framed grammar: bounded, sequenced, closed vocabulary, no code |
| `hubs.py`         | Which hubs exist, their ports, their firmware requirement          |
| `capabilities.py` | Capabilities derived from what is actually plugged in (FR-051)     |
| `adapter.py`      | Commands to frames, clamps in hub units, ownership, keep-alive     |
| `autonomous.py`   | Pybricks programs built from a closed step list (FR-048)           |
| `discovery.py`    | Configured hubs, bound by advertised name only                     |
| `diagnostics.py`  | Failures a person can act on (FR-052, UI 11.6)                     |
| `fakes.py`        | The simulated hub, including the ways a real one fails             |
| `ble.py`          | `pybricksdev`; optional, unverified                                |
| `transport.py`    | The boundary the two transports satisfy                            |

## Safety this adapter is responsible for

Arming, expiry, leases, the speed ceiling, and priority all happen before a
command reaches here. What is enforced in this package:

- Motor power converted to hub percent and capped by the class ceiling.
- Every command bounded in time; a movement with no duration is given one.
- Port validation against what the hub reported, with the port named in the
  refusal.
- Stop on disconnect, and the hub's own 500 ms watchdog if the link goes.
- Host mode and autonomous mode are mutually exclusive (ADR-024).
- The hub button is a stop control and arrives as a safety event.

## Optional Bluetooth

```bash
uv sync --extra hardware
```

Read `docs/LICENSING.md` first — the extra's dependency tree currently fails the
repository's licence gate, and the decision is open (ADR-023).
