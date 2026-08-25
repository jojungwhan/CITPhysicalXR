# CIT Sphero Ollie adapter

Independent out-of-process BLE adapter for exact `2B-XXXX` Sphero Ollie
advertisements. Discovery is read-only. Physical commands are canonical,
bounded, idempotent, and protected by a 750 ms local deadman stop.

The adapter exposes directional roll, stop, aim reset, main LED color, semantic
sensor state, a simulator, and contract tests. Raw motor commands are not
exposed. Physical hardware validation remains required before increasing the
conservative classroom speed-value ceiling.
