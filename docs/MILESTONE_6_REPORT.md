# Milestone 6 Verification Report

- Status date: 2026-08-16
- Scope: unified projects, roles, and the instructor console
- Host: Ubuntu (Linux 7.0.0-29-generic), CPython 3.11.15, Node 22.22.1, pnpm 10.28.2

## Outcome

Two students and an instructor share one runtime. Each student sees their own
robot and the free ones, and cannot see, command, or stop the other's. The
instructor sees the whole room, arms a device, and stops everything.

That was exercised in two real browser contexts against the built Studio:

```text
student-one sees:  Fake Leap Motion, Fake Quest Client, Fake RoboMaster S1
student-two sees:  Fake Leap Motion, Fake LEGO Hub,     Fake Quest Client
instructor sees:   Fake Leap Motion, Fake LEGO Hub,     Fake Quest Client, Fake RoboMaster S1

student-one sees student-two's hub? false
student-two sees student-one's S1? false
an unauthenticated fetch from the page context: 401
```

Still no hardware. Every device above is a fake, and the physical-mode evidence
below runs against fakes whose `physical` flag only changes what they _claim_
(M1 report). Nothing here is hardware verification.

## The two things that were not enforced before

Reading the Milestone 1 API before writing any Milestone 6 code turned up two
rules that existed on paper and were enforced against nobody.

**A caller declared its own authority.** `POST /api/commands` took `source` from
the request body, so a student's page could send `source: "instructor"` and be
ranked as an instructor. `POST /api/safety/arm` took `instructor_id` from the
body, so any caller could name themselves the instructor who armed a robot.
FR-068 is a list of things a student cannot do, and none of it was enforceable
while identity was self-declared. Identity is now a token the runtime issued
(ADR-027), and a student sending `source: "instructor"` gets a 403.

**A caller declared its own dead-man.** `deadmanActive` was a boolean in the
request body that the student's own page filled in, and the Studio filled it
with `true` unconditionally. The supervisor now derives it from a heartbeat
(ADR-028): holding the control in the Studio starts that heartbeat and releasing
it stops it, so letting go and losing the browser are the same event.

## What was added

| Area                                     | Module                               | Requirements            |
| ---------------------------------------- | ------------------------------------ | ----------------------- |
| Roles, scoped tokens, authorization      | `cit_runtime.roles`                  | FR-068, NFR 12.5        |
| Attested dead-man control                | `supervisor.deadman_attested`        | FR-068, FR-070          |
| Observed device status                   | `cit_runtime.status`                 | FR-065, UI 11.3         |
| Projects on disk                         | `cit_runtime.projects`               | FR-001, FR-002, 12.4    |
| Retention, replay packages               | `cit_runtime.retention`              | FR-064, FR-084, 12.6    |
| Lease revoke, queue clear, inputs        | `pipeline`, `supervisor`, `runtime`  | FR-067                  |
| Per-session failure policy               | `sessions.FailurePolicy`, `pipeline` | FR-058                  |
| Per-principal event scoping              | `api.EventBroadcaster`               | FR-068, 12.6            |
| Studio navigation and sign-in            | `App`, `SignIn`, `routes`            | UI 11.1                 |
| Safety banner                            | `SafetyBanner`                       | UI 11.4                 |
| Instructor console                       | `views/InstructorView`               | FR-065, FR-067          |
| Projects, Simulation, Logs, XR, Settings | `views/*`                            | UI 11.1, FR-064, FR-084 |
| Korean and English interface             | `i18n`                               | UI 11.5                 |
| Held dead-man control                    | `useDeadman`, `ProgramView`          | FR-068, ADR-028         |

## Verification

All eleven gates pass. Tests: 375 Python, 102 TypeScript (was 313 and 78).

Browser run, two students and an instructor, against the real runtime:

- The Studio is gated: before signing in there is no navigation, and an
  unauthenticated `fetch` from the page's own context returns 401.
- A student runs a lesson, and the instructor console shows the S1 held by
  `student-one` with its lease, its last command, and its age.
- A student opening the Instructor tab is told it is for instructors. The
  runtime returns 403 for every instructor route regardless.
- Switching the interface to Korean relabels the navigation, the safety banner,
  and the XR panel.
- The instructor's stop-all reaches all four devices and lands in the log.

Physical-mode run, against fakes declaring themselves physical:

```text
before arming            Refused · DEVICE_NOT_ARMED
armed, control not held  Refused · SAFETY_POLICY_DENIED
                         "No dead-man heartbeat has arrived for this device
                          within the last 300 ms"
armed, control held      Accepted · completed
control released         safety.watchdog_fired  quest_deadman_heartbeat
                         action=disarm elapsedSeconds=0.3848
                         Refused · DEVICE_NOT_ARMED
```

