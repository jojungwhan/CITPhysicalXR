import { createHash, randomUUID } from "node:crypto";

import {
  validateDefinition,
  type AdapterEventFrame,
  type CapabilityDescriptor,
  type HealthReport,
  type IntegrationNode,
  type PluginManifest,
} from "@citxr/protocol";

import type { BridgeConfig } from "./config.js";
import type { BridgeOutbox } from "./outbox.js";
import type {
  AgentMeshCompletion,
  AgentMeshCompanionInput,
  AgentMeshDiscovery,
  AgentMeshDeviceControlInteraction,
  AgentMeshRingInteraction,
  AgentMeshIntent,
  AgentMeshSession,
  AgentMeshWearable,
} from "./types.js";

type ProtocolDefinitionName = Parameters<typeof validateDefinition>[0];

export const AGENT_MESH_PLUGIN_ID = "cit.agent-mesh-bridge";
export const INTENT_CAPABILITY = "interaction.intent.agent_prompt";
export const FLIGHT_SEQUENCE_INTENT_CAPABILITY =
  "interaction.intent.flight_sequence_start";
export const RING_GESTURE_CAPABILITY = "interaction.gesture.smart_ring";
export const DEVICE_CONTROL_INTENT_CAPABILITY =
  "interaction.intent.device_control";
export const AGENT_PROMPT_CAPABILITY = "agent.prompt.submit";
export const AGENT_OUTPUT_CAPABILITY = "agent.output.completed";
export const DISPLAY_CAPABILITY = "display.text.render";

export const semanticSha256 = (value: string): string =>
  createHash("sha256").update(value, "utf8").digest("hex");

const VERSION = "0.1.0";
const RUNTIME_VERSION = "node-22";
const MAX_ADAPTER_NODES = 64;
const WEARABLE_CONNECTION_WINDOW_MS = 120_000;
const MAX_FUTURE_LAST_USE_SKEW_MS = 30_000;
const RECENTLY_EXITED_OBSERVED_MS = 30 * 60_000;
const UNAVAILABLE_AGENT_STATES = new Set([
  "failed",
  "stopping",
  "stopped",
  "disconnected",
]);

const intentCapability: CapabilityDescriptor = {
  name: INTENT_CAPABILITY,
  version: "1.0",
  direction: "publish",
  latencyClass: "conversational",
  safetyClassification: "none",
  dataClassification: "voice_transcript",
  constraints: { maximumUtf8Bytes: 32_768, semanticOnly: true },
};

const flightSequenceIntentCapability: CapabilityDescriptor = {
  name: FLIGHT_SEQUENCE_INTENT_CAPABILITY,
  version: "1.0",
  direction: "publish",
  latencyClass: "interactive",
  safetyClassification: "informational",
  dataClassification: "operational",
  constraints: {
    semanticOnly: true,
    structuredIntentOnly: true,
    acceptedModalities: ["voice", "smart_ring"],
    rawTranscriptExcluded: true,
  },
};

const ringGestureCapability: CapabilityDescriptor = {
  name: RING_GESTURE_CAPABILITY,
  version: "1.0",
  direction: "publish",
  latencyClass: "interactive",
  safetyClassification: "informational",
  dataClassification: "operational",
  constraints: {
    semanticOnly: true,
    source: "even_r1",
    gestures: ["tap", "double_tap", "scroll_up", "scroll_down"],
  },
};

const deviceControlIntentCapability: CapabilityDescriptor = {
  name: DEVICE_CONTROL_INTENT_CAPABILITY,
  version: "1.0",
  direction: "publish",
  latencyClass: "interactive",
  safetyClassification: "informational",
  dataClassification: "operational",
  constraints: {
    semanticOnly: true,
    structuredIntentOnly: true,
    rawTranscriptExcluded: true,
    confirmedOnly: true,
    actions: [
      "forward",
      "backward",
      "left",
      "right",
      "stop",
      "light",
      "demo",
      "takeoff",
      "land",
      "power_on",
      "power_off",
      "activate",
    ],
    targets: [
      "ground_outputs",
      "tello_fleet",
      "power_outputs",
      "assigned_output",
      "all_outputs",
    ],
    exactLessonRoleSelection: true,
    correlatedBatchId: true,
  },
};

