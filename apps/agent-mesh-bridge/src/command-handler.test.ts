import { randomUUID } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import type { AdapterCommandFrame } from "@citxr/protocol";
import { afterEach, describe, expect, it } from "vitest";

import { MirrorCommandHandler } from "./command-handler.js";
import type { BridgeConfig } from "./config.js";
import {
  AGENT_PROMPT_CAPABILITY,
  intentEventFrame,
  mapDiscovery,
  semanticSha256,
} from "./mapping.js";
import { BridgeOutbox } from "./outbox.js";

const roots: string[] = [];
afterEach(() => {
  for (const root of roots.splice(0))
    rmSync(root, { recursive: true, force: true });
});

const commandFrame = (
  targetNodeId: string,
  causationId: string,
  prompt = "Run tests.",
): AdapterCommandFrame => {
  const now = new Date();
  return {
    frameType: "adapter.command",
    frameId: randomUUID(),
    protocolVersion: 1,
    command: {
      commandId: randomUUID(),
      requestMessageId: randomUUID(),
      schemaVersion: "1.0",
      sessionId: "lesson-session-a",
      targetNodeId,
      action: AGENT_PROMPT_CAPABILITY,
      parameters: { prompt },
      priority: "student_interaction",
      idempotencyKey: randomUUID(),
      requestedAt: now.toISOString(),
      expiresAt: new Date(now.getTime() + 30_000).toISOString(),
      safetyProfile: "agent-session",
      correlationId: randomUUID(),
      causationId,
    },
    sentAt: now.toISOString(),
  };
};

describe("Agent Mesh compatibility command handling", () => {
  it("acknowledges a mirrored prompt without dispatching it a second time", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-command-"));
    roots.push(root);
    const databasePath = path.join(root, "bridge.sqlite3");
    const config: BridgeConfig = {
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
    };
    const outbox = new BridgeOutbox(databasePath);
    try {
      const mapping = mapDiscovery(
        {
          generatedAt: new Date().toISOString(),
          wearables: [
            {
              deviceId: "g2-a",
              displayName: "G2 A",
              kind: "even_g2",
              scopes: ["read", "prompt"],
              status: "active",
            },
          ],
          sessions: [
            {
              sessionId: "codex-a",
              agent: "codex",
              nodeId: "desktop-a",
              nodeName: "Desktop A",
              workspaceId: "workspace-a",
              workspaceName: "Workspace A",
              state: "idle",
              controlStatus: "managed",
              headline: "Ready",
              lastActivityAt: new Date().toISOString(),
            },
          ],
        },
        config,
      );
      const wearable = mapping.wearableNodeByDeviceId.get("g2-a");
      const agent = mapping.agentNodeBySessionId.get("codex-a");
      if (wearable === undefined || agent === undefined)
        throw new Error("Missing fixture nodes");
      const source = intentEventFrame(
        {
          intentId: randomUUID(),
          sequence: 1,
          deviceId: "g2-a",
          deviceKind: "even_g2",
          deviceDisplayName: "G2 A",
          requestedSessionId: "codex-a",
          dispatchedSessionId: "codex-a",
          agentMeshCommandId: randomUUID(),
          prompt: "Run tests.",
          route: "managed",
          createdAt: new Date().toISOString(),
          alreadyDispatched: true,
        },
        wearable,
        config,
        outbox,
      );
      outbox.enqueueEvent("intent:1", source, {
        kind: "intent",
        agentMeshSessionId: "codex-a",
        agentMeshDispatchedSessionId: "codex-a",
        agentMeshCommandId: source.event.causationId ?? "missing-command-id",
        alreadyDispatched: true,
        legacyDisplayDelivered: false,
        semanticSha256: semanticSha256("Run tests."),
      });
      const handler = new MirrorCommandHandler(outbox);
      const command = commandFrame(agent.nodeId, source.event.messageId);

      expect(
        handler.handle(command, mapping).map((item) => item.lifecycle.stage),
      ).toEqual(["ACCEPTED", "SUCCEEDED"]);
      expect(outbox.agentRoute("codex-a")).toMatchObject({
        targetNodeId: agent.nodeId,
        correlationId: command.command.correlationId,
      });
      expect(handler.handle(command, mapping)).toEqual([]);
    } finally {
      outbox.close();
    }
  });

  it("rejects altered or retargeted mirrored prompts", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-command-"));
    roots.push(root);
    const databasePath = path.join(root, "bridge.sqlite3");
    const config: BridgeConfig = {
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
    };
    const outbox = new BridgeOutbox(databasePath);
    try {
      const mapping = mapDiscovery(
        {
          generatedAt: new Date().toISOString(),
          wearables: [
            {
              deviceId: "g2-a",
              displayName: "G2",
              kind: "even_g2",
              scopes: ["read", "prompt"],
              status: "active",
            },
          ],
          sessions: [
            {
              sessionId: "codex-a",
              agent: "codex",
              nodeId: "desktop-a",
              nodeName: "Desktop",
              workspaceId: "workspace-a",
              workspaceName: "Workspace",
              state: "idle",
              controlStatus: "managed",
              headline: "Ready",
              lastActivityAt: new Date().toISOString(),
            },
          ],
        },
        config,
      );
      const agent = mapping.agentNodeBySessionId.get("codex-a");
      if (agent === undefined) throw new Error("Missing fixture node");
      const causationId = randomUUID();
      const fakeEvent = intentEventFrame(
        {
          intentId: causationId,
          sequence: 1,
          deviceId: "g2-a",
          deviceKind: "even_g2",
          deviceDisplayName: "G2",
          requestedSessionId: "codex-a",
          dispatchedSessionId: "codex-a",
          agentMeshCommandId: randomUUID(),
          prompt: "Original",
          route: "managed",
          createdAt: new Date().toISOString(),
          alreadyDispatched: true,
        },
        mapping.wearableNodeByDeviceId.get("g2-a")!,
        config,
        outbox,
      );
      outbox.enqueueEvent("intent:altered", fakeEvent, {
        kind: "intent",
        agentMeshSessionId: "codex-a",
        agentMeshDispatchedSessionId: "codex-a",
        alreadyDispatched: true,
        legacyDisplayDelivered: false,
        semanticSha256: semanticSha256("Original"),
      });
      const result = new MirrorCommandHandler(outbox).handle(
        commandFrame(agent.nodeId, causationId, "Altered"),
        mapping,
      );
      expect(result.at(-1)?.lifecycle).toMatchObject({
        stage: "REJECTED",
        code: "MIRROR_PAYLOAD_MISMATCH",
      });
    } finally {
      outbox.close();
    }
  });
});
