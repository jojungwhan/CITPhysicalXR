# Reuse Audit

- Status: Milestone 0 discovery baseline
- Audited: 2026-08-16
- Method: read-only source, manifest, Git, test, and installed-environment inspection. No hardware discovery or connection was attempted, and none of the audited repositories was modified.

## Executive decision

The existing assets are strong reference and later integration candidates, but no source is copied into this Apache-2.0 repository in Milestone 0.

- Agent CLI Mesh is private and its README says that no licence has been selected. CIT will integrate it through the optional authenticated bridge in Milestone 7 unless its owner later publishes compatible reusable packages.
- The RoboMaster gesture repository is the correct S1/Leap behavior baseline and is pinned by the existing Agent Mesh RoboMaster work. It has no top-level licence for its original code, so Milestone 2 will wrap the owner-designated checkout rather than copy it.
- A working DJI SDK environment was found at `D:\dev\robomasterCITCourse\.venv-robot`; the Leap runtime expected by the gesture checkout was not found. This is an explicit discovery gap, not evidence that Leap is unavailable on the owner's other machines.
- The alternate Agent Mesh RoboMaster branch allows confirmed wearable movement pulses. That behavior conflicts with the Physical XR v1 rule that wearables may stop but may not initiate movement, so it is reference-only for stop/status/expiry patterns.

## Repository inventory

| Repository                          | Local path                                    | Branch / revision                                                             | Working tree                                                       | Licence finding                                                                                          |
| ----------------------------------- | --------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| Agent CLI Mesh                      | `D:\dev\glasses2CLI`                          | `fix/g2-durable-alert-ack` / `79983dfadc378566168343e57814a046089c2047`       | Dirty before this audit: three owner-edited Meta phone files/tests | README: no licence selected; private                                                                     |
| Agent CLI Mesh RoboMaster branch    | `D:\dev\glasses2CLI-robomaster`               | `agent/stabilize-g2-launcher-ci` / `644895966ad3e1f2011dcc83ed111cd2f12762b1` | Clean                                                              | Same unlicensed private repository                                                                       |
| Agent CLI Mesh service branch       | `D:\dev\glasses2CLI-service-replace`          | `agent/windows-service-replace` / `75a16343ac597d8eaecc1fbb5ea6f6f297507875`  | Clean                                                              | Same unlicensed private repository; no unique Physical XR candidate found                                |
| RoboMaster gesture control          | `D:\dev\robomaster-gesture-control-reference` | `main` / `e5a94865451dc8a9a266bb9223f8ed090ac11681`                           | Clean                                                              | No top-level project licence; an Apache-2.0 text covers the attributed Ultraleap-derived visualizer only |
| RoboMaster classroom mission system | `D:\dev\robomasterCITCourse`                  | `main` / `2f54bc7f2de6925b1e388632c45cb4dd7296d660`                           | Clean                                                              | No top-level project licence found; third-party model notices exist                                      |

## Detailed module decisions

### R-001 — Agent Mesh protocol and normalized event envelope

| Field             | Finding                                                                                                                                                                                                             |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source repository | Agent CLI Mesh, `D:\dev\glasses2CLI`                                                                                                                                                                                |
| Module            | `packages/protocol/src/envelope.ts`, `session.ts`, `node.ts`, `errors.ts`, and `message-types.ts`                                                                                                                   |
| Purpose           | Version-1 message envelope, typed command expiry/idempotency, node identity fields, normalized Claude/Codex session events, and typed errors                                                                        |
| Language/runtime  | TypeScript ESM on Node.js; Zod validators                                                                                                                                                                           |
| Licence           | No licence selected for Agent CLI Mesh; direct copying or distribution is not permitted by current repository evidence                                                                                              |
| Current tests     | `envelope.test.ts`, `session.test.ts`, `node.test.ts`, `control.test.ts`, `observed.test.ts`, and workspace tests cover versions, typed payloads, exact correlation, expiry, sequence bounds, and data minimization |
| Dependencies      | `zod`; Node.js 22.17+ in the audited manifest                                                                                                                                                                       |
| Protocol          | JSON messages over REST/WebSocket; envelope contains version, IDs, sequence, timestamps, expiry, idempotency, node/device identity, and payload                                                                     |
| Reusability       | Reference now; later adapter mapping. Direct package reuse only after a compatible licence and release boundary exist                                                                                               |
| Required changes  | Keep the physical protocol domain-neutral and JSON-Schema-first; map Agent Mesh status/events in `apps/agent-mesh-bridge` without importing Claude/Codex vendor types into the runtime                              |
| Risk              | Medium: good design fit, but licence and session-domain coupling prevent direct reuse now                                                                                                                           |
| Decision          | Adapt through an optional authenticated API in Milestone 7                                                                                                                                                          |
| Evidence          | Symbols `PROTOCOL_VERSION`, `meshEnvelopeSchema`, `hubCommandEnvelopeSchema`, `normalizedAgentEventSchema`, and `meshErrorSchema`; exact paths above                                                                |

