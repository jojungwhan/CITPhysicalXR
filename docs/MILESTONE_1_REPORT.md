# Milestone 1 Verification Report

- Status date: 2026-08-16
- Scope: Runtime core and simulation
- Host: Ubuntu (Linux 7.0.0-29-generic), CPython 3.11.15, Node 22.22.1, pnpm 10.28.2

## Outcome

The repository now has a working local runtime and a Studio console that drives it.
A lesson can be run end to end against the four fake adapters: create a session,
bind a device, validate, drive it, watch events stream back, and stop everything.

No hardware was contacted. No hardware adapter exists. Every device in this
milestone is a fake from `packages/device-simulator`.

## What was added

| Area                       | Module                   | Requirements                          |
| -------------------------- | ------------------------ | ------------------------------------- |
| Injectable clocks          | `cit_runtime.clock`      | FR-060, FR-070                        |
| Session model and states   | `cit_runtime.sessions`   | FR-017, FR-018, FR-015                |
| Device registry, discovery | `cit_runtime.registry`   | FR-004, FR-005, FR-006, FR-019        |
| Safety supervisor          | `cit_runtime.supervisor` | FR-066, FR-069, FR-070–FR-072, FR-074 |
| Command pipeline           | `cit_runtime.pipeline`   | FR-058, FR-067, FR-071, FR-087        |
| Event routing              | `cit_runtime.events`     | FR-059, FR-060                        |
| Record and replay          | `cit_runtime.recorder`   | FR-064                                |
| Audit and structured logs  | `cit_runtime.audit`      | FR-081, FR-082, FR-083                |
| Local API                  | `cit_runtime.api`        | FR-085, UI 11.3                       |
| Studio console             | `apps/studio-web`        | UI 11.3                               |

## Verification

All eleven repository gates pass:

```text
generate:check  schema:check  quest:check  secret:check  format:check
lint  typecheck  build  test  license:check  sbom
```

Tests: 165 Python, 13 TypeScript.

The runtime was started (`python -m cit_runtime`) and driven over HTTP, and the
Studio console was driven in a real browser (Chromium via Playwright): session
creation, device binding, validation, four drive directions, a deliberately
out-of-range speed, an AI-sourced movement, and stop-all. No console errors.

## Safety properties asserted by tests, not by convention

- Arming requires an instructor and a validated program, and expires on its own.
- A movement command from `agent_mesh` is refused even when armed, dead-man held,
  and confidence is 1.0. The AI can stop a device; it cannot start one.
- Movement without a dead-man control, or below the confidence floor, is refused.
- Speed, acceleration, and duration are clamped before the adapter is called, and
  a movement with no duration is given one, so an unbounded movement cannot exist.
- Each of the five FR-070 watchdogs fires at its own documented timeout.
- An expired or duplicate command is refused before safety is even consulted, so
  a reconnect cannot resurrect old motion.
- A disconnect disarms the device, clears its queue, and moves the session to
  `disconnected`.
- `Replayer` holds no registry, adapter, or pipeline reference. A test asserts its
  entire public surface, so replay has no code path to a device.
- The audit log has no update or delete method, and every context value passes an
  allowlist that redacts anything named like video, audio, biometrics, or a secret.

## Two bugs found and fixed during verification

1. **Simulation required an instructor arm.** The Milestone 0 foundation gate was
   being consulted for every command. Its arm rule is about moving hardware, so a
   simulated robot could not move without an instructor, defeating the
   simulation-first default (FR-062). The gate is now consulted only for physical
   execution; the AI-movement rule stays unconditional because it is about
   authority, not physics.

2. **A session could send exactly one command.** Every command takes a write
   lease, and `InMemoryDeviceLeaseRegistry` treated the holder re-taking its own
   lease as a conflict, so the second command failed with
   `DEVICE_LEASE_CONFLICT` against itself. Found by clicking twice in a browser,
   not by the Python suite. The registry now allows the holder to renew while
   still refusing every other session; regression tests cover both.

## Deliberate limits

- **No hardware.** The fake adapters gained a `physical` flag so the physical-only
  gates can be exercised at all. It changes only what a fake _claims_. It is not
  evidence of hardware support.
- **Loopback only.** `serve()` refuses a non-loopback bind unless explicitly
  overridden, and the CORS allowlist contains no remote origin. A Studio copy
  served from any other host resolves the API to its own origin, finds nothing,
  and reports the runtime unreachable. That is intended: a remote page must not
  be able to drive a robot on someone's desk.
- **No student programming yet.** Blockly and student Python are M3. The Studio's
  drive buttons are fixed commands, not a program.
- **The command queue is not yet the dispatch path.** `CommandQueue` implements
  FR-072 ordering and FR-067 clearing and is used by the stop paths, but
  `submit()` still dispatches directly. Wiring the queue into dispatch belongs
  with M3's program execution, where commands actually arrive faster than they
  complete.
- **The event dedupe window is memory, not a ledger.** It protects against an
  adapter retrying within a burst. Expiry and the command ledger are what stop
  stale motion.

## Running it

```bash
uv run python -m cit_runtime          # http://127.0.0.1:8791
```

The runtime serves the built Studio at `/`, so that one URL is both the console
and the API. Build the Studio first with `pnpm --filter @citxr/studio-web build`.