const promptCapability: CapabilityDescriptor = {
  name: AGENT_PROMPT_CAPABILITY,
  version: "1.0",
  direction: "consume",
  latencyClass: "conversational",
  safetyClassification: "none",
  dataClassification: "source_code",
  constraints: {
    maximumUtf8Bytes: 32_768,
    structuredParametersOnly: true,
    unrestrictedShellFromDeviceInput: false,
  },
};

const outputCapability: CapabilityDescriptor = {
  name: AGENT_OUTPUT_CAPABILITY,
  version: "1.0",
  direction: "publish",
  latencyClass: "ui_feedback",
  safetyClassification: "informational",
  dataClassification: "source_code",
  constraints: { maximumDisplayCharacters: 500, semanticOnly: true },
};

const displayCapability: CapabilityDescriptor = {
  name: DISPLAY_CAPABILITY,
  version: "1.0",
  direction: "consume",
  latencyClass: "ui_feedback",
  safetyClassification: "informational",
  dataClassification: "student",
  constraints: {
    maximumCharacters: 500,
    compatibilityMode: "agent_mesh_completion_projection",
  },
};

export interface AgentMeshFabricMapping {
  readonly manifest: PluginManifest;
  readonly nodes: [IntegrationNode, ...IntegrationNode[]];
  readonly wearableNodeByDeviceId: ReadonlyMap<string, IntegrationNode>;
  readonly companionNodeByParentDeviceId: ReadonlyMap<string, IntegrationNode>;
  readonly agentNodeBySessionId: ReadonlyMap<string, IntegrationNode>;
  readonly agentSessionByNodeId: ReadonlyMap<string, AgentMeshSession>;
}

export const mapDiscovery = (
  discovery: AgentMeshDiscovery,
  config: BridgeConfig,
): AgentMeshFabricMapping => {
  const wearableNodeByDeviceId = new Map<string, IntegrationNode>();
  const companionNodeByParentDeviceId = new Map<string, IntegrationNode>();
  const agentNodeBySessionId = new Map<string, IntegrationNode>();
  const agentSessionByNodeId = new Map<string, AgentMeshSession>();
  for (const wearable of discovery.wearables) {
    const node = wearableNode(wearable, config, discovery.generatedAt);
    wearableNodeByDeviceId.set(wearable.deviceId, node);
  }
  if (wearableNodeByDeviceId.size > MAX_ADAPTER_NODES) {
    throw new TypeError("Agent Mesh discovery exceeds the wearable-node limit");
  }
  for (const companion of discovery.companionInputs ?? []) {
    const parent = wearableNodeByDeviceId.get(companion.parentDeviceId);
    if (
      parent === undefined ||
      parent.metadata.model !== "even-realities-g2" ||
      parent.metadata.applicationProfile !== "physical_controls"
    ) {
      continue;
    }
    const node = companionInputNode(companion, config, discovery.generatedAt);
    companionNodeByParentDeviceId.set(companion.parentDeviceId, node);
  }
  if (
    wearableNodeByDeviceId.size + companionNodeByParentDeviceId.size >
    MAX_ADAPTER_NODES
  ) {
    throw new TypeError("Agent Mesh discovery exceeds the input-node limit");
  }
  const agentCapacity =
    MAX_ADAPTER_NODES -
    wearableNodeByDeviceId.size -
    companionNodeByParentDeviceId.size;
  const selectedSessions = [...discovery.sessions]
    .sort(
      (left, right) =>
        Date.parse(right.lastActivityAt) - Date.parse(left.lastActivityAt) ||
        left.sessionId.localeCompare(right.sessionId),
    )
    .slice(0, agentCapacity);
  for (const session of selectedSessions) {
    const node = agentNode(session, config, discovery.generatedAt);
    agentNodeBySessionId.set(session.sessionId, node);
    agentSessionByNodeId.set(node.nodeId, session);
  }
  const nodes = [
    ...wearableNodeByDeviceId.values(),
    ...companionNodeByParentDeviceId.values(),
    ...agentNodeBySessionId.values(),
  ];
  if (nodes.length === 0) {
    throw new TypeError("Agent Mesh discovery returned no integration nodes");
  }
  const manifest: PluginManifest = {
    schemaVersion: "1.0",
    pluginId: AGENT_MESH_PLUGIN_ID,
    pluginVersion: VERSION,
    runtimeVersion: RUNTIME_VERSION,
    displayName: "Agent Mesh glasses and coding agents",
    adapterMode: "out_of_process",
    configurationSchema: {
      type: "object",
      additionalProperties: false,
      description:
        "Configured through the bridge process environment; secrets are never advertised.",
    },
    publishedCapabilities: [
      intentCapability,
      flightSequenceIntentCapability,
      ringGestureCapability,
      deviceControlIntentCapability,
      outputCapability,
    ],
    consumedCapabilities: [promptCapability, displayCapability],
    requiredPermissions: ["agentmesh.read"],
    safetyClassification: "informational",
    dataClassifications: ["voice_transcript", "source_code", "operational"],
    simulatorAvailability: "external",
    vendor: "CIT",
    description:
      "Thin, opt-in compatibility adapter around existing Agent Mesh behavior.",
  };
  assertValid("PluginManifest", manifest);
  for (const node of nodes) assertValid("IntegrationNode", node);
  return {
    manifest,
    nodes: nodes as [IntegrationNode, ...IntegrationNode[]],
    wearableNodeByDeviceId,
    companionNodeByParentDeviceId,
    agentNodeBySessionId,
    agentSessionByNodeId,
  };
};