### R-002 — Agent Mesh security and scoped device tokens

| Field             | Finding                                                                                                                                                                                      |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source repository | Agent CLI Mesh, `D:\dev\glasses2CLI`                                                                                                                                                         |
| Module            | `packages/security`, `packages/wearable-api/src/schemas.ts`, `packages/persistence/src/wearable-store.ts`, Hub device-token routes, Android `KeystoreSecretStore.java`                       |
| Purpose           | Ed25519 node identity, protected secret stores, visible-text redaction, hashed/expiring/revocable device tokens, device scopes, and Android Keystore encryption                              |
| Language/runtime  | TypeScript/Node.js and Java/Android API 26+                                                                                                                                                  |
| Licence           | No Agent Mesh licence selected. Third-party dependencies inspected include MIT Zod and the platform Android APIs                                                                             |
| Current tests     | Node challenge tamper/expiry, DPAPI/protected-file storage, traversal rejection, redaction, scoped token issuance/authentication/rotation/revocation, and Android pairing/Keystore behaviors |
| Dependencies      | Node crypto, Windows DPAPI or protected files, SQLite persistence, Android Keystore/AES-GCM                                                                                                  |
| Protocol          | Bearer device tokens in headers, never URLs; scopes currently include read, prompt, and approval                                                                                             |
| Reusability       | Agent Mesh bridge can consume existing tokens directly. CIT-local Quest/device pairing needs a separate local scope model                                                                    |
| Required changes  | Add physical-status and stop-only scopes/routes in Agent Mesh during Milestone 7; never grant movement authority; define local Quest tokens independently                                    |
| Risk              | High if token authorities are conflated; low for consuming an existing least-authority token through the bridge                                                                              |
| Decision          | Reuse the deployed Agent Mesh authority through its API; reference security patterns only for original CIT code                                                                              |
| Evidence          | `generateNodeIdentity`, `verifyNodeChallenge`, `redactVisibleText`, `WEARABLE_DEVICE_SCOPES`, `WearableStore.issueDeviceToken`, and `KeystoreSecretStore`                                    |

### R-003 — Agent Mesh configuration

| Field             | Finding                                                                                                                    |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Source repository | Agent CLI Mesh, `D:\dev\glasses2CLI`                                                                                       |
| Module            | `packages/config/src/schema.ts`, `loader.ts`, `config/examples`                                                            |
| Purpose           | Strict YAML validation, secure remote URL rules, platform-native paths, reconnect settings, and non-secret configuration   |
| Language/runtime  | TypeScript, Zod, YAML                                                                                                      |
| Licence           | No Agent Mesh licence selected; `yaml` dependency is ISC                                                                   |
| Current tests     | Unknown-field rejection, remote TLS enforcement, Windows/POSIX path preservation, and shipped JSON Schema parsing          |
| Dependencies      | `yaml`, `zod`, Agent Mesh protocol                                                                                         |
| Protocol          | YAML files validated into typed configuration                                                                              |
| Reusability       | Design reference; CIT needs different device/runtime fields and JSON Schema as the source of truth                         |
| Required changes  | Keep repository paths and runtime configuration outside secrets; add explicit Windows/Linux path slots without translation |
| Risk              | Low conceptually; direct source reuse blocked by licence                                                                   |
| Decision          | Implement an original CIT schema and loader contract in Milestone 0                                                        |
| Evidence          | `meshConfigSchema`, `parseMeshConfigText`, and `getDefaultConfigPath`                                                      |