The last two lines are the property worth having: releasing the control does not
merely block the next command, it disarms the device, so recovering requires an
instructor again.

## The parts that are enforced rather than described

- **Authorization is not an HTTP concern.** `roles.authorize` names every
  privileged action and answers; `api.py` only maps the refusal to a 403. A test
  iterates the whole `Action` enum and asserts a student is refused each one, so
  an action added later is instructor-only or it fails the suite.
- **A student's socket carries their own devices.** The filter is asked per
  event rather than fixed at connect time, so binding a device mid-lesson starts
  delivering it and losing one stops.
- **Replay holds nothing it could dispatch to.** A test asserts `Replayer` has no
  registry, pipeline, adapter, or runtime attribute, and that the adapter emits
  nothing during a replay.
- **A project write is atomic.** Temporary file in the same directory, fsynced,
  renamed over the target, with the previous version kept as `.bak.json`.
- **Retention runs on write, not on a timer.** A timer that only runs while the
  runtime is up would keep a term of recordings on a machine switched off at four
  o'clock.
- **Ownership is a sidecar.** The project schema is the Studio's and closed to
  additional properties, so the owner lives in `<id>.owner.json` rather than
  being smuggled into a permissive corner of the student's document.

## Bugs found by running it, not by unit tests

- **Replay delivered nothing.** The router's dedupe window still held the
  original event ids, so every replayed event was dropped as a retry of itself.
  Dedupe now skips historical events, which is the case it was never meant to
  cover: it exists to stop an adapter's retry causing a second physical action,
  and a historical event causes none.
- **The audit named the mechanism, not the person.** The Logs view showed
  `student_blocks` as the actor for every command, which tells an instructor that
  a block moved a robot and not whose block it was. The actor is now the
  session's owner; the source is recorded one field along.
- **The device list went stale on navigation.** The first two-student run
  appeared to show a student seeing another's hub. The runtime was right and the
  page was old: it refetched only on sign-in. It now refetches on every view
  change, which is also how somebody stops binding a robot that is no longer
  free.
- **An instructor's ordinary command outranked the runtime's safety stop.**
  `classify_priority` mapped the `instructor` source to `INSTRUCTOR_STOP_ALL`,
  so an instructor driving a robot was ranked above the stop that exists to
  interrupt it. FR-072 ranks the instructor's _stop-all_ second, not everything
  they send. This only became reachable in Milestone 6, when instructors gained
  the ability to issue commands at all.
- **The arming workflow had no user interface.** FR-066 steps 1 to 5 were
  reachable only through the API: the Studio could start simulation sessions
  only, and had no arm action. Both are now in the Program view, instructor-only.

## What Milestone 6 does not include

- **No hardware, and no XR.** The XR tab says so rather than simulating a
  headset. AC-15 to AC-20 remain Milestone 5.
- **The passcode is weak on purpose, and the runtime says so.** It defends
  against the other browser tab on the same machine, not against a network; the
  runtime still refuses every non-loopback bind. There is no password store,
  because a classroom runtime cannot keep that promise (ADR-027).
- **Tokens are in memory only.** Reloading the page signs you out. A shared
  classroom machine is the reason: a token in local storage would outlive the
  lesson and the person.
- **Projects do not autosave.** Saving is a button. The store is built for
  autosave -- atomic writes and a retained previous version -- but nothing calls
  it on a timer yet. _(Closed 2026-08-17; see `MILESTONE_6_FOLLOWUP_REPORT.md`
  and ADR-030. Turning it on exposed a bug of this milestone's: opening a
  project did not load its blocks, so the editor overwrote what was opened.)_
- **The export shows a byte count rather than downloading a file.** The audit and
  replay-package routes return their documents; the Studio reports the size and
  does not yet hand the browser a file. _(Closed 2026-08-17; ADR-031.)_
- **The command queue is still not the dispatch path.** Unchanged from Milestone
  1: `CommandQueue` implements FR-072 ordering and FR-067 clearing, and
  `submit()` still dispatches directly. _(Closed 2026-08-17; ADR-029.)_
- **Roles are two.** Student and instructor. There is no administrator, and no
  per-class membership: anyone who can reach the loopback port can join as a
  student.
- **The Korean has not been read by a Korean-speaking instructor.** It was
  written as Korean rather than translated, and the safety vocabulary was
  chosen to remove an ambiguity found during review -- `해제됨` for ARMED reads
  equally as "released" and could have presented the dangerous state as the safe
  one, so the armed and disarmed states are now `작동 허용` and `작동 잠김`. That
  is a review, not a native reader's verdict.
- **ADR-023 is still open**, and still blocks LEGO hardware bring-up. _(Decided
  2026-08-17: option 3, the transport split. Not implemented.)_