export const ringGestureEventFrame = (
  interaction: AgentMeshRingInteraction,
  sourceNode: IntegrationNode,
  config: BridgeConfig,
  outbox: BridgeOutbox,
): AdapterEventFrame => {
  const frame: AdapterEventFrame = {
    frameType: "adapter.event",
    frameId: randomUUID(),
    protocolVersion: 1,
    event: {
      messageId: interaction.interactionId,
      schemaVersion: "1.0",
      messageType: "event",
      topic: RING_GESTURE_CAPABILITY,
      sourceNodeId: sourceNode.nodeId,
      sourceCapability: RING_GESTURE_CAPABILITY,
      siteId: config.siteId,
      roomId: config.roomId,
      sessionId: config.fabricSessionId,
      timestamp: interaction.createdAt,
      monotonicTimestamp: Date.now(),
      sequence: outbox.nextNodeSequence(sourceNode.nodeId),
      correlationId: interaction.interactionId,
      confidence: 1,
      ttlMs: 5_000,
      dataClassification: "operational",
      payload: {
        gesture: interaction.gesture,
        inputModality: "smart_ring",
        inputDevice: "even_r1",
        pairedGlassesDeviceId: interaction.deviceId,
      },
    },
    sentAt: new Date().toISOString(),
  };
  assertValid("AdapterEventFrame", frame);
  return frame;
};

export const deviceControlEventFrame = (
  interaction: AgentMeshDeviceControlInteraction,
  sourceNode: IntegrationNode,
  config: BridgeConfig,
  outbox: BridgeOutbox,
): AdapterEventFrame => {
  const frame: AdapterEventFrame = {
    frameType: "adapter.event",
    frameId: randomUUID(),
    protocolVersion: 1,
    event: {
      messageId: interaction.interactionId,
      schemaVersion: "1.0",
      messageType: "event",
      topic: DEVICE_CONTROL_INTENT_CAPABILITY,
      sourceNodeId: sourceNode.nodeId,
      sourceCapability: DEVICE_CONTROL_INTENT_CAPABILITY,
      siteId: config.siteId,
      roomId: config.roomId,
      sessionId: config.fabricSessionId,
      timestamp: interaction.createdAt,
      monotonicTimestamp: Date.now(),
      sequence: outbox.nextNodeSequence(sourceNode.nodeId),
      correlationId: interaction.batchId ?? interaction.interactionId,
      confidence: 1,
      ttlMs: 5_000,
      dataClassification: "operational",
      payload: {
        action: interaction.action,
        target: interaction.target,
        ...(interaction.targetRole === undefined
          ? {}
          : { targetRole: interaction.targetRole }),
        ...(interaction.batchId === undefined
          ? {}
          : { batchId: interaction.batchId }),
        confirmed: interaction.confirmed,
        inputModality: "voice",
        deviceKind: interaction.deviceKind,
      },
    },
    sentAt: new Date().toISOString(),
  };
  assertValid("AdapterEventFrame", frame);
  return frame;
};

