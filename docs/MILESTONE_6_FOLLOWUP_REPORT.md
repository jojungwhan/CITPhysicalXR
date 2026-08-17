# Milestone 6 Follow-up Verification Report

- Status date: 2026-08-17
- Scope: the three loose ends listed in `MILESTONE_6_REPORT.md` under "What Milestone 6 does not include" — project autosave, real file downloads for the exports, and the command queue in the dispatch path
- Host: Ubuntu (Linux 7.0.0-29-generic), CPython 3.11.15, Node 22.22.1, pnpm 10.28.2

## Outcome

A student's work reaches the disk without anybody pressing anything. An export
leaves the browser as a file. And the queue that has implemented FR-072 and
FR-067 since Milestone 1 is now the path every command takes, so a stop can
overtake a command that is waiting and clearing a queue clears commands that
were really in one.

Still no hardware. Every device below is a fake.

## What was not enforced before

**The queue was a structure beside the runtime, not in it.** `CommandQueue`
ordered by priority and cleared by device, and `submit()` handed every command
straight to an adapter. A queued instructor stop could not overtake a queued
student command because nothing was ever queued, and `clear-queue` cleared an
empty structure while the commands it was meant to stop were already gone to a
robot. This is the same shape as the two rules Milestone 6 found (ADR-027,
ADR-028): a requirement with tests, enforced against nobody.

Every command now enters the queue and each device drains its own lane in
priority order (ADR-029). The caller still awaits its own outcome; what changed
is what may run first while it waits.

**Opening a project did not open it.** The Projects list could open a stored
project, and the editor went on showing the previous program; the workspace's
next change event then wrote its own blocks over the ones just loaded. With a
Save button that was a bug a student could see and undo. With autosave it would
have been silent and automatic, so it is fixed here (ADR-030): opening loads the
stored blocks into the workspace, and the translation back into Blockly's format
is tested in `packages/blockly-cit`.

Evidence that the old behaviour was real, from this repository's own run: a
project created empty, opened, and saved came back with the editor's starter
program — `hello from my program` — in its `blocksState`.

## What was added

| Area                                           | Module                                   | Requirements     |
| ---------------------------------------------- | ---------------------------------------- | ---------------- |
| Queue in the dispatch path, per-device lanes   | `pipeline.CommandPipeline._drain`        | FR-072, FR-057   |
| Discarded commands answered and audited        | `pipeline.CommandPipeline._discard`      | FR-067, UI 11.6  |
| Autosave engine (debounce, in-flight, failure) | `autosave.Autosave`                      | FR-001, NFR 12.4 |
| Autosave wiring and save-state label           | `ProgramView`                            | FR-001, UI 11.6  |
| Stored blocks back into a workspace            | `blockly-cit/serialize`, `loadWorkspace` | FR-001, FR-003   |
| Exports saved as files                         | `download.ts`, Logs, Simulation, Program | FR-084           |
| Korean for the new labels                      | `i18n`                                   | UI 11.5          |

## Verification

All eleven gates pass. Tests: 381 Python (was 375), 122 TypeScript (was 102).

Browser run against the real runtime, two contexts:

```text
autosave        after opening a stored project    Unsaved changes
                a moment later                    Saved.
                on disk without pressing Save     true

downloads       citxr-project-project-1-20260817-1109.json    578 bytes
                citxr-audit-20260817-1109.jsonl               8 lines
                citxr-replay-rec-704a657faef8-...json         3182 bytes
                replay package physicalOutput                 false

dispatch        drive outcome                     Accepted · completed
                queue depth at rest               0
```

Opening a project seeded on disk, in a browser:

```text
from citxr import device, log, sleep


async def main():
    await log("loaded from disk")
    await sleep(2)

shows the stored program              true
starter blocks gone                   true
on disk still the stored program      true
on disk not overwritten by the editor true
```

Korean interface, same page: `아직 런타임에 저장하지 않았습니다. 한 번 저장하면
그다음부터는 알아서 저장합니다.`

The Python suite proves what a browser cannot show: that a stop submitted last
runs first (`gate.order == ["set", "halt", "set"]`), that one device's slow
command does not hold up another's, that clearing a queue answers the student
whose command it dropped rather than leaving them waiting, that a disconnect
does the same, and that a full queue is refused rather than growing.

## The parts that are enforced rather than described

- **A cleared queue is a refusal.** Every discarded command is answered with a
  `SAFETY_POLICY_DENIED` naming the reason and is recorded as denied. A test
  asserts the awaited call returns, because the failure this replaces is a page
  that waits forever.
- **Emergency paths never queue.** `stop_device`, `stop_all`, and the watchdogs
  do not wait for a lane, because a stop that waits for the command it is meant
  to interrupt is not a stop.
- **The lane cannot be duplicated.** A lane is reference-counted before its lock
  is awaited, so it cannot be dropped and recreated while somebody is queued
  behind it — two lanes for one device would be two commands on one robot.
- **Autosave does not lose the edit made during a save.** A change that arrives
  while a write is in flight is written after it, and a failed save keeps its
  document rather than dropping it.
- **A shared project id is never autosaved.** The Studio's page-load project has
  a constant id, so autosaving it would have every tab in the room writing one
  file. Autosave starts once the runtime has the project.
- **The block round-trip is exact or it fails loudly.** A test asserts every
  catalog block has at most one value input and at most one statement input,
  which is what makes routing a stored child back to its socket exact.

## Bugs found by running it, not by unit tests

- **Opening a project overwrote it.** Found by reading a downloaded project file
  and seeing the starter program in it. Described above.
- **A project saved itself because it had been opened.** The first dirty check
  compared the whole document, and opening restamps `updatedAt`, so every open
  wrote the file again and rotated its backup for nothing. The comparison now
  ignores `updatedAt`.
- **The save-state label was unreachable in a browser.** The first run read the
  safety banner instead: both are `role="status"`. The label now carries a class
  of its own, which is also how a person's assistive technology tells them
  apart.

## What this does not include

- **No hardware, and no XR.** Unchanged. AC-15 to AC-20 remain Milestone 5, and
  ADR-023 is now decided (option 3) but not implemented, so LEGO bring-up is
  still ahead.
- **A project is not autosaved before its first save.** By design (ADR-030), and
  the Studio says so in both languages rather than leaving a student to guess.
- **A failed autosave does not retry on a timer.** The next edit, or leaving the
  Program view, tries again. A runtime that has gone away would otherwise be
  asked every second and a half for the rest of the lesson.
- **Blocks chained at the top level are still dropped.** `readWorkspace` records
  the head of each top-level chain and its inputs; a statement connected after a
  top-level block is neither a top block nor an input child, so it is not stored
  and not generated. That predates this work and is unchanged by it.
- **No conflict detection between two editors.** Two tabs open on one project
  overwrite each other, last write wins. Ownership is recorded; concurrency is
  not.
- **The Korean has still not been read by a Korean-speaking instructor.**
