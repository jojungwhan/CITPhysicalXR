# ADR 0037: Bounded, separately confirmed 3D-printer jobs

- Status: accepted
- Date: 2026-09-08

## Context

The classroom control center needs to prepare models for the Creality printer
at `172.30.1.55`. A print may already be running when the control center starts,
and printer model, nozzle, filament, build plate, orientation, supports, and
slicing profile all affect whether a job is safe. Creality Print documents an
offline slicing command, but not a stable command-line contract for upload and
print start. Some Creality/Klipper installations expose documented Moonraker
HTTP endpoints; this installation has not yet been verified to do so.

Starting a print is materially different from ordinary Fabric device fan-out.
It can heat equipment and continue for hours, and an ambiguous network result
must not be retried automatically.

## Decision

The printer is a dedicated fabrication boundary, not a selectable Fabric node.
It is excluded from lesson, demonstration, **Select all**, wearable, and retry
fan-out. The workflow has four independent transitions:

1. stage one bounded STL or 3MF file on the control-center PC;
2. slice locally with the installed Creality Print CLI and one explicit,
   installed K1 Max printer/process/filament profile;
3. download the resulting G-code for manual handoff, or upload it without
   starting; and
4. start only that exact uploaded artifact after a fresh standby check and a
   short-lived, actor-bound, one-use confirmation.

The persistent runtime starts with a current-print lock. While locked, status
polling does not open a printer connection and slicing, upload, and start are
disabled. Local source staging remains available. After the existing job ends,
an instructor must physically inspect the printer and use a read-only standby
verification before the in-memory lock can be released. A restart restores the
lock.

Remote monitoring and writes are disabled by default. They may be enabled only
for an explicitly configured Moonraker port on the exact IPv4 address, and
remote writes additionally require physical-actuation mode. Upload always sends
Moonraker's `print=false` field. Start is a separate request. Every remote
transition performs a fresh state read and accepts only `standby`. A start
request is never retried; a transport failure after submission is reported as
an unknown outcome that requires physical/status inspection.

Generated G-code is bounded and checked for the expected Creality/Klipper start
macro, blocked emergency/restart commands, and profile temperature limits. Each
artifact is identified by a SHA-256 digest. Printer actions use existing Fabric
authentication and audit storage. No printer credential is sent to the browser.

The proprietary Creality TCP service is not reverse engineered. If a documented
Moonraker endpoint is unavailable, the supported delivery path is to download
the reviewed G-code and import/send it manually with Creality Print.

## Consequences

- Opening or refreshing the locked control-center panel cannot disturb the
  current print.
- An STL cannot become an unattended print through one click or a group action.
- Upload success does not imply print start, and the UI states that explicitly.
- Enabling live control requires an operator to verify the printer generation,
  installed profile, documented transport, and idle state after the current job.
- Staged sources and prepared G-code metadata are runtime-local; restarting the
  runtime deliberately restores the safety lock and clears the active list.
- Automated tests use fake transports only. Live acceptance remains a separate
  owner-supervised task after the printer is idle.
