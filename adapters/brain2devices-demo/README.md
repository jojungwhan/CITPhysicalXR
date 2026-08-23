# Brain2Devices bounded demo adapter

This optional out-of-process plugin wraps only the characterized one-shot
MindWave-to-Tello automatic demonstration in Brain2Devices revision
`536a256ef3f4b3182a74891b5971e9124ed051b0` (v0.6.35, merged to `main`).

It is intentionally separate from `cit.mindwave-mobile2` and `cit.tello`.
Those adapters continue to own semantic biosignal publication and per-aircraft
telemetry/safe-state commands. This controller exposes no generic takeoff,
movement, shell, or low-level flight interface.

Physical arming requires an active, explicitly armed Fabric physical session,
instructor priority, three affirmative safety confirmations, at least one
selected signal, the exact `classroom-drone-monitoring` safety profile, and all
additional upstream Brain2Devices gates. Simulation completes without issuing
any physical command.