### R-004 — Agent Mesh persistence, audit, and replay

| Field             | Finding                                                                                                                                                                                |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source repository | Agent CLI Mesh, `D:\dev\glasses2CLI`                                                                                                                                                   |
| Module            | `packages/persistence`, especially `database.ts`, `node-store.ts`, `hub-store.ts`, `session-store.ts`, `hub-command-store.ts`, `dashboard-store.ts`, and `wearable-store.ts`           |
| Purpose           | SQLite-WAL stores for sequence acknowledgement, bounded queues, idempotency, session events, scoped token hashes, expiring commands, chained audit, and verified backups               |
| Language/runtime  | TypeScript/Node.js with SQLite                                                                                                                                                         |
| Licence           | No Agent Mesh licence selected                                                                                                                                                         |
| Current tests     | Persistence/restart, contiguous sequence, gaps/duplicates, queue bounds, command expiry and payload scrubbing, token rotation, audit-chain tamper detection, and backups               |
| Dependencies      | Node SQLite APIs and Agent Mesh protocol/wearable packages                                                                                                                             |
| Protocol          | Durable sequence cursors and command outcomes; WebSocket transport reconciles through acknowledged sequence                                                                            |
| Reusability       | Domain-neutral concepts are candidates for extraction after licensing; current tables are Agent-session-specific                                                                       |
| Required changes  | Physical runtime needs separate tables and a hard rule that movement is never durable/replayed; telemetry may be durable and marked historical                                         |
| Risk              | High if generic replay is reused for movement without a physical-command policy                                                                                                        |
| Decision          | Reference only in Milestone 0; design a separate physical persistence layer in Milestone 1                                                                                             |
| Evidence          | `NodeStore.pending/acknowledge`, `HubStore.persistNodeMessage`, `SessionStore.claimCommand`, `HubCommandStore.listUnacknowledged/expirePending`, and `DashboardStore.verifyAuditChain` |

### R-005 — Agent Mesh observability and redaction

| Field             | Finding                                                                                                                                     |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Source repository | Agent CLI Mesh, `D:\dev\glasses2CLI`                                                                                                        |
| Module            | `packages/observability/src/index.ts` and `packages/security/src/redaction.ts`                                                              |
| Purpose           | Structured context policy and bounded credential/path/ANSI redaction for visible output                                                     |
| Language/runtime  | TypeScript/Node.js                                                                                                                          |
| Licence           | No Agent Mesh licence selected                                                                                                              |
| Current tests     | Redaction covers bearer tokens, common API keys, signed URLs, private keys, ANSI/control characters, extra configured keys, and size bounds |
| Dependencies      | None for observability; regex and Node runtime for redaction                                                                                |
| Protocol          | Structured log context; no transport of its own                                                                                             |
| Reusability       | Redaction behavior is valuable but source cannot be copied under current licence state                                                      |
| Required changes  | CIT logs add runtime, device, adapter, safety-decision, latency, and correlation fields; raw biometric/video/audio remains excluded         |
| Risk              | Medium because incomplete redaction could leak device secrets                                                                               |
| Decision          | Reimplement and test CIT-specific redaction before production logging; consider shared extraction after licensing                           |
| Evidence          | `LogContext`, `OBSERVABILITY_POLICY`, `configureProcessRedaction`, and `redactVisibleText`                                                  |

### R-006 — Wearable API, concise projections, and deterministic resolution

