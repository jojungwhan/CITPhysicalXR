import { mkdtempSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { validateDefinition } from "@citxr/protocol";
import { afterEach, describe, expect, it } from "vitest";

import type { BridgeConfig } from "./config.js";
import {
  AGENT_OUTPUT_CAPABILITY,
  AGENT_PROMPT_CAPABILITY,
  DEVICE_CONTROL_INTENT_CAPABILITY,
  DISPLAY_CAPABILITY,
  FLIGHT_SEQUENCE_INTENT_CAPABILITY,
  INTENT_CAPABILITY,
  RING_GESTURE_CAPABILITY,
  completionEventFrame,
  deviceControlEventFrame,
  flightSequenceIntentFrame,
  intentEventFrame,
  mapDiscovery,
  ringFlightSequenceIntentFrame,
  ringGestureEventFrame,
} from "./mapping.js";
import { BridgeOutbox } from "./outbox.js";
import type {
  AgentMeshDiscovery,
  AgentMeshInteraction,
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
  fabricApiUrl: "http://127.0.0.1:8765",
  fabricReadCredential: "cit-reader-" + "c".repeat(40),
  fabricSessionId: "lesson-session-a",
  projectFabricControls: false,
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
  scopes: ["read", "prompt"],
  status: "active",
  lastUsedAt: "2026-08-21T02:59:00.000Z",
};

const controlsG2: AgentMeshWearable = {
  ...classG2,
  deviceId: "class-g2-controls",
  displayName: "CIT controls · Class G2",
  scopes: ["read", "control"],
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
      metadata: {
        model: "even-realities-g2",
        productFamily: "Even Realities G2",
        fabricProfile: "even-g2",
        mediaCompanionSupported: false,
        applicationProfile: "coding_agents",
      },
    });
    expect(mapping.agentNodeBySessionId.get("managed-codex")).toMatchObject({
      nodeId: "agentmesh-agent-managed-codex",
      consumedCapabilities: [{ name: AGENT_PROMPT_CAPABILITY }],
      publishedCapabilities: [{ name: AGENT_OUTPUT_CAPABILITY }],
    });
  });

  it("keeps Even G2 and Meta Ray-Ban as distinct profiles on the shared bridge", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-map-"));
    roots.push(root);
    const mapping = mapDiscovery(
      {
        ...discovery,
        wearables: [
          classG2,
          {
            deviceId: "class-meta",
            displayName: "Class Meta",
            kind: "ray_ban",
            scopes: ["read", "prompt", "control"],
            status: "active",
            lastUsedAt: discovery.generatedAt,
          },
        ],
      },
      config(path.join(root, "bridge.sqlite3")),
    );

    expect(
      mapping.wearableNodeByDeviceId.get("class-g2")?.metadata,
    ).toMatchObject({
      model: "even-realities-g2",
      fabricProfile: "even-g2",
      mediaCompanionSupported: false,
    });
    expect(
      mapping.wearableNodeByDeviceId.get("class-meta")?.metadata,
    ).toMatchObject({
      model: "meta-rayban",
      fabricProfile: "meta-rayban",
      mediaCompanionSupported: true,
    });
    expect(mapping.manifest.pluginId).toBe("cit.agent-mesh-bridge");
  });

  it("registers Even R1 as a separate input-only node and derives only double-tap as a cue", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-map-"));
    roots.push(root);
    const databasePath = path.join(root, "bridge.sqlite3");
    const mapping = mapDiscovery(
      {
        ...discovery,
        wearables: [controlsG2],
        companionInputs: [
          {
            parentDeviceId: controlsG2.deviceId,
            displayName: "Class G2 · Even R1",
            kind: "even_r1",
            status: "active",
            lastUsedAt: discovery.generatedAt,
          },
        ],
      },
      config(databasePath),
    );
    const ringNode = mapping.companionNodeByParentDeviceId.get(
      controlsG2.deviceId,
    );
    expect(ringNode).toMatchObject({
      nodeId: "agentmesh-input-even-r1-class-g2-controls",
      connectionState: "connected",
      physical: true,
      publishedCapabilities: [
        { name: RING_GESTURE_CAPABILITY },
        { name: FLIGHT_SEQUENCE_INTENT_CAPABILITY },
      ],
      consumedCapabilities: [],
      metadata: {
        model: "even-realities-r1",
        inputOnly: true,
        agentMeshParentDeviceId: controlsG2.deviceId,
      },
    });
    if (ringNode === undefined) throw new Error("R1 node is missing");
    const outbox = new BridgeOutbox(databasePath);
    try {
      const interaction: AgentMeshInteraction = {
        interactionId: "6463013e-fe23-4ff7-babc-34239d88f1db",
        sequence: 1,
        deviceId: controlsG2.deviceId,
        deviceKind: "even_g2",
        deviceDisplayName: controlsG2.displayName,
        source: "even_r1",
        gesture: "double_tap",
        createdAt: discovery.generatedAt,
      };
      expect(
        validateDefinition(
          "AdapterEventFrame",
          ringGestureEventFrame(
            interaction,
            ringNode,
            config(databasePath),
            outbox,
          ),
        ).valid,
      ).toBe(true);
      expect(
        ringFlightSequenceIntentFrame(
          interaction,
          ringNode,
          config(databasePath),
          outbox,
        )?.event,
      ).toMatchObject({
        topic: FLIGHT_SEQUENCE_INTENT_CAPABILITY,
        sourceNodeId: ringNode.nodeId,
        payload: {
          intent: "start",
          inputModality: "smart_ring",
          gesture: "double_tap",
        },
      });
      expect(
        ringFlightSequenceIntentFrame(
          { ...interaction, gesture: "tap" },
          ringNode,
          config(databasePath),
          outbox,
        ),
      ).toBeUndefined();
    } finally {
      outbox.close();
    }
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
            scopes: ["read", "prompt"],
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

  it("projects confirmed G2 or Meta device control without a transcript", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-map-"));
    roots.push(root);
    const databasePath = path.join(root, "bridge.sqlite3");
    const bridgeConfig = config(databasePath);
    const mapping = mapDiscovery(
      { ...discovery, wearables: [controlsG2] },
      bridgeConfig,
    );
    const wearable = mapping.wearableNodeByDeviceId.get(controlsG2.deviceId);
    if (wearable === undefined) throw new Error("Fixture mapping failed");
    const outbox = new BridgeOutbox(databasePath);
    try {
      const frame = deviceControlEventFrame(
        {
          interactionId: "fe3d7f0e-cbea-4a45-888b-1af3a69f497c",
          sequence: 1,
          deviceId: controlsG2.deviceId,
          deviceKind: "even_g2",
          deviceDisplayName: controlsG2.displayName,
          source: "device_control",
          action: "left",
          target: "ground_outputs",
          batchId: "6299cc17-1a72-457f-823a-c511f33eff0b",
          confirmed: true,
          createdAt: discovery.generatedAt,
        },
        wearable,
        bridgeConfig,
        outbox,
      );

      expect(validateDefinition("AdapterEventFrame", frame).valid).toBe(true);
      expect(frame.event).toMatchObject({
        topic: DEVICE_CONTROL_INTENT_CAPABILITY,
        sourceNodeId: wearable.nodeId,
        correlationId: "6299cc17-1a72-457f-823a-c511f33eff0b",
        dataClassification: "operational",
        payload: {
          action: "left",
          target: "ground_outputs",
          batchId: "6299cc17-1a72-457f-823a-c511f33eff0b",
          confirmed: true,
          inputModality: "voice",
          deviceKind: "even_g2",
        },
      });
      expect(frame.event.payload).not.toHaveProperty("text");
      expect(frame.event.payload).not.toHaveProperty("transcript");

      const plugFrame = deviceControlEventFrame(
        {
          interactionId: "c414232b-d0c7-40b6-8868-207276350ed3",
          sequence: 2,
          deviceId: controlsG2.deviceId,
          deviceKind: "even_g2",
          deviceDisplayName: controlsG2.displayName,
          source: "device_control",
          action: "power_on",
          target: "assigned_output",
          targetRole: "power_output_1",
          confirmed: true,
          createdAt: discovery.generatedAt,
        },
        wearable,
        bridgeConfig,
        outbox,
      );
      expect(validateDefinition("AdapterEventFrame", plugFrame).valid).toBe(
        true,
      );
      expect(plugFrame.event.payload).toMatchObject({
        action: "power_on",
        target: "assigned_output",
        targetRole: "power_output_1",
        confirmed: true,
      });

      const activateAllFrame = deviceControlEventFrame(
        {
          interactionId: "34b33aa9-13bc-47bd-8401-913a7e1b78a3",
          sequence: 3,
          deviceId: controlsG2.deviceId,
          deviceKind: "even_g2",
          deviceDisplayName: controlsG2.displayName,
          source: "device_control",
          action: "activate",
          target: "all_outputs",
          confirmed: true,
          createdAt: discovery.generatedAt,
        },
        wearable,
        bridgeConfig,
        outbox,
      );
      expect(
        validateDefinition("AdapterEventFrame", activateAllFrame).valid,
      ).toBe(true);
      expect(activateAllFrame.event.payload).toMatchObject({
        action: "activate",
        target: "all_outputs",
        confirmed: true,
      });
    } finally {
      outbox.close();
    }
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

  it("never turns a CLI-only G2 prompt into a physical fleet command", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-map-"));
    roots.push(root);
    const bridgeConfig = config(path.join(root, "bridge.sqlite3"));
    const outbox = new BridgeOutbox(bridgeConfig.databasePath);
    try {
      const mapping = mapDiscovery(discovery, bridgeConfig);
      const wearable = mapping.wearableNodeByDeviceId.get("class-g2");
      if (wearable === undefined) throw new Error("Fixture mapping failed");
      const baseIntent = {
        intentId: "e39d8ec7-97d6-4f2c-90af-01a2bd178677",
        sequence: 1,
        deviceId: "class-g2",
        deviceKind: "even_g2" as const,
        deviceDisplayName: "Class G2",
        requestedSessionId: "managed-codex",
        dispatchedSessionId: "managed-codex",
        agentMeshCommandId: "b21a8bea-f174-4510-8f83-a969d192c71c",
        route: "managed" as const,
        createdAt: "2026-08-21T03:00:01.000Z",
        alreadyDispatched: true as const,
      };

      const frame = flightSequenceIntentFrame(
        { ...baseIntent, prompt: "Start drone sequence." },
        wearable,
        bridgeConfig,
        outbox,
      );

      expect(frame).toBeUndefined();
      const metaMapping = mapDiscovery(
        {
          ...discovery,
          wearables: [
            {
              ...classG2,
              deviceId: "class-meta",
              displayName: "Class Meta",
              kind: "ray_ban",
              scopes: ["read", "prompt", "control"],
            },
          ],
        },
        bridgeConfig,
      );
      const meta = metaMapping.wearableNodeByDeviceId.get("class-meta");
      if (meta === undefined) throw new Error("Meta fixture mapping failed");
      const metaFrame = flightSequenceIntentFrame(
        {
          ...baseIntent,
          intentId: "4a624174-7472-42bb-80e6-e286ab7ea350",
          deviceId: "class-meta",
          deviceKind: "ray_ban",
          deviceDisplayName: "Class Meta",
          prompt: "드론 순차 이륙",
        },
        meta,
        bridgeConfig,
        outbox,
      );
      expect(metaFrame?.event.payload).toEqual({
        intent: "start",
        inputModality: "voice",
        deviceKind: "ray_ban",
      });
      expect(
        flightSequenceIntentFrame(
          {
            ...baseIntent,
            prompt: "Could you inspect the drone sequence code?",
          },
          wearable,
          bridgeConfig,
          outbox,
        ),
      ).toBeUndefined();
    } finally {
      outbox.close();
    }
  });
});