export const ringFlightSequenceIntentFrame = (
  interaction: AgentMeshRingInteraction,
  sourceNode: IntegrationNode,
  config: BridgeConfig,
  outbox: BridgeOutbox,
): AdapterEventFrame | undefined => {
  if (interaction.gesture !== "double_tap") return undefined;
  const frame: AdapterEventFrame = {
    frameType: "adapter.event",
    frameId: randomUUID(),
    protocolVersion: 1,
    event: {
      messageId: randomUUID(),
      schemaVersion: "1.0",
      messageType: "event",
      topic: FLIGHT_SEQUENCE_INTENT_CAPABILITY,
      sourceNodeId: sourceNode.nodeId,
      sourceCapability: FLIGHT_SEQUENCE_INTENT_CAPABILITY,
      siteId: config.siteId,
      roomId: config.roomId,
      sessionId: config.fabricSessionId,
      timestamp: interaction.createdAt,
      monotonicTimestamp: Date.now(),
      sequence: outbox.nextNodeSequence(sourceNode.nodeId),
      correlationId: interaction.interactionId,
      causationId: interaction.interactionId,
      confidence: 1,
      ttlMs: 5_000,
      dataClassification: "operational",
      payload: {
        intent: "start",
        inputModality: "smart_ring",
        deviceKind: "even_r1",
        gesture: interaction.gesture,
      },
    },
    sentAt: new Date().toISOString(),
  };
  assertValid("AdapterEventFrame", frame);
  return frame;
};

export const intentEventFrame = (
  intent: AgentMeshIntent,
  sourceNode: IntegrationNode,
  config: BridgeConfig,
  outbox: BridgeOutbox,
): AdapterEventFrame => {
  const sequence = outbox.nextNodeSequence(sourceNode.nodeId);
  const frame: AdapterEventFrame = {
    frameType: "adapter.event",
    frameId: randomUUID(),
    protocolVersion: 1,
    event: {
      messageId: intent.intentId,
      schemaVersion: "1.0",
      messageType: "event",
      topic: INTENT_CAPABILITY,
      sourceNodeId: sourceNode.nodeId,
      sourceCapability: INTENT_CAPABILITY,
      siteId: config.siteId,
      roomId: config.roomId,
      sessionId: config.fabricSessionId,
      timestamp: intent.createdAt,
      monotonicTimestamp: Date.now(),
      sequence,
      correlationId: intent.intentId,
      causationId: intent.agentMeshCommandId,
      confidence: 1,
      ttlMs: 30_000,
      dataClassification: "voice_transcript",
      payload: {
        text: intent.prompt,
        requestedSessionId: intent.requestedSessionId,
        dispatchedSessionId: intent.dispatchedSessionId,
        agentMeshCommandId: intent.agentMeshCommandId,
        route: intent.route,
        alreadyDispatched: true,
      },
    },
    sentAt: new Date().toISOString(),
  };
  assertValid("AdapterEventFrame", frame);
  return frame;
};

const FLIGHT_SEQUENCE_PHRASES = new Set([
  "start drone sequence",
  "launch drone sequence",
  "take off drones",
  "드론 순차 이륙",
  "드론 이륙 시작",
]);

