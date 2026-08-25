# Tello Fabric adapter

This package is an independently supervised Tello node. Physical mode reuses
the `DroneClient` implementation from the characterized local Brain2Devices
checkout at commit `536a256ef3f4b3182a74891b5971e9124ed051b0` in a separate
Python process. It imports no MindWave module.

The Tello node advertises telemetry; instructor-confirmed takeoff; discrete
20–50 cm movement; 1–90° rotation; land; and emergency stop. Physical takeoff,
movement, and rotation require an active, armed Fabric session, instructor
priority, the classroom drone safety profile, and three exact safety
confirmations. The adapter repeats the direction and numeric bounds before it
calls Brain2Devices. It exposes no continuous RC or unrestricted command path.

In simulation and Brain2Devices API compatibility modes, a separate media
worker copies only the latest bounded JPEG/PNG into Fabric's in-memory media
plane; video never enters the event database or recorder.
