# ADR-0014: Bootstrap Classroom Control with a native Windows button

- Status: accepted
- Date: 2026-08-22

## Context

The Fabric browser UI is served by the local Fabric process. It therefore
cannot provide the cold-start button for the process that must exist before the
page is reachable. Requiring tutors to type a package-manager or PowerShell
command is unsuitable for classroom operations. Adding a browser endpoint that
executes arbitrary local processes would create an unnecessary shell boundary.

## Decision

Install a current-user **CIT Classroom Control** shortcut on the Windows
Desktop and Start menu. It opens a small native WinForms launcher with one
state-aware primary button:

- **Start classroom devices** when the local host is offline;
- **Enable classroom devices** when a simulation-only Fabric requires a
  confirmed safe restart; or
- **Open Classroom Control** when the device host is ready.

The launcher invokes only the repository-owned `classroom-devices.ps1` with a
fixed mode, fixed loopback port, fixed state root, and the physical-adapter flag
on cold start. It contains no command text box, shell expression, device
address, URL, or credential input. Startup enables adapter registration but
does not arm a session, move a robot, fly a drone, switch an outlet, start an
agent session, or connect an unverified candidate. The existing one-use console
ticket performs browser sign-in.

The installer writes only two current-user shortcuts and supports exact-path
removal. The browser service gains no process-spawning endpoint.

## Consequences

- Tutor startup is a visible button workflow with no terminal interaction.
- The native button resolves the cold-start dependency without weakening the
  Fabric's independent authentication boundary.
- Source-checkout installation still has a one-time maintainer command; a
  packaged installer should invoke it automatically.
- Linux and managed multi-host deployments will need an equivalent
  service-manager-native launcher rather than this Windows-specific UI.
