# Target State

Status: accepted architecture for the first CIT Interaction Fabric reference implementation.

## Architectural shape

```text
Course pack + instructor policy
              │
              ▼
Interaction session ─ role bindings ─ flow recipes
              │
              ▼
Event intake ─ flow decision ─ target resolution ─ command arbiter
              │                                      │
              └──────── trace/audit ◀ safety policy ◀┘
                                                     │
                                                     ▼
                         in-process adapter or authenticated wire adapter
                                                     │
                                                     ▼
                               vendor device / Agent Mesh / simulator
```

Every running integration is a node. Input/output is a property of advertised capabilities, not a permanent device category.

## Core boundaries

### Contracts

One Draft 2020-12 JSON Schema source defines canonical Fabric manifests, nodes, capabilities, health, semantic events, role bindings, command requests, lifecycle outcomes, flow recipes, course packs, and adapter wire frames. Generated Python and TypeScript bindings are convenience artifacts; JSON is the language-neutral contract.

Existing Physical XR protocol v1 types remain valid. Fabric messages use their own `schemaVersion` and additive API namespace so current classroom, authoring, LEGO, and Studio clients do not break.

### Registry

The registry stores:

- plugin manifests separately from running node instances;
- published and consumed capability descriptors with direction, version, constraints, units, rate, latency, safety, and data classifications;
- host, site, room, connection, health, and simulator state;
- last-seen and lease expiry for out-of-process nodes.

Registration never grants command authority. A node is selectable only when its state, capability version, constraints, session assignment, and policy all match.

### Session and role assignment

An interaction session names a course pack and binds logical roles such as `primary_glasses` or `coding_agent` to exact node IDs. Assignment is explicit and session-scoped. The selected `coding_agent` node represents an existing managed or observed Agent Mesh session; Fabric does not create an unrestricted shell process.

### Event path

Adapters publish bounded semantic events. The runtime validates schema, source registration, capability, session, sequence, timestamp, TTL, data class, and size before persistence or flow evaluation. Raw continuous video, audio, and biosignal streams are outside the ordinary Fabric bus.

### Flow path

The first flow engine deliberately supports a small deterministic subset:

- exact event and optional intent match;
- minimum confidence and TTL;
- debounce;
- fixed parameter mapping and bounded template substitution;
- logical target role;
- session, connectivity, role, and approval guards;
- one command action plus optional display routing.

No expression evaluator, arbitrary code, shell, or LLM-authored executable flow is permitted. Unsupported recipe features fail validation.

### Command path

```text
PROPOSED
→ VALIDATED
→ AUTHORIZED
→ DISPATCHED
→ ACCEPTED
→ RUNNING
→ SUCCEEDED | FAILED | CANCELLED | TIMED_OUT | REJECTED
```

Every command retains one correlation chain from source event through flow decision, role resolution, arbitration, safety decision, adapter dispatch, and result. Delivery may be retried, but physical execution is idempotent and TTL-bounded. Movement commands are not placed in a replayable durable outbox.

The arbiter preserves this precedence:

1. emergency stop;
2. deterministic safety engine;
3. instructor override;
4. approved lesson automation;
5. student interaction;
6. autonomous agent proposal.

### Adapter boundary

In-process adapters continue to implement the existing Python lifecycle protocol through a compatibility wrapper. Out-of-process adapters connect over an authenticated WebSocket wire protocol and exchange bounded registration, heartbeat, event, command acknowledgement, command result, and stop frames.

The core imports no vendor SDK. Adapter processes are supervised independently and enter a defined unavailable/safe state when their lease expires.

## First vertical slice

```text
G2 or Meta
  → Agent Mesh durable Fabric intent outbox
  → least-authority bridge identity
  → interaction.intent event
  → glasses-agent-control flow
  → role: coding_agent
  → agent.prompt.submit command
  → exact existing Agent Mesh session
  → normalized agent output/status events
  → role: primary_glasses and/or instructor_console
```

Legacy glasses-to-session behavior stays available when Fabric mode is disabled. The current compatibility checkpoint is deliberately narrower than final cutover:

- G2 and Meta keep their working exact-session prompt path;
- Agent Mesh durably mirrors the already-dispatched semantic intent to Fabric;
- the assigned `coding_agent` role must match that exact requested session, otherwise Fabric rejects the mirrored command rather than dispatching twice;
- Agent Mesh remains the authority for workspace, process, prompt, and approval permissions;
- the bridge cannot control physical movement or access device credentials;
- Agent Mesh persists the outgoing intent before delivery and replays the same identity until acknowledged or expired;
- Fabric traces the correlated command without repeating it, publishes normalized completion events, and confirms the existing glasses projection without repeating the display.

The later native-cutover gate will move initial prompt selection behind the Fabric role while retaining cross-system idempotency. It is not claimed by this checkpoint.

## Authentication and trust boundaries

### Instructor console

The Python runtime issues and stores hashes of independent CIT tokens. Tokens carry actor ID, role, site/room/session scope, explicit capabilities, creation/expiry, and revocation state. Administrator, instructor, teaching-assistant, student, observer, automated-agent, and adapter identities are not interchangeable.

The production console is served from the same origin as the API. The local
launcher obtains a high-entropy, one-use console ticket and places only that
short-lived ticket in the URL fragment. The page removes it before requesting
classroom data and exchanges it for an instructor-scoped bearer credential.
Bearer credentials stay in memory, never URL parameters, fragments, local
storage, or session storage. All state-changing Fabric routes require an
authenticated scope and append an audit record. WebSocket authentication uses
the first frame or an HttpOnly same-origin session established through explicit
token exchange; origin is checked exactly.

The upstream classroom and simulator routes remain compatibility routes during migration and are clearly separated from the independently authorized standalone Fabric service.

### Agent Mesh bridge

The compatibility bridge receives a dedicated CIT adapter credential and a dedicated read-only Agent Mesh device credential. It can register its exact nodes and publish semantic intent/output and lifecycle reports, but it has no administrator, prompt, arbitrary workspace, shell, approval-grant, arm, or movement scope. A future native-cutover credential must be reviewed separately before gaining an idempotent typed prompt/cancel capability.

## Data and privacy model

- Semantic event persistence uses a declared data classification and retention policy.
- Raw audio, camera frames, video, continuous EEG, secrets, tokens, unredacted CLI frames, hidden reasoning, and full filesystem content are rejected from standard event payloads.
- MindWave signals retain vendor namespaces and are never relabelled as objective attention.
- Agent visible output is bounded and redacted before crossing Agent Mesh; artifacts are referenced by opaque metadata, not copied wholesale.
- Recording is visible, opt-in where raw sensitive data is ever required, and dry-run on replay.

## Deployment

- One local orchestrator and same-origin console per classroom host.
- Zero or more authenticated local/remote edge adapter processes.
- Optional Agent Mesh bridge on a host that can reach both local services.
- Optional administrative distribution service outside all emergency and continuous-control loops.
- Emergency stop, disarm, connection-loss safe state, and interactive ground control remain local.

## Extensibility invariant

Adding a plugin supplies a manifest, adapter implementation, configuration schema, contract tests, and simulator/mock. It does not add model-specific routing branches to the orchestration core.
