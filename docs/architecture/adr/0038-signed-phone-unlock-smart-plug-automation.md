# ADR 0038: Signed local phone-unlock smart-plug automation

- Status: accepted
- Date: 2026-09-10

## Context

The owner wants selected Matter smart plugs to turn on when a dedicated Android
phone is unlocked, without leaving that phone attached to the Control Tower PC.
Android's browser/PWA cannot reliably observe a system unlock while closed, and
MAC allowlisting alone authenticates neither an event nor a phone application.
An unlock-triggered outlet command is unattended physical actuation, so a
missed, duplicated, delayed, or forged event must not become a later command.

## Decision

Use a small native Android companion solely for the unlock edge. A foreground
service observes a secure locked-to-unlocked transition and sends one event to
an exact RFC1918 Control Tower origin over the phone's active Wi-Fi transport.
It does not connect to Matter devices. The app is installed and provisioned
once over an authorized USB/ADB connection; USB is not part of normal runtime.

Provisioning creates one random phone identity and one random HMAC secret. The
secret is stored in the Android application's private preferences and in the
PC's local runtime state, is excluded from API snapshots and representations,
and is sent only in the one-time ADB launch intent. Every event signs a
domain-separated canonical payload containing device id, event UUID,
monotonically increasing sequence, and timestamp. Control Tower rejects an
unknown phone, invalid signature, repeated sequence, or timestamp outside a
two-minute window. A 15-second server cooldown bounds repeated genuine unlocks.

The phone request passes through the existing direct-link IPv4 MAC allowlist.
That gate is defense in depth; the event HMAC remains required. The trigger
endpoint accepts no browser bearer credential and the administration endpoints
remain loopback-only and require `fabric.lan_access.manage`.

The operator selects the exact Matter nodes in the existing smart-plug UI,
saves that selection separately, and explicitly enables the automation. The
server persists this selection because browser-local checkbox state is not an
authority for a background event. If any configured node is absent, not a
Matter plug, disconnected, or in another room, the whole unlock action fails
closed. Otherwise Control Tower creates or reuses an ordinary smart-plug Fabric
session, arms and starts it, and submits the existing bounded
`power.switch.set {on: true}` command at lesson-automation priority.

The Android client never queues or retries an event. A sequence is persisted
before networking, so an uncertain response cannot replay the same unlock.
Pairing and configuration both default to disabled on the server. Only one
phone may be paired; replacing it requires an explicit unpair followed by a new
one-time install, which clears only this companion application's prior state.

The companion main screen and an optional Home screen widget expose one
explicit manual toggle for the same saved node set. They use a separate HMAC
signing domain but share the phone's monotonic replay sequence. The server,
rather than the phone, reads every selected node's latest Matter health state:
all-on becomes all-off, while an all-off or mixed group becomes all-on.
Missing, unknown, offline, non-Matter, or cross-room state fails the whole
action closed. The button does not depend on unlock automation being enabled
and still routes through the ordinary bounded Fabric session and command
lifecycle.

## Consequences

- The PC and phone must be awake enough to run their services and connected to
  the same directly reachable private Wi-Fi when the unlock occurs.
- Disconnecting USB after pairing does not affect unlock automation.
- A phone on a camera's isolated Wi-Fi Direct network cannot reach Control
  Tower; that unlock is discarded rather than executed later.
- Android displays an ongoing notification while monitoring. A secure PIN,
  pattern, password, or biometric-backed lock is required.
- Reboot recovery uses Android's boot broadcast, subject to the phone vendor's
  battery/background restrictions; the companion exposes battery settings for
  the operator.
- Automated tests use simulated Fabric nodes and fake ADB only. They never
  switch a real outlet.
