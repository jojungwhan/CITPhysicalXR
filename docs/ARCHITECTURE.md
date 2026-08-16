# Milestone 0 Architecture

## Implemented boundary

Milestone 0 establishes types and test seams. It intentionally does not assemble the Milestone 1 runtime services.

```text
JSON Schema v1 ──generates──► TypeScript models
       │
       └─────────generates──► Python/Pydantic models
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
            safety foundation          DeviceAdapter protocol
       expiry · dedupe · lease · denial         │
                                                ▼
                                  in-memory S1 · Leap · LEGO · Quest
```

The fake adapters are marked `physical: false`. They have no vendor SDK dependency and no socket, Bluetooth, USB, subprocess, or hardware path.

## Future command boundary

The approved architecture for later milestones is request → local runtime → safety supervisor → exact leased adapter → device. Studio, student Python, Quest, Leap, wearables, Agent Mesh, and AI integrations never receive adapters or vendor SDK access. Milestone 0 tests individual prerequisites for that chain but does not implement or claim the chain itself.

## Application scaffolds

- Studio is a buildable React page that reports foundation status.
- Runtime Python contains schema-validated configuration selection only.
- Agent Mesh bridge contains an allow/deny policy only and has no transport.
- Quest is a parseable text project/scene/script scaffold with OpenXR explicitly unconfigured.

## External systems

Existing Agent Mesh and RoboMaster/Leap work remains outside this repository. `REUSE_AUDIT.md` records exact checkout revisions, file evidence, licences, and reuse decisions. No external source was copied into the implementation.
