# Sphero BOLT adapter

Independent out-of-process BOLT integration for the CIT Interaction Fabric.
It discovers exact `SB-XXXX` BLE advertisements, exposes an opaque candidate
ID to the UI, and connects to only the tutor-selected robot.

The adapter provides:

- semantic sensor summaries at at most 10 Hz;
- bounded two-dimensional travel vectors, mapped to BOLT heading;
- a 750 ms adapter-local deadman stop;
- stop, RGB matrix/front/back colour, and explicit aim reset commands;
- command idempotency and Fabric lifecycle results;
- validation of BOLT command response status before reporting success;
- a radio-free simulator.

It does not pair through Windows Settings, expose raw BLE addresses, offer raw
motor power, select the nearest robot, or depend on a Sphero account/cloud.
The optional `spherov2` protocol dependency is isolated here and pinned by both
package version and source revision. Real BOLT hardware-in-the-loop validation
is still required for each supported firmware version.

The adapter deliberately bypasses `SpheroEduAPI.set_main_led()` for BOLT. In
`spherov2` 0.12.1 on Python 3.13 its capability probe rejects a method that is
present, so the high-level call returns without writing a packet. CIT invokes
the BOLT matrix and front/back LED commands explicitly at this vendor boundary.