| Field             | Finding                                                                                                                                                               |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source repository | Agent CLI Mesh, `D:\dev\glasses2CLI`                                                                                                                                  |
| Module            | `packages/wearable-api/src/schemas.ts`, `client.ts`, `projection.ts`, `resolver.ts`, and `event-queue.ts`                                                             |
| Purpose           | Bounded snapshots/events, concise display and speech text, deterministic session selection, ambiguity rejection, scoped HTTP client, and priority/coalescing queues   |
| Language/runtime  | TypeScript; HTTP/fetch; Zod                                                                                                                                           |
| Licence           | No Agent Mesh licence selected                                                                                                                                        |
| Current tests     | Scope trust rules, bounded projection, high-value speech, deterministic ambiguity rejection, bounded queue behavior, token-bearing URL rejection, and response limits |
| Dependencies      | Agent Mesh protocol and Zod                                                                                                                                           |
| Protocol          | Authenticated REST plus cursor-based feeds; OpenAI-compatible command route for G2                                                                                    |
| Reusability       | Directly usable by existing G2/Meta clients after Agent Mesh API extension; not imported by the physical runtime                                                      |
| Required changes  | Add physical status cards and typed pause/stop routes only; retain existing selection and display behavior                                                            |
| Risk              | Low for status/stop extension, high if prompt/control endpoints are mapped to robot movement                                                                          |
| Decision          | Extend the existing API/client in Milestone 7 instead of creating new glasses clients                                                                                 |
| Evidence          | `WearableHttpClient`, `projectWearableSession`, `formatWearableSessionCard`, `resolveWearableCommand`, and `BoundedWearableEventQueue`                                |

### R-007 — Even Realities G2 client and plugin

| Field             | Finding                                                                                                                                                                                     |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source repository | Agent CLI Mesh, `D:\dev\glasses2CLI`                                                                                                                                                        |
| Module            | `apps/even-g2`, `apps/even-g2-plugin`                                                                                                                                                       |
| Purpose           | Existing Even Hub application, credential bootstrap, concise session pages, gestures/voice, durable alert cursors, and update handling                                                      |
| Language/runtime  | TypeScript/Vite in the Even Hub WebView                                                                                                                                                     |
| Licence           | Agent Mesh code unlicensed/private; `@evenrealities/even_hub_sdk` 0.0.10 reports MIT                                                                                                        |
| Current tests     | Bootstrap credential stripping, private enrollment, WebView reload recovery, durable completion/Telegram acknowledgement, session navigation, voice bounds, packaging, and update detection |
| Dependencies      | `@agentmesh/wearable-api`, `@evenrealities/even_hub_sdk`, Vite                                                                                                                              |
| Protocol          | Authenticated Agent Mesh REST/OpenAI-compatible routes; cursor feeds; Even Hub SDK callbacks                                                                                                |
| Reusability       | Existing app should be extended, not forked or duplicated                                                                                                                                   |
| Required changes  | Render Physical XR status and offer only pause/stop/request-arm actions allowed by the PRD                                                                                                  |
| Risk              | Medium due private deployment and credential bootstrap lifecycle                                                                                                                            |
| Decision          | Reuse by extension in Agent Mesh Milestone 7; no G2 code in this repository                                                                                                                 |
| Evidence          | `EvenG2Client`, `consumeEvenG2Bootstrap`, completion/Telegram cursor helpers, `view.ts`, `voice.ts`, and package tests                                                                      |

### R-008 — Android bridge and Meta smart-glasses path

| Field             | Finding                                                                                                                                                                                                             |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source repository | Agent CLI Mesh, `D:\dev\glasses2CLI`                                                                                                                                                                                |
| Module            | `apps/android-bridge/src`, native `common`, `phone`, and `wear` modules                                                                                                                                             |
| Purpose           | Phone/Wear bridge, encrypted device credential storage, Meta speech/keep-alive delivery, G2 notifications, media-button ownership, and concise speech formatting                                                    |
| Language/runtime  | TypeScript boundary plus Java 17; Android compile SDK 36; phone min SDK 26; Wear min SDK 30                                                                                                                         |
| Licence           | Agent Mesh code unlicensed/private; Google Play Services dependencies have vendor terms                                                                                                                             |
| Current tests     | Spoken transition selection, pairing, credential-safe bootstrap, snapshot/feed ordering, Meta completion/Telegram speech plans, reconnect backlog summaries, media ownership, G2 lens policy, and speech formatting |
| Dependencies      | Agent Mesh wearable API, Android Keystore, Google Play Services Wearable 20.0.1, JUnit 4.13.2                                                                                                                       |
| Protocol          | Authenticated HTTPS REST with bearer header; Wear data layer; Android notifications/TTS/Bluetooth integration                                                                                                       |
| Reusability       | Existing phone and glasses paths should receive a physical-status extension                                                                                                                                         |
| Required changes  | Add stop/status presentation and typed requests; never translate arbitrary speech into movement                                                                                                                     |
| Risk              | Medium because device/vendor lifecycle behavior is hardware-specific and the audited branch has owner edits                                                                                                         |
| Decision          | Extend in Agent Mesh Milestone 7; do not create a second Meta or Android bridge                                                                                                                                     |
| Evidence          | `AndroidBridgeClient`, `HubClient`, `KeystoreSecretStore`, `GlassesSpeechFormatter`, `MetaVoiceKeepAliveService`, and native tests                                                                                  |