export const flightSequenceIntentFrame = (
  intent: AgentMeshIntent,
  sourceNode: IntegrationNode,
  config: BridgeConfig,
  outbox: BridgeOutbox,
): AdapterEventFrame | undefined => {
  if (
    !sourceNode.publishedCapabilities.some(
      (capability) => capability.name === FLIGHT_SEQUENCE_INTENT_CAPABILITY,
    )
  ) {
    return undefined;
  }
  const normalized = intent.prompt
    .normalize("NFKC")
    .toLocaleLowerCase("en-US")
    .trim()
    .replace(/[.!?…]+$/gu, "")
    .replace(/\s+/gu, " ");
  if (!FLIGHT_SEQUENCE_PHRASES.has(normalized)) return undefined;
  const frame: AdapterEventFrame = {
    frameType: "adapter.event",
    frameId: randomUUID(),
    protocolVersion: 1,
    event: {
      messageId: randomUUID(),
      schemaVersion: "1.0",
      messageType: "event",
      topic: FLIGHT_SEQUENCE_INTENT_CAPABILITY,
      sourceNodeId: sourceNode.nodeId,
      sourceCapability: FLIGHT_SEQUENCE_INTENT_CAPABILITY,
      siteId: config.siteId,
      roomId: config.roomId,
      sessionId: config.fabricSessionId,
      timestamp: intent.createdAt,
      monotonicTimestamp: Date.now(),
      sequence: outbox.nextNodeSequence(sourceNode.nodeId),
      correlationId: intent.intentId,
      causationId: intent.agentMeshCommandId,
      confidence: 1,
      ttlMs: 5_000,
      dataClassification: "operational",
      payload: {
        intent: "start",
        inputModality: "voice",
        deviceKind: intent.deviceKind,
      },
    },
    sentAt: new Date().toISOString(),
  };
  assertValid("AdapterEventFrame", frame);
  return frame;
};

export const completionEventFrame = (
  completion: AgentMeshCompletion,
  sourceNode: IntegrationNode,
  config: BridgeConfig,
  outbox: BridgeOutbox,
): AdapterEventFrame => {
  const sequence = outbox.nextNodeSequence(sourceNode.nodeId);
  const frame: AdapterEventFrame = {
    frameType: "adapter.event",
    frameId: randomUUID(),
    protocolVersion: 1,
    event: {
      messageId: completion.notificationId,
      schemaVersion: "1.0",
      messageType: "event",
      topic: AGENT_OUTPUT_CAPABILITY,
      sourceNodeId: sourceNode.nodeId,
      sourceCapability: AGENT_OUTPUT_CAPABILITY,
      siteId: config.siteId,
      roomId: config.roomId,
      sessionId: config.fabricSessionId,
      timestamp: completion.createdAt,
      monotonicTimestamp: Date.now(),
      sequence,
      correlationId:
        outbox.latestCorrelationForTarget(sourceNode.nodeId) ??
        completion.notificationId,
      confidence: 1,
      ttlMs: 300_000,
      dataClassification: "source_code",
      payload: {
        outcome: completion.outcome,
        title: completion.title,
        displayText: completion.displayText,
        speechText: completion.speechText,
        agent: completion.agent,
        agentMeshSessionId: completion.sessionId,
        workspaceName: completion.workspaceName,
      },
    },
    sentAt: new Date().toISOString(),
  };
  assertValid("AdapterEventFrame", frame);
  return frame;
};

export const healthReports = (
  mapping: AgentMeshFabricMapping,
  reportedAt = new Date().toISOString(),
): [HealthReport, ...HealthReport[]] =>
  mapping.nodes.map((node) => ({
    schemaVersion: "1.0",
    nodeId: node.nodeId,
    reportedAt,
    connectionState: node.connectionState,
    healthState: node.healthState,
    metrics: {},
  })) as [HealthReport, ...HealthReport[]];

