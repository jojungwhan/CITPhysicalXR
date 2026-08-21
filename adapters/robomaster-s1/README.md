# RoboMaster S1 adapter boundary

The production wrapper is implemented in
[`adapters/robomaster-leap`](../robomaster-leap/README.md). RoboMaster is exposed
as its own Fabric node even though the preserved upstream repository also
contains Leap gesture code. DJI and Win32 imports remain in the external Python
3.8 worker and never enter the orchestration core.
