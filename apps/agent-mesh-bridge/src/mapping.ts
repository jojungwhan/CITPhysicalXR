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
  AgentMeshDiscovery,
  AgentMeshIntent,
  AgentMeshSession,
  AgentMeshWearable,
} from "./types.js";

type ProtocolDefinitionName = Parameters<typeof validateDefinition>[0];

export const AGENT_MESH_PLUGIN_ID = "cit.agent-mesh-bridge";
export const INTENT_CAPABILITY = "interaction.intent.agent_prompt";
export const FLIGHT_SEQUENCE_INTENT_CAPABILITY =
  "interaction.intent.flight_sequence_start";
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
    exactPhrasesOnly: true,
    rawTranscriptExcluded: true,
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
  readonly agentNodeBySessionId: ReadonlyMap<string, IntegrationNode>;
  readonly agentSessionByNodeId: ReadonlyMap<string, AgentMeshSession>;
}

export const mapDiscovery = (
  discovery: AgentMeshDiscovery,
  config: BridgeConfig,
): AgentMeshFabricMapping => {
  const wearableNodeByDeviceId = new Map<string, IntegrationNode>();
  const agentNodeBySessionId = new Map<string, IntegrationNode>();
  const agentSessionByNodeId = new Map<string, AgentMeshSession>();
  for (const wearable of discovery.wearables) {
    const node = wearableNode(wearable, config, discovery.generatedAt);
    wearableNodeByDeviceId.set(wearable.deviceId, node);
  }
  if (wearableNodeByDeviceId.size > MAX_ADAPTER_NODES) {
    throw new TypeError("Agent Mesh discovery exceeds the wearable-node limit");
  }
  const agentCapacity = MAX_ADAPTER_NODES - wearableNodeByDeviceId.size;
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
    agentNodeBySessionId,
    agentSessionByNodeId,
  };
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
    publishedCapabilities: [intentCapability, flightSequenceIntentCapability],
    consumedCapabilities: [displayCapability],
    configurationSchema: {},
    safetyClassification: "informational",
    dataClassifications: ["voice_transcript", "student", "operational"],
    simulatorAvailable: false,
    requiredPermissions: ["microphone", "display"],
    lastSeenAt: wearable.lastUsedAt ?? generatedAt,
    metadata: {
      agentMeshDeviceId: wearable.deviceId,
      deviceKind: wearable.kind,
      ...wearableProfile,
      compatibilityMode: true,
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