const wearableNode = (
  wearable: AgentMeshWearable,
  config: BridgeConfig,
  generatedAt: string,
): IntegrationNode => {
  const promptEnabled = wearable.scopes.includes("prompt");
  const controlEnabled = wearable.scopes.includes("control");
  const wearableProfile =
    wearable.kind === "even_g2"
      ? {
          model: "even-realities-g2",
          productFamily: "Even Realities G2",
          fabricProfile: "even-g2",
          mediaCompanionSupported: false,
        }
      : {
          model: "meta-rayban",
          productFamily: "Meta Ray-Ban",
          fabricProfile: "meta-rayban",
          mediaCompanionSupported: true,
        };
  const credentialActive = wearable.status === "active";
  const lastUseAgeMs =
    wearable.lastUsedAt === undefined
      ? Number.POSITIVE_INFINITY
      : Date.parse(generatedAt) - Date.parse(wearable.lastUsedAt);
  const recentlyConnected =
    credentialActive &&
    lastUseAgeMs >= -MAX_FUTURE_LAST_USE_SKEW_MS &&
    lastUseAgeMs <= WEARABLE_CONNECTION_WINDOW_MS;
  return {
    schemaVersion: "1.0",
    nodeId: stableIdentifier("agentmesh-wearable", wearable.deviceId),
    pluginId: AGENT_MESH_PLUGIN_ID,
    pluginVersion: VERSION,
    runtimeVersion: RUNTIME_VERSION,
    hostId: config.hostId,
    siteId: config.siteId,
    roomId: config.roomId,
    displayName: boundedDisplayName(wearable.displayName),
    connectionState: recentlyConnected
      ? "connected"
      : credentialActive
        ? "disconnected"
        : "unavailable",
    healthState: recentlyConnected
      ? "healthy"
      : credentialActive
        ? "degraded"
        : "unhealthy",
    physical: true,
    simulated: false,
    publishedCapabilities: [
      ...(promptEnabled ? [intentCapability] : []),
      ...(controlEnabled
        ? [flightSequenceIntentCapability, deviceControlIntentCapability]
        : []),
    ],
    consumedCapabilities: promptEnabled ? [displayCapability] : [],
    configurationSchema: {},
    safetyClassification: "informational",
    dataClassifications: promptEnabled
      ? ["voice_transcript", "student", "operational"]
      : ["operational"],
    simulatorAvailable: false,
    requiredPermissions: [
      ...(promptEnabled || controlEnabled ? ["microphone"] : []),
      ...(promptEnabled ? ["display"] : []),
    ],
    lastSeenAt: wearable.lastUsedAt ?? generatedAt,
    metadata: {
      agentMeshDeviceId: wearable.deviceId,
      deviceKind: wearable.kind,
      agentMeshScopes: wearable.scopes.join(","),
      applicationProfile: controlEnabled
        ? "physical_controls"
        : "coding_agents",
      ...wearableProfile,
      compatibilityMode: true,
    },
  };
};

const companionInputNode = (
  companion: AgentMeshCompanionInput,
  config: BridgeConfig,
  generatedAt: string,
): IntegrationNode => {
  const lastUseAgeMs =
    Date.parse(generatedAt) - Date.parse(companion.lastUsedAt);
  const recentlyConnected =
    companion.status === "active" &&
    lastUseAgeMs >= -MAX_FUTURE_LAST_USE_SKEW_MS &&
    lastUseAgeMs <= WEARABLE_CONNECTION_WINDOW_MS;
  return {
    schemaVersion: "1.0",
    nodeId: stableIdentifier(
      "agentmesh-input-even-r1",
      companion.parentDeviceId,
    ),
    pluginId: AGENT_MESH_PLUGIN_ID,
    pluginVersion: VERSION,
    runtimeVersion: RUNTIME_VERSION,
    hostId: config.hostId,
    siteId: config.siteId,
    roomId: config.roomId,
    displayName: boundedDisplayName(companion.displayName),
    connectionState: recentlyConnected
      ? "connected"
      : companion.status === "active"
        ? "disconnected"
        : "unavailable",
    healthState: recentlyConnected
      ? "healthy"
      : companion.status === "active"
        ? "degraded"
        : "unhealthy",
    physical: true,
    simulated: false,
    publishedCapabilities: [
      ringGestureCapability,
      flightSequenceIntentCapability,
    ],
    consumedCapabilities: [],
    configurationSchema: {},
    safetyClassification: "informational",
    dataClassifications: ["operational"],
    simulatorAvailable: false,
    requiredPermissions: ["bluetooth"],
    lastSeenAt: companion.lastUsedAt,
    metadata: {
      agentMeshParentDeviceId: companion.parentDeviceId,
      deviceKind: companion.kind,
      model: "even-realities-r1",
      productFamily: "Even Realities R1",
      fabricProfile: "even-r1",
      inputOnly: true,
      companionTransport: "even-app-g2",
    },
  };
};

