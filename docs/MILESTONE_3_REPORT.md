# Milestone 3 Verification Report

- Status date: 2026-08-16
- Scope: Blockly and student Python
- Host: Ubuntu (Linux 7.0.0-29-generic), CPython 3.11.15, Node 22.22.1, pnpm 10.28.2

## Outcome

A student can drag a block, read the Python it generates, press Run, and watch
the command travel through the safety supervisor to a device.

That whole path was exercised in a real browser. The proof is the runtime's own
audit log, which recorded the block's command arriving from the sandbox:

```text
command.accepted | device=fake-s1-main | cap=drive.velocity | src=student_blocks | completed
```

No hardware was contacted. The device is a fake, as in M1.

## What was added

| Area                      | Package                        | Requirements           |
| ------------------------- | ------------------------------ | ---------------------- |
| Versioned project file    | `packages/project-format`      | FR-001, FR-002, FR-003 |
| Block catalog and toolbox | `packages/blockly-cit`         | FR-008, FR-009, FR-010 |
| Blocks to Python          | `packages/blockly-cit`         | FR-011, FR-012         |
| Student Python API        | `packages/student-sdk-py`      | FR-014, FR-015, FR-057 |
| Browser sandbox           | `packages/student-runtime-web` | FR-013, FR-012         |
| Runtime RPC gate          | `cit_runtime.student_bridge`   | FR-013, FR-019, FR-068 |
| Studio program view       | `apps/studio-web`              | UI 11.2, UI 11.5       |

## Verification

All eleven gates pass. Tests: 204 Python, 75 TypeScript.

Browser run (Chromium via Playwright), against the real runtime:

- Blockly workspace injects; toolbox shows six device-free categories.
- Binding the S1 adds `Devices` and `RoboMaster` to the toolbox and nothing else.
  Unbinding removes them. That is FR-010 observed, not just unit-tested.
- Generated Python updates live as blocks change.
- Run boots Pyodide from vendored assets, executes the program, prints to the
  Studio console, and lands one command in the audit log.

## How the sandbox is actually constrained (FR-013)

Two gates, and neither is a promise in a comment:

1. **The SDK bridge** has a five-name allowlist (`command`, `read_sensor`,
   `log`, `sleep`, `device_info`). A test asserts the set exactly and asserts no
   module in `citxr` comes from `os`, `subprocess`, `socket`, or `shutil`.
2. **The worker host** re-checks the method name before forwarding. A test sends
   `read_file` and asserts the runtime is never called.

Past those, the ordinary M1 pipeline still applies: a student command is
clamped, leased, and refused exactly as any other. Tests assert a student
program cannot arm a device, cannot raise its own speed ceiling, and cannot
claim to be an instructor.

Pyodide's runtime files are copied into the bundle at build time. The Studio
never contacts a CDN, so a classroom on a locked-down network still works
(FR-085).

## Decisions worth knowing

- **Loose blocks join `main()`.** A block dropped on the canvas alone would
  otherwise emit `await` at module level, which is a SyntaxError. Wrapping it in
  a second function nobody calls would be worse: it would look like it ran.
- **The attribute chain is the capability.** `s1.drive.velocity(...)` sends
  capability `drive.velocity`, action `set`, because that is what a manifest
  advertises (FR-007). Sending `drive` as the capability is what the protocol
  schema rejects, and it did.
- **No `pythonToBlocks`.** The PRD forbids claiming arbitrary Python converts
  back, so the module offers no function that would have to lie. A test asserts
  no such export exists.
- **`jsdom` was dropped rather than widening the licence allowlist.** Adding
  Blockly pulled in `jsdom` as an auto-installed optional peer, which brought
  `MIT-0` and `CC0-1.0` transitive licences. Nothing here uses a DOM test
  environment, so `auto-install-peers=false` removes them and the allowlist is
  unchanged.

## Bugs found by running it, not by unit tests

1. **`AttributeError: get`** — the worker returned a JavaScript object to Python;
   the bridge needs a real mapping. Now converted via `to_py()`.
2. **Stale closure wiped device bindings.** Blockly's change listener is
   registered once and captured `regenerate` from the first render, when nothing
   was bound. Every block edit then regenerated with no devices and silently
   dropped the `device(...)` lines. Now called through a ref.
3. **Empty function body.** A block that only produced a warning emitted no
   lines, so `emitBody` wrote a header with nothing under it -- an
   `IndentationError` at run time. It now counts emitted lines, not blocks.
4. **Devices were never released.** A session held its devices until the runtime
   restarted, so the second lesson of the day found every robot taken. Ending a
   session now releases and disarms, and the Studio ends the previous session
   when a new one starts.
5. **A malformed capability returned HTTP 500.** Student code is untrusted
   input; it now comes back as a readable refusal.

## What M3 does not include

- **Variables, functions, lists, and math blocks.** The catalog declares those
  categories (FR-009) but ships no blocks in them, so the toolbox does not show
  them. Events, control, loops, time, text, parallel, and the device families
  are implemented.
- **Keyboard navigation and block search.** FR-008 lists them; Blockly provides
  zoom, undo/redo, copy/paste, comments, and drag out of the box, and the
  remaining accessibility work is not done.
- **Korean UI strings are wired but unexercised.** Block labels and Blockly's own
  catalog both switch on the locale, and the Studio currently passes `en`. No
  Korean review has happened.
- **Project persistence.** Projects are created, edited, exported, and imported
  in memory. Nothing writes them to disk yet.
- **AC-11 (blocks control an armed S1) is not met.** It requires hardware.
