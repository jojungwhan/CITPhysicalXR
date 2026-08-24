# ADR 0017 — Cloud-independent Matter smart-plug boundary

- Status: Accepted; legacy-compatibility clauses superseded by ADR-0022
- Date: 2026-08-22

## Context

The TinyTuya compatibility adapter can control some Tuya-family plugs over the
LAN after a technician obtains a device ID and local key. Obtaining those values
normally depends on a vendor account or vendor provisioning workflow, and the
result is not portable to another Windows operator profile. CIT needs a new
business-site path that does not depend on Tuya or Gosund accounts, APIs, or
cloud availability.

Brand names are not protocols. An older Tuya or Gosund product cannot become a
vendor-independent device merely because CIT changes its software. A device
must expose an interoperable local protocol in its installed firmware.

## Decision

CIT's default smart-plug path uses certified Matter On/Off Plug-in Unit
endpoints (device type `0x010A`) commissioned into a CIT-owned local Matter
fabric.

- Pin Open Home Foundation `matter-server` 1.4.0 behind a loopback-only process
  boundary.
- Store the Matter fabric and Wi-Fi commissioning material under the current
  Windows operator profile, outside the repository.
- Accept a printed Matter QR/manual setup code through an authenticated CIT
  endpoint and pass it to the fixed launcher over stdin.
- Never place setup codes or Wi-Fi passwords in command-line arguments, URLs,
  Fabric events, audit details, or repository files.
- Expose canonical `power.switch.set` and `power.switch.state` capabilities.
  Advertise read-only `telemetry.power.electrical` per endpoint only when the
  device exposes the standard Matter 1.3 Electrical Power/Energy Measurement
  clusters; never fall back to a vendor API.
- Require the Matter Descriptor cluster to identify device type `0x010A`; do not
  turn arbitrary OnOff clusters into electrical outputs.
- Bind the controller only to `127.0.0.1`, disable its separate dashboard and
  OTA provider, and keep CIT as the only tutor interface.
- Keep the existing TinyTuya integration as an explicitly legacy compatibility
  path. It is not installed or configured by the business-site workflow.

The controller can use its bundled Matter trust seed and the local network; a
Tuya or Gosund service is never in commissioning or command execution. Internet
availability may allow the standards controller to refresh CSA Distributed
Compliance Ledger metadata, but that is not a vendor account or an execution
dependency.

## Consequences

- New purchases must explicitly support Matter and include a Matter setup code.
- Tapo P110M is one compatible product instance, not a separate vendor adapter;
  the same contract remains available to any conforming `0x010A` endpoint.
- Existing non-Matter Tuya/Gosund firmware still needs its legacy local-key
  adapter, a supported firmware conversion, or replacement hardware.
- Initial Wi-Fi commissioning on Windows uses Bluetooth and currently requires
  the pinned native Node module build prerequisites.
- Moving to another Windows computer normally means installing CIT there and
  recommissioning each plug. Copying DPAPI files or raw controller private-key
  storage is not a supported migration method.
- Matter multi-admin transfer is a future enhancement; it is not silently
  approximated by copying secrets.
