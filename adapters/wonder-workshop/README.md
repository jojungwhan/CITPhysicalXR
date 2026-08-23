# Wonder Workshop Dash and Dot adapter

This package is an independent out-of-process CIT Interaction Fabric adapter.
It discovers and connects to Wonder Workshop Dash and Dot robots over local
Bluetooth Low Energy; it uses no Wonder Workshop account or cloud service.

- Dash: sensor events, RGB lights, three fixed sound cues, bounded drive, stop,
  and bounded head pose.
- Dot: sensor events, RGB lights, and three fixed sound cues. Dot deliberately
  advertises no drive or movable-head capability.
- Simulation: included and does not require Bluetooth or hardware.

Discovery is read-only. A tutor selects exact opaque robot IDs in the web UI;
the launcher never chooses the closest anonymous robot. Dash continuous motion
is limited to 0.20 m/s and guarded by a 350 ms adapter-level deadman stop in
addition to Fabric arming and policy checks.

The minimal BLE packet subset is adapted from the Apache-2.0 sources pinned in
`config/external-sources.yaml`. See `THIRD_PARTY_NOTICES.md`.
