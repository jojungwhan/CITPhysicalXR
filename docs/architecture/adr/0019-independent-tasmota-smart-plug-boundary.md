# ADR 0019 — Independent Tasmota smart-plug boundary

- Status: Superseded by ADR-0022
- Date: 2026-08-22

## Context

CIT has Gosund WP3 outlets that do not advertise Matter. Stock Gosund/Smart
Life firmware remains a Tuya-family integration and does not satisfy the
business-site requirement for operation without a vendor account or service.
Some WP3 revisions can run Tasmota, but the product name alone does not prove
the internal chip, board layout, or safe conversion method.

The existing `cit.tuya-smart-plug` adapter is deliberately coupled only to the
Tuya LAN protocol and an exact device ID/local key. Adding Tasmota commands to
that adapter would mix firmware-specific configuration, authentication, error
semantics, and lifecycle risks.

## Decision

Create `cit.tasmota-smart-plug` as an independent out-of-process adapter.

- It uses Tasmota's local HTTP command boundary and has no vendor-cloud client.
- It accepts an exact private IPv4 address, one relay number, and optional
  Tasmota web credentials.
- Only `Power<x>` query, explicit off, and explicit on are implemented. No
  arbitrary Tasmota command, backlog, template, firmware, or shell operation is
  exposed.
- It publishes and consumes the same canonical `power.switch.state` and
  `power.switch.set` capabilities as Matter and Tuya adapters.
- It repeats boolean validation, idempotency, state verification, safe-off on
  connection/shutdown, and health reporting at the adapter boundary.
- The authenticated tutor UI sends the bounded profile to one fixed runtime
  route. Secrets pass to one fixed launcher over stdin, are protected with
  current-user Windows DPAPI, and never enter Fabric events, command arguments,
  discovery output, or audit details.
- Discovery and connection never flash a plug. A WP3 must already run a
  correctly configured Tasmota build before CIT attempts its read-only probe.
- An instructor-only discovery action checks at most 512 private LAN addresses
  using only `Power1` state queries and Tasmota WebUI markers. It also detects
  visible `tasmota_*` setup networks. Returned addresses are untrusted hints;
  only the adapter's exact read-only handshake creates a node.

The Tuya MT1000 remains on the independent `cit.tuya-smart-plug` path when an
exact local key is available. Matter remains the recommended path for new
hardware.

## Consequences

- Tuya, Tasmota, and Matter failures remain isolated and independently
  deployable.
- A course can substitute any of them through the canonical boolean capability.
- The same UI can configure either known legacy family without offering an
  unrestricted device command interface.
- Tutors do not need to inspect the router or manually enter a DHCP address for
  an already converted Tasmota plug.
- Tasmota's legacy HTTP command API does not provide transport encryption. The
  adapter is therefore limited to private IPv4 addresses and must run only on a
  trusted, isolated classroom IoT network with a unique web password. Tasmota's
  device-side authentication travels in its required query string; CIT does not
  log or persist that URL.
- CIT cannot make a stock WP3 or MT1000 cloud-independent through software
  configuration alone. Hardware/firmware conversion remains a separately
  reviewed, revision-specific operation.
- Real-device acceptance still requires no-load or approved-load HIL evidence
  for on, off, duplicate delivery, network loss, adapter exit, and restart.