### R-009 — WebSocket reconnect, replay, ordering, and idempotency

| Field             | Finding                                                                                                                                                                                             |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source repository | Agent CLI Mesh, `D:\dev\glasses2CLI`                                                                                                                                                                |
| Module            | `apps/node/src/node-client.ts`, `packages/persistence/src/node-store.ts`, and `packages/agent-runtime`                                                                                              |
| Purpose           | Authenticated WebSocket reconnect with jittered exponential backoff, hello/welcome sequence reconciliation, durable pending events, gaps, acknowledgements, bounded queues, and command idempotency |
| Language/runtime  | TypeScript/Node.js using `ws` 8.21.3 (MIT)                                                                                                                                                          |
| Licence           | Agent Mesh source unlicensed/private                                                                                                                                                                |
| Current tests     | Ordered/duplicate/gap tracking, idempotency expiry, queue bounds/cancellation, and durable reconnect state                                                                                          |
| Dependencies      | `ws`, protocol, persistence, security                                                                                                                                                               |
| Protocol          | WebSocket auth challenge, transport acknowledgements/gaps, versioned envelopes, replay after acknowledged sequence                                                                                  |
| Reusability       | Excellent for telemetry/status semantics; unsafe to apply blindly to movement commands                                                                                                              |
| Required changes  | The CIT bridge may reuse Agent Mesh event replay; the physical runtime must clear movement on reconnect and require a new lease/arm/dead-man signal                                                 |
| Risk              | High if transport replay and physical command replay are conflated                                                                                                                                  |
| Decision          | Reuse only on the Agent Mesh side; implement explicit no-motion-replay invariants in CIT                                                                                                            |
| Evidence          | `MeshNodeClient.#flushPending/#scheduleReconnect`, `EventSequenceTracker`, `InMemoryIdempotencyStore`, and `OrderedSessionCommandQueue`                                                             |

### R-010 — Claude/Codex adapters, CLI communication, and test harness

| Field             | Finding                                                                                                                                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source repository | Agent CLI Mesh, `D:\dev\glasses2CLI`                                                                                                                                                                      |
| Module            | `packages/adapter-claude`, `packages/adapter-codex`, `packages/agent-runtime`, `packages/test-harness`, and `apps/cli`                                                                                    |
| Purpose           | Vendor protocol normalization, safe visible output, session control/status, approvals, observed hooks, deterministic queueing, fake adapters, and operator CLI                                            |
| Language/runtime  | TypeScript/Node.js; vendor CLIs remain separate processes                                                                                                                                                 |
| Licence           | No Agent Mesh licence selected                                                                                                                                                                            |
| Current tests     | Sanitized protocol fixtures, unknown-message fail-closed behavior, approvals, idempotent prompts, process loss/reconcile, safe executable detection, fake adapter contract, and credential-safe CLI files |
| Dependencies      | Agent Mesh protocol/domain/persistence/security; vendor CLIs at runtime                                                                                                                                   |
| Protocol          | Claude structured JSONL/control and Codex App Server JSON-RPC-like messages normalized to Agent Mesh events                                                                                               |
| Reusability       | Status events are reusable through the bridge; vendor adapters must stay outside the physical runtime                                                                                                     |
| Required changes  | Subscribe to normalized Agent Mesh status only. Do not import vendor adapters or expose their prompt/process endpoints from the physical runtime                                                          |
| Risk              | High if CLI process control crosses the physical safety boundary                                                                                                                                          |
| Decision          | Reuse normalized status through Agent Mesh API in Milestone 7; reject direct runtime imports                                                                                                              |
| Evidence          | `ClaudeManagedAdapter`, `CodexManagedAdapter`, observed hook normalizers, runtime idempotency/sequence classes, `describeAgentAdapter`, and CLI tests                                                     |

