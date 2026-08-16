# Safety Foundation

## Verified in Milestone 0

- Expired command intents cannot be claimed for execution.
- An idempotency key is accepted once during its active expiry window; repeats are classified as duplicates.
- Only one active write lease exists per device, and an expired lease no longer blocks a new session.
- Unarmed movement is denied.
- Agent Mesh movement initiation is denied even when an input is marked armed.
- Stop operations remain available without arming.
- Fake adapters reject wrong-device, offline, unsupported, expired, and duplicate commands.
- Fake network/process failure performs an observable stop, then requires recovery, reconnect, and reconciliation.

These primitives are process-local and non-persistent. They establish public contracts only; the independent safety service, watchdogs, dead-man signals, bounds, stop-all orchestration, persisted leases, and runtime dispatch order belong to Milestone 1 or later.

## Fail-closed rule

Unknown movement sources or missing safety prerequisites must be denied at the runtime boundary. Stops have priority. Telemetry replay may be historical, but physical movement may never be replayed after expiry or reconnect.

## Hardware status

No hardware test was run. Fake success cannot substitute for S1, Leap, LEGO, Quest, watchdog, latency, or emergency-stop verification.
