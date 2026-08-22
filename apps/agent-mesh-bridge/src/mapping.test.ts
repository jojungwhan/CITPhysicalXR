import { mkdtempSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { validateDefinition } from "@citxr/protocol";
import { afterEach, describe, expect, it } from "vitest";

import type { BridgeConfig } from "./config.js";
import {
  AGENT_OUTPUT_CAPABILITY,
  AGENT_PROMPT_CAPABILITY,
  DISPLAY_CAPABILITY,
  INTENT_CAPABILITY,
  completionEventFrame,
  intentEventFrame,
  mapDiscovery,
} from "./mapping.js";
import { BridgeOutbox } from "./outbox.js";
import type {
  AgentMeshDiscovery,
  AgentMeshSession,
  AgentMeshWearable,
} from "./types.js";

const roots: string[] = [];
afterEach(() => {
  for (const root of roots.splice(0))
    rmSync(root, { recursive: true, force: true });
});

const config = (databasePath: string): BridgeConfig => ({
  fabricAdapterUrl: "ws://127.0.0.1:8765/api/v1/adapters/connect",
  fabricCredential: "cit-adapter-" + "a".repeat(40),
  fabricSessionId: "lesson-session-a",
  agentMeshBaseUrl: "http://127.0.0.1:7342",
  agentMeshDeviceToken: "device_" + "b".repeat(43),
  databasePath,
  siteId: "local-site",
  roomId: "local-room",
  hostId: "agent-mesh-bridge-local",
  pollIntervalMs: 2_000,
  reconnectDelayMs: 2_000,
});

const classG2: AgentMeshWearable = {
  deviceId: "class-g2",
  displayName: "Class G2",
  kind: "even_g2",
  status: "active",
  lastUsedAt: "2026-08-21T02:59:00.000Z",
};

const managedCodex: AgentMeshSession = {
  sessionId: "managed-codex",
  agent: "codex",
  nodeId: "desktop-a",
  nodeName: "Desktop A",
  workspaceId: "course-workspace",
  workspaceName: "Course Workspace",
  state: "idle",
  controlStatus: "managed",
  headline: "Ready",
  lastActivityAt: "2026-08-21T02:58:00.000Z",
};

const discovery: AgentMeshDiscovery = {
  generatedAt: "2026-08-21T03:00:00.000Z",
  wearables: [classG2],
  sessions: [managedCodex],
};

describe("Agent Mesh canonical mapping", () => {
  it("advertises stable, transport-neutral nodes and capabilities", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-map-"));
    roots.push(root);
    const mapping = mapDiscovery(
      discovery,
      config(path.join(root, "bridge.sqlite3")),
    );

    expect(validateDefinition("PluginManifest", mapping.manifest).valid).toBe(
      true,
    );
    expect(mapping.nodes).toHaveLength(2);
    expect(mapping.wearableNodeByDeviceId.get("class-g2")).toMatchObject({
      nodeId: "agentmesh-wearable-class-g2",
      physical: true,
      publishedCapabilities: [{ name: INTENT_CAPABILITY }],
      consumedCapabilities: [{ name: DISPLAY_CAPABILITY }],
    });
    expect(mapping.agentNodeBySessionId.get("managed-codex")).toMatchObject({
      nodeId: "agentmesh-agent-managed-codex",
      consumedCapabilities: [{ name: AGENT_PROMPT_CAPABILITY }],
      publishedCapabilities: [{ name: AGENT_OUTPUT_CAPABILITY }],
    });
  });

  it("advertises the safe continuation path for an observed local CLI", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-map-"));
    roots.push(root);
    const observedSession: AgentMeshSession = {
      ...managedCodex,
      sessionId: "observed-codex",
      controlStatus: "observed" as const,
    };
    const mapping = mapDiscovery(
      { ...discovery, sessions: [observedSession] },
      config(path.join(root, "bridge.sqlite3")),
    );

    expect(mapping.agentNodeBySessionId.get("observed-codex")).toMatchObject({
      connectionState: "connected",
      healthState: "degraded",
      publishedCapabilities: [{ name: AGENT_OUTPUT_CAPABILITY }],
      consumedCapabilities: [{ name: AGENT_PROMPT_CAPABILITY }],
      metadata: {
        controlStatus: "observed",
        agentMeshLastActivityAt: observedSession.lastActivityAt,
      },
    });
  });

  it("does not project a historical managed session as connected", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-map-"));
    roots.push(root);
    const mapping = mapDiscovery(
      {
        ...discovery,
        sessions: [{ ...managedCodex, state: "disconnected" }],
      },
      config(path.join(root, "bridge.sqlite3")),
    );

    expect(mapping.agentNodeBySessionId.get("managed-codex")).toMatchObject({
      connectionState: "disconnected",
      healthState: "unhealthy",
      consumedCapabilities: [{ name: AGENT_PROMPT_CAPABILITY }],
    });
  });

  it("does not advertise a stale wearable credential as connected hardware", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-map-"));
    roots.push(root);
    const mapping = mapDiscovery(
      {
        ...discovery,
        wearables: [
          {
            ...classG2,
            lastUsedAt: "2026-08-21T02:55:00.000Z",
          },
        ],
      },
      config(path.join(root, "bridge.sqlite3")),
    );

    expect(mapping.wearableNodeByDeviceId.get("class-g2")).toMatchObject({
      connectionState: "disconnected",
      healthState: "degraded",
      physical: true,
      publishedCapabilities: [{ name: INTENT_CAPABILITY }],
      consumedCapabilities: [{ name: DISPLAY_CAPABILITY }],
    });
  });

  it("keeps an inactive wearable discoverable without making it bindable", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-map-"));
    roots.push(root);
    const mapping = mapDiscovery(
      {
        ...discovery,
        wearables: [
          {
            deviceId: "retired-g2",
            displayName: "Retired G2",
            kind: "even_g2",
            status: "revoked",
          },
        ],
      },
      config(path.join(root, "bridge.sqlite3")),
    );

    expect(mapping.wearableNodeByDeviceId.get("retired-g2")).toMatchObject({
      connectionState: "unavailable",
      healthState: "unhealthy",
      publishedCapabilities: [{ name: INTENT_CAPABILITY }],
      consumedCapabilities: [{ name: DISPLAY_CAPABILITY }],
    });
  });

  it("bounds a large discovery snapshot to the most recently active agent sessions", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-map-"));
    roots.push(root);
    const sessions = Array.from({ length: 100 }, (_, index) => ({
      ...managedCodex,
      sessionId: `managed-codex-${index.toString().padStart(3, "0")}`,
      lastActivityAt: new Date(
        Date.parse("2026-08-21T01:00:00.000Z") + index * 1_000,
      ).toISOString(),
    }));

    const mapping = mapDiscovery(
      { ...discovery, sessions },
      config(path.join(root, "bridge.sqlite3")),
    );

    expect(mapping.nodes).toHaveLength(64);
    expect(mapping.agentNodeBySessionId.size).toBe(63);
    expect(mapping.agentNodeBySessionId.has("managed-codex-099")).toBe(true);
    expect(mapping.agentNodeBySessionId.has("managed-codex-000")).toBe(false);
  });

  it("produces valid correlated intent and completion frames", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-map-"));
    roots.push(root);
    const bridgeConfig = config(path.join(root, "bridge.sqlite3"));
    const outbox = new BridgeOutbox(bridgeConfig.databasePath);
    try {
      const mapping = mapDiscovery(discovery, bridgeConfig);
      const wearable = mapping.wearableNodeByDeviceId.get("class-g2");
      const agent = mapping.agentNodeBySessionId.get("managed-codex");
      if (wearable === undefined || agent === undefined)
        throw new Error("Fixture mapping failed");
      const intent = intentEventFrame(
        {
          intentId: "e39d8ec7-97d6-4f2c-90af-01a2bd178677",
          sequence: 1,
          deviceId: "class-g2",
          deviceKind: "even_g2",
          deviceDisplayName: "Class G2",
          requestedSessionId: "managed-codex",
          dispatchedSessionId: "managed-codex",
          agentMeshCommandId: "b21a8bea-f174-4510-8f83-a969d192c71c",
          prompt: "Run the selected tests.",
          route: "managed",
          createdAt: "2026-08-21T03:00:01.000Z",
          alreadyDispatched: true,
        },
        wearable,
        bridgeConfig,
        outbox,
      );
      const completion = completionEventFrame(
        {
          notificationId: "2bf40e47-e733-42e1-96f7-acdb872d622c",
          sequence: 1,
          sessionId: "managed-codex",
          agent: "codex",
          nodeId: "desktop-a",
          nodeName: "Desktop A",
          workspaceName: "Course Workspace",
          outcome: "completed",
          title: "Codex finished",
          displayText: "All selected tests passed.",
          speechText: "Codex finished. All selected tests passed.",
          createdAt: "2026-08-21T03:01:00.000Z",
        },
        agent,
        bridgeConfig,
        outbox,
      );

      expect(validateDefinition("AdapterEventFrame", intent).valid).toBe(true);
      expect(intent.event.payload).toMatchObject({ alreadyDispatched: true });
      expect(validateDefinition("AdapterEventFrame", completion).valid).toBe(
        true,
      );
      expect(completion.event.sequence).toBe(1);
    } finally {
      outbox.close();
    }
  });
});