### R-011 — Existing RoboMaster S1 and Leap Motion implementation

| Field             | Finding                                                                                                                                                                                          |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Source repository | RoboMaster gesture control, `D:\dev\robomaster-gesture-control-reference`                                                                                                                        |
| Module            | `robomaster_gesture/robot_adapter.py`, `leap_source.py`, `gesture.py`, `app.py`, `models.py`, `control_lease.py`, and native LeapC bridge                                                        |
| Purpose           | Dry-run or guarded S1 control from Leap input, SDK and stock-app transports, gesture dead-man state machine, stale tracking/command watchdogs, and cross-process controller lease                |
| Language/runtime  | Python; C/LeapC on Windows; DJI SDK 0.1.1.68 for SDK mode; Win32 W/A/S/D for stock S1                                                                                                            |
| Licence           | No top-level licence for original repository code. `LICENSES/Apache-2.0.txt` and notices apply to attributed Ultraleap-derived visualizer material, not automatically to all files               |
| Current tests     | Eleven unit modules cover gestures, direction mapping, command pump/watchdog, controller lease, status, stock S1 app adapter, visualizer, scene speech, voice, and YOLO safety                   |
| Dependencies      | Core requirement pins `robomaster==0.1.1.68`; optional Ultralytics 8.4.118 and Piper 1.6.0 have separate AGPL/GPL considerations; native LeapC SDK/service is proprietary runtime infrastructure |
| Protocol          | In-process Python interfaces today; LeapC native polling; DJI SDK or guarded desktop-key transport                                                                                               |
| Reusability       | Wrapper/subprocess reference integration; do not rewrite or copy before adapter contract/regression tests                                                                                        |
| Required changes  | Define handshake/health IPC, record exact interpreter/build/service versions, normalize Leap events, and ensure CIT owns the only physical lease in Milestone 2                                  |
| Risk              | High: hardware/environment fragility, unclear original-code licence, and missing local Leap runtime artifacts                                                                                    |
| Decision          | Preserve and wrap the exact owner-designated checkout in Milestone 2 after contract fixtures exist                                                                                               |
| Evidence          | Revision `e5a948...`; `GestureController`, `LeapSource`, `DjiRobotAdapter`, `S1AppKeyboardAdapter`, `CommandPump`, `ControllerLease`; dry-run default and watchdogs documented in README         |

### R-012 — Installed RoboMaster SDK environment and classroom code

| Field             | Finding                                                                                                                                   |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Source repository | RoboMaster classroom mission system, `D:\dev\robomasterCITCourse`                                                                         |
| Module            | `.venv-robot`, `autonomy.py`, setup scripts, vendored SDK wheel metadata, and tests                                                       |
| Purpose           | Existing S1/EP classroom navigation/safety system and a verified legacy DJI Python runtime                                                |
| Language/runtime  | CPython 3.8.10 at `D:\dev\robomasterCITCourse\.venv-robot\Scripts\python.exe`; `robomaster` 0.1.1.68                                      |
| Licence           | No top-level project licence found; vendor and model notices do not license original source                                               |
| Current tests     | Unit tests cover safety serialization, stop failures, impact latching, watchdogs, navigation, gimbal, local-only startup, and UI behavior |
| Dependencies      | Pinned/local DJI wheel plus NumPy, OpenCV, MSS, pyttsx3, sounddevice, Ultralytics, and optional OpenAI access                             |
| Protocol          | Direct Python SDK and local application state; no Leap integration found                                                                  |
| Reusability       | Environment compatibility evidence and selected safety behavior reference; not the CIT production adapter                                 |
| Required changes  | Owner must confirm whether this is the intended S1 interpreter or whether the missing `.venv-robomaster` environment exists elsewhere     |
| Risk              | High if upgraded in place; Python 3.8 and native DJI dependencies are intentionally isolated                                              |
| Decision          | Preserve read-only. Never install/upgrade into this environment from CIT tooling                                                          |
| Evidence          | `pyvenv.cfg` reports CPython 3.8.10; `pip show robomaster` reports 0.1.1.68 at the exact path above                                       |

