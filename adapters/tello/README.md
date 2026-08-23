# Tello Fabric adapter

This package is an independently supervised Tello node. Physical mode reuses
the `DroneClient` implementation from the characterized local Brain2Devices
checkout at commit `536a256ef3f4b3182a74891b5971e9124ed051b0` in a separate
Python process. It imports no MindWave module.

The Tello node deliberately advertises only telemetry, land, and emergency
stop. Takeoff and movement are not part of this adapter. In simulation and
Brain2Devices API compatibility modes, a separate media worker copies only the
latest bounded JPEG/PNG into Fabric's in-memory media plane; video never enters
the event database or recorder.
