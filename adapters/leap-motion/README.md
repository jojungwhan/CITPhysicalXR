# Leap Motion adapter boundary

The production wrapper is implemented in
[`adapters/robomaster-leap`](../robomaster-leap/README.md). Leap is registered as
an independent input node and publishes only semantic velocity gestures. Its
worker imports no robot module, and raw Leap frames are not persisted.