### R-013 — Agent Mesh RoboMaster branch

| Field             | Finding                                                                                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source repository | `D:\dev\glasses2CLI-robomaster` at `644895966ad3e1f2011dcc83ed111cd2f12762b1`                                                                             |
| Module            | `apps/robomaster-bridge`, `packages/wearable-api/src/robomaster.ts`, Hub relay/routes, G2 and Meta extensions, `docs/ROBOMASTER.md`                       |
| Purpose           | Dry-run-by-default, expiring in-memory relay for confirmed glasses movement pulses, stop/status, and local camera descriptions                            |
| Language/runtime  | Python bridge plus TypeScript/Node.js and existing glasses clients                                                                                        |
| Licence           | Same unlicensed private Agent Mesh code; imports the pinned gesture repository rather than copying it                                                     |
| Current tests     | Python bridge fakes, relay expiry/epoch behavior, robot-only token scope, G2/Meta behavior, installer tests, and a hardware checklist                     |
| Dependencies      | Pinned gesture checkout `e5a948...`; Agent Mesh wearable/security/runtime packages                                                                        |
| Protocol          | Robot-only token, ephemeral command feed, durable sanitized observations, HTTP polling/status/result routes                                               |
| Reusability       | Stop/status, bridge process isolation, relay epoch, and camera-data-minimization concepts are useful; wearable movement is not reusable in Physical XR v1 |
| Required changes  | Remove movement authority from wearables, route all physical commands through CIT safety and lease/arming, and keep only typed stop/status integration    |
| Risk              | Critical if reused unchanged because it conflicts with FR-073/FR-079 and acceptance criterion 29                                                          |
| Decision          | Reference only; explicitly reject its movement route for Physical XR v1                                                                                   |
| Evidence          | `robomasterCommandInputSchema`, `RoboMasterBridge`, `MotionController`, and `docs/ROBOMASTER.md`                                                          |

## Environment gaps and owner follow-up

The following paths or runtime facts remain unresolved after local read-only discovery:

1. `D:\dev\.venv-robomaster\Scripts\python.exe`, expected by `run_gesture_control.ps1`, does not exist on this machine.
2. `D:\dev\robomaster-gesture-control-reference\build\leap_hand_bridge.dll` and its adjacent `LeapC.dll` do not exist.
3. No Ultraleap/Leap service, installed-program entry, or `LeapC.dll` was found in the standard Windows installation roots.
4. The working DJI environment exists, but no local evidence links `robomasterCITCourse\.venv-robot` to the Leap gesture checkout.
5. No owner-provided Linux clones or paths were found locally.
6. Original-code licensing needs an owner decision for Agent CLI Mesh, RoboMaster gesture control, and RoboMaster classroom mission repositories before source extraction or redistribution.

These gaps do not authorize an environment rebuild or hardware probe. Milestone 2 must begin with owner-confirmed paths and adapter contract fixtures.

## Reuse guardrails

- Import or call reusable code only across an explicit package or adapter boundary with recorded licence/version evidence.
- Do not create a dependency from Agent CLI Mesh back into this repository.
- Do not import Claude/Codex vendor adapters into the physical runtime.
- Do not replay physical movement after reconnect, even if the transport supports replay.
- Do not expose the alternate branch's wearable movement routes.
- Keep the existing S1 and Leap repositories and environments read-only until Milestone 2 is approved.
- Update this audit whenever a path, version, licence, or reuse decision changes.
