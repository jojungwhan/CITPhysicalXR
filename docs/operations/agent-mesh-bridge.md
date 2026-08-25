# Agent Mesh bridge runbook

This runbook enables the opt-in glasses-and-coding-agent compatibility slice on one local classroom host. It does not enable physical actuation.

## Automated Windows hardware-test path

The recommended Windows path attaches the glasses/agent bridge to the shared
Fabric UI. The bridge launcher owns only its session, bridge process, and
temporary Agent Mesh Hub changes; stopping it does not stop the shared Fabric
or another adapter. It never changes the scheduled-task definition.

```powershell
pnpm hardware:fabric:windows -- -Mode Start
$fabricRoot = Join-Path $env:LOCALAPPDATA "CITPhysicalXR\interaction-fabric"
pnpm hardware:glasses:windows -- -Mode Preflight -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:glasses:windows -- -Mode Start -SharedFabricRoot $fabricRoot -FabricPort 8766 -SelectMostRecentAgentSession
pnpm hardware:glasses:windows -- -Mode Status -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:glasses:windows -- -Mode Verify -SharedFabricRoot $fabricRoot -FabricPort 8766
pnpm hardware:glasses:windows -- -Mode Stop -SharedFabricRoot $fabricRoot -FabricPort 8766
```

The original no-`SharedFabricRoot` behavior remains available as a standalone
compatibility path, but it should not be used when multiple integration types
need to appear together.

The shared Fabric and component launchers open **CIT Classroom Control** with
automatic local sign-in. Choose **Glasses and coding assistant**, connect the
display/glasses and coding assistant roles, complete the safety check, and
start the lesson. Use the **CIT Classroom Control** Windows Desktop or Start
menu button to reopen the screen without restarting either service.

Prefer `-AgentMeshSessionId <exact-id>` over `-SelectMostRecentAgentSession` when the intended G2 or Meta session is already known. `-ProvisionWearables` invokes Agent Mesh's existing phone/G2 provisioner and therefore requires one authorized Android phone attached through ADB. Without that switch, a previously provisioned G2 or Meta phone bridge can reconnect normally.

For the ordered-drone lesson, tutors do not run that command. Connect one or more
Tellos in Classroom Control first (two or more for a multi-drone exercise),
choose **Find devices**, then choose **Connect**
on the G2/Meta card. The fixed launcher detects the existing bounded fleet
session, restarts the bridge against that exact session if necessary, and binds
up to four connected wearables as input-only nodes. It neither selects a coding
agent nor creates a glasses-agent lesson. Saying an approved exact phrase emits
only `{ intent: "start" }`; the raw transcript is not copied into the fleet
event and the current tutor arm is still mandatory.

The current Agent Mesh compatibility feed exposes an intent only after Agent
Mesh has dispatched the original phrase to the session selected by the
wearable. The fleet launcher does not select or grant a coding-agent role, but
an already selected Agent Mesh session may therefore also receive that phrase
as an ordinary prompt. That compatibility behavior cannot command aircraft:
coding-agent nodes have no fleet capability, the semantic fleet event contains
no transcript, and deterministic role, source, session-arm, controller-arm,
and safety checks still gate launch. A future native wearable-intent endpoint
should intercept these exact phrases before coding-agent dispatch.

Runtime state, logs, SQLite files, and DPAPI ciphertext default to `%LOCALAPPDATA%\CITPhysicalXR\glasses-hardware-test`; no plaintext credential is retained. On a clean start the launcher deliberately uses this order: create the draft Fabric session, start the bridge so nodes can register, bind connected nodes, then start the session. If no glasses client has polled Agent Mesh within two minutes, it remains visible but disconnected and cannot be bound until the owner opens or wears it and reruns `Start`.

### Owner-hardware acceptance check

1. Start a managed Claude/Codex session, or leave an idle observed session available for Agent Mesh's safe continuation path.
2. For G2, wear/wake the glasses and open the provisioned Even Hub plugin on the companion phone. For Meta Ray-Ban, confirm the Android phone's **Calls** and **Media** Bluetooth profiles, then visibly open **CIT glasses** once so Android may start its microphone foreground service.
3. Wait for the device to poll, then rerun `Start` with the exact Agent Mesh session selected on the glasses. `-SkipBuild` is appropriate for this rerun.
4. Confirm `-Mode Status` reports that session as `active` and the intended glasses node as `connected/healthy` or `connected/degraded`.
5. Send the harmless prompt `Reply exactly CIT_HARDWARE_OK. Do not use tools or modify files.` G2 voice starts with its configured back/right ring gesture; Meta starts with one right-temple tap and requires a second tap after transcript playback to confirm.
6. Run `-Mode Verify` and confirm it reports `PASS`: this requires an `interaction.intent.agent_prompt`, `SUCCEEDED / AGENT_MESH_ALREADY_DISPATCHED`, a visible/spoken completion, and `DISPLAY_ALREADY_PROJECTED`. Then run `-Mode Stop` and confirm the normal Agent Mesh Hub task is restored.

This is an owner-hardware gate: software tests, an emulator, or a stale device credential cannot substitute for the physical microphone, gesture, display/audio, latency, reconnect, and battery checks.

## 1. Build both systems

In `CITPhysicalXR`:

```text
pnpm install --frozen-lockfile
uv sync --all-packages --frozen
pnpm --filter @citxr/protocol build
pnpm --filter @citxr/agent-mesh-bridge build
pnpm --filter @citxr/studio-web build
```

Build and initialize Agent Mesh using its own `docs/OPERATIONS.md`. Keep both services on loopback unless the documented TLS/private-network controls have been configured.

## 2. Bootstrap CIT Fabric

Retrieve a random credential of at least 32 characters from the approved local secret store and expose it only to the runtime process as `CITXR_FABRIC_BOOTSTRAP_TOKEN`. Then start:

```text
uv run uvicorn cit_runtime.fabric_service:create_persistent_fabric_app --factory --host 127.0.0.1 --port 8766
```

Open `http://127.0.0.1:8766/fabric` and sign in with that bootstrap credential. The standalone Fabric service stores only its domain-separated hash; the upstream classroom runtime keeps its own authorization and database.

Use the administrator identity API to issue a dedicated adapter identity with:

- actor type `adapter`;
- role `plugin.cit.agent-mesh-bridge`;
- permissions `fabric.adapters.connect`, `fabric.events.publish`, and `fabric.nodes.write`;
- exact site and room scope;
- the shortest practical expiry.

The plaintext adapter token is returned once. Put it in the approved secret store; do not place it in a URL, command history, repository file, or log.

## 3. Enable the Agent Mesh mirror

Issue one Agent Mesh device identity named `cit-fabric-bridge`, kind `test_client`, with only the `read` scope. Write its one-time token to a new restrictive bootstrap file as described by Agent Mesh operations, provision it into the bridge secret store, and remove the bootstrap copy.

Start the Agent Mesh Hub with the exact identity enabled:

```text
pnpm agentmesh hub start --host 127.0.0.1 --port 7342 --cit-fabric-bridge-device cit-fabric-bridge
```

Omitting `--cit-fabric-bridge-device` leaves every Fabric mirror route disabled. A different valid wearable token receives `403` from those routes.

## 4. Create the lesson session

In the instructor console:

1. Select `Glasses and coding agents`.
2. Create a `Safe / simulated outputs` session for the bridge's exact site and room. This mode allows real informational glasses I/O but prohibits real motor, flight, or electrical actuation.
3. Copy its session ID and leave the new session in draft until the bridge has registered its nodes.

Compatibility mode intentionally rejects a coding-agent role that differs from the session already selected by the glasses. It never sends a second prompt to make the targets agree.

## 5. Start the bridge

Provide these values to the bridge process through the local service manager or approved secret injection mechanism:

| Variable                      | Value                                         |
| ----------------------------- | --------------------------------------------- |
| `CIT_FABRIC_ADAPTER_URL`      | `ws://127.0.0.1:8766/api/v1/adapters/connect` |
| `CIT_FABRIC_ADAPTER_TOKEN`    | Dedicated CIT adapter credential              |
| `CIT_FABRIC_READ_TOKEN`       | Session-scoped nodes/session read credential  |
| `CIT_FABRIC_SESSION_ID`       | Active interaction-session ID                 |
| `CIT_AGENT_MESH_URL`          | `http://127.0.0.1:7342`                       |
| `CIT_AGENT_MESH_DEVICE_TOKEN` | Exact read-only bridge device credential      |
| `CIT_BRIDGE_DATABASE_PATH`    | Absolute, access-restricted SQLite path       |
| `CIT_SITE_ID`, `CIT_ROOM_ID`  | Values matching the session                   |
| `CIT_BRIDGE_HOST_ID`          | Stable host identifier                        |

Then run:

```text
pnpm --filter @citxr/agent-mesh-bridge start
```

The bridge authenticates without URL credentials, discovers current glasses and agent sessions, registers their canonical capabilities, and starts heartbeat and durable semantic polling.

On a clean database, now refresh the instructor console:

1. Assign the connected G2 or Meta node to `primary_glasses`.
2. Assign the same existing Agent Mesh session that the glasses will address to `coding_agent`.
3. Optionally assign a compatible feedback display.
4. Start the now-ready session.

## 6. Verify

- Nodes appear connected in `/fabric` with the expected capabilities.
- A G2 or Meta prompt produces one `interaction.intent.agent_prompt` event.
- Its command lifecycle ends in `SUCCEEDED / AGENT_MESH_ALREADY_DISPATCHED`, proving duplicate execution was prevented.
- A mismatched assigned agent ends in `REJECTED / MIRROR_TARGET_MISMATCH`.
- Agent completion produces `agent.output.completed`; the correlated display command ends in `DISPLAY_ALREADY_PROJECTED`.
- Restarting the bridge replays unacknowledged semantic and lifecycle frames from its local outbox.

## 7. Stop and rollback

Stop the bridge process, then restart Agent Mesh without `--cit-fabric-bridge-device`. Revoke the dedicated Agent Mesh and CIT adapter identities if the integration will remain disabled. Existing glasses-to-agent behavior continues independently; no rollback rewrites or deletes its session history.

Do not copy or replay the bridge SQLite database onto another host. Unacknowledged rows can contain a bounded voice transcript or visible agent output; acknowledged rows retain correlation metadata and hashes, not the semantic text.
