# ADR-0012: Use launcher-assisted, one-use tutor access

- Status: accepted
- Date: 2026-08-21

## Context

ADR-0005 correctly requires independent scoped CIT authentication, but asking a
classroom tutor to retrieve and paste the Fabric administrator credential
exposes unnecessary authority and makes startup look like infrastructure
administration. Reloading also needs to remain a sign-out boundary, so durable
browser storage is not appropriate.

## Decision

The local Windows launcher authenticates with the DPAPI-protected administrator
bootstrap and requests a one-use console ticket. The ticket:

- contains at least 256 bits of randomness;
- expires after 90 seconds and is consumed atomically once;
- is placed in the URL fragment, never in an HTTP request or server log;
- is removed from browser history before classroom data is requested; and
- redeems only for a 12-hour instructor identity limited to classroom session,
  device, safety, command, and audit-view permissions.

The browser holds the redeemed bearer only in memory. Reload and sign-out clear
it. The administrator bootstrap is never sent to the page. Manual access-code
entry and clipboard copy remain a recovery path, not the normal tutor workflow.
The ticket store is process-local, matching the local single-worker runtime.

## Consequences

Tutors normally use the installed **CIT Classroom Control** Windows button and
arrive signed in. They do not type the launcher command. Capturing an unused
link provides only a short redemption window; capturing a redeemed link
provides no authority. Restarting the runtime invalidates outstanding tickets.
A future multi-worker or remote deployment requires a shared atomic ticket
store or a separately reviewed signed-exchange design.
