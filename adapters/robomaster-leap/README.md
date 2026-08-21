# RoboMaster S1 and Leap Motion Fabric adapter

This package wraps the existing
[`jojungwhan/robomaster-gesture-control`](https://github.com/jojungwhan/robomaster-gesture-control)
checkout at revision `3c213c110b0cdf2912985bfcde442d67092b98f0`.
It does not copy or rewrite the upstream gesture, LeapC, DJI SDK, stock S1 app,
or command-pump implementation.

The CIT Python process registers two independent nodes:

- Leap publishes `interaction.gesture.velocity` semantic events. Raw frames do
  not enter Fabric persistence.
- RoboMaster consumes `mobility.ground.set_velocity` and
  `mobility.ground.stop`, and publishes bounded command telemetry.

The upstream code runs under its owner-selected Python 3.8 interpreter through
strict JSON-lines workers. The Leap worker never imports the robot module. The
robot worker retains upstream `CommandPump` behavior: 15 Hz rate limiting, a
200 ms stale-command stop, a 150 ms moving keepalive, and a 350 ms device
timeout. CIT repeats the 0.35 m/s and 35 deg/s bounds before a request reaches
that process.

Simulation uses the upstream `DryRunRobot` and a deterministic gesture pulse.
Physical mode is unavailable unless Fabric was explicitly started with physical
actuation enabled, the session was explicitly armed, and the hardware launcher
activated input after role assignment.

Use `pnpm hardware:robot:windows -- -Mode Preflight` and follow
[`docs/operations/robomaster-leap-hardware.md`](../../docs/operations/robomaster-leap-hardware.md).
