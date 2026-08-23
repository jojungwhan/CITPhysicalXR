# MindWave Mobile 2 Fabric adapter

This package is an independently supervised, publish-only MindWave node.
Physical mode reuses the `HeadsetClient` implementation from the characterized
local Brain2Devices checkout at commit
`536a256ef3f4b3182a74891b5971e9124ed051b0` in a separate Python process. It
imports no Tello module.

Only NeuroSky-labelled eSense attention/meditation, signal quality, and blink
events are published. Raw EEG is never emitted or persisted, and eSense values
are explicitly not represented as medical or objective attention measures.
Brain2Devices' optional automatic EEG-to-flight demo trigger is not imported or
advertised by this adapter. The separately supervised
`cit.brain2devices-demo` compatibility plugin is the only Fabric boundary that
can expose that explicitly armed, one-shot workflow.
