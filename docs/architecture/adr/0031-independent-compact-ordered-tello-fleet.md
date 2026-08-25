# 0031 — Independent compact ordered Tello fleet control

Status: Accepted — 2026-08-25

## Context

The fleet adapter already launched aircraft serially, but the tutor panel was
resolved from the currently selected lesson. Connecting Tellos could therefore
register every aircraft while leaving the fleet controls hidden. The stop
command also sent one multi-aircraft landing request, which did not provide the
requested or observable one-at-a-time landing order. Repeated technical details
and expanded manual controls made the connected-device cards unnecessarily tall.

## Decision

Resolve the `cit.brain2devices-fleet` controller through its own adapter-owned
monitoring session, independently of the lesson picker, and poll that session's
semantic events separately. Render its controls inside the Tello discovery card
beside the independent per-aircraft adapter controls. The Windows connect action
continues to connect every Tello reported by the allowlisted Brain2Devices local
radio endpoint and now starts the bounded sequence controller for one to eight
connected aircraft.

Keep the explicit physical-flight attestation unchecked. Provide one tutor
button that internally prepares the session, submits the one-shot ordered arm,
and consumes it immediately; retain a separate prepare button for an approved
ring, MindWave-derived, Leap, or glasses trigger. Technical capability lists and
per-aircraft directional controls use collapsed disclosures, while connection,
live-value summaries, takeoff, normal landing, and emergency stop remain visible.
The three discovery tiers are disclosures: the connected tier opens by default
when hardware is live, otherwise the available tier opens. Candidate paths and
setup tips remain one-click disclosures. A single grounded-aircraft attestation
feeds remembered reconnect, connect-all, and the repeatable Tello fleet action,
so the same safety fact is not requested three times.

The Tello connect-all action remains visible when one aircraft is already
connected. An instructor can power another aircraft or attach another Wi-Fi
route, scan, and reconcile every available Tello without disconnecting the
first or changing the selected lesson.

Ordered takeoff remains confirm-before-advance. Normal fleet stop now sends a
landing command to exactly one aircraft, waits for that aircraft to report
landed, and then advances in the configured order. A failed landing is recorded,
but does not prevent landing attempts for the remaining selected aircraft.
Emergency stop remains a separate per-aircraft and global safety path.

## Consequences

- Reloading the console or selecting another lesson no longer hides connected
  fleet controls.
- Tutors can connect all locally reachable Tellos, take off one at a time, and
  land one at a time from the same compact device card.
- A single Tello can exercise the same controller and UI before a multi-aircraft
  classroom test.
- Physical flight still requires one local network route per stock access-point
  mode Tello and an explicit tutor safety confirmation.
- Landing may take longer because each confirmation is bounded and serialized;
  the global emergency-stop path remains immediately available.