const agentNode = (
  session: AgentMeshSession,
  config: BridgeConfig,
  generatedAt: string,
): IntegrationNode => {
  const controllable =
    session.controlStatus === "managed" || session.controlStatus === "observed";
  const stoppedAge =
    Date.parse(generatedAt) - Date.parse(session.lastActivityAt);
  const recentlyExitedObserved =
    session.controlStatus === "observed" &&
    session.state === "stopped" &&
    Number.isFinite(stoppedAge) &&
    stoppedAge >= -MAX_FUTURE_LAST_USE_SKEW_MS &&
    stoppedAge <= RECENTLY_EXITED_OBSERVED_MS;
  const disconnected =
    session.controlStatus === "disconnected" ||
    (UNAVAILABLE_AGENT_STATES.has(session.state) && !recentlyExitedObserved);
  const connectionState = disconnected
    ? "disconnected"
    : session.controlStatus === "unsupported"
      ? "unavailable"
      : recentlyExitedObserved
        ? "degraded"
        : "connected";
  const healthState = disconnected
    ? "unhealthy"
    : session.controlStatus === "managed"
      ? "healthy"
      : "degraded";
  return {
    schemaVersion: "1.0",
    nodeId: stableIdentifier("agentmesh-agent", session.sessionId),
    pluginId: AGENT_MESH_PLUGIN_ID,
    pluginVersion: VERSION,
    runtimeVersion: RUNTIME_VERSION,
    hostId: config.hostId,
    siteId: config.siteId,
    roomId: config.roomId,
    displayName: boundedDisplayName(`${session.agent} · ${session.nodeName}`),
    connectionState,
    healthState,
    physical: false,
    simulated: false,
    publishedCapabilities: [outputCapability],
    consumedCapabilities: controllable ? [promptCapability] : [],
    configurationSchema: {},
    safetyClassification: "none",
    dataClassifications: ["source_code", "operational"],
    simulatorAvailable: false,
    requiredPermissions: ["workspace.scoped"],
    lastSeenAt: session.lastActivityAt || generatedAt,
    metadata: {
      agentMeshSessionId: session.sessionId,
      agent: session.agent,
      agentMeshNodeId: session.nodeId,
      workspaceId: session.workspaceId,
      workspaceName: session.workspaceName,
      controlStatus: session.controlStatus,
      agentMeshState: session.state,
      agentMeshLastActivityAt: session.lastActivityAt,
    },
  };
};

const stableIdentifier = (prefix: string, source: string): string => {
  const safe = source
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/gu, "-")
    .replace(/^-+|-+$/gu, "");
  const candidate = `${prefix}-${safe || "node"}`;
  if (candidate.length <= 128) return candidate;
  const digest = createHash("sha256").update(source).digest("hex").slice(0, 16);
  return `${candidate.slice(0, 111)}-${digest}`;
};

const boundedDisplayName = (value: string): string =>
  value.trim().slice(0, 128) || "Agent Mesh";

const assertValid = (
  definition: ProtocolDefinitionName,
  value: unknown,
): void => {
  const result = validateDefinition(definition, value);
  if (!result.valid) {
    throw new TypeError(`Invalid ${definition}: ${result.errors.join("; ")}`);
  }
};
