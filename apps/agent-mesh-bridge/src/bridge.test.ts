import { randomUUID } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import type { AdapterClientFrame, AdapterServerFrame } from "@citxr/protocol";
import { afterEach, describe, expect, it } from "vitest";

import {
  CitAgentMeshBridge,
  type AgentMeshBridgeSource,
  type BridgeSocket,
} from "./bridge.js";
import type { BridgeConfig } from "./config.js";
import { BridgeOutbox } from "./outbox.js";

const roots: string[] = [];
afterEach(() => {
  for (const root of roots.splice(0))
    rmSync(root, { recursive: true, force: true });
});

class FakeSocket implements BridgeSocket {
  readyState = 0;
  readonly sent: AdapterClientFrame[] = [];
  readonly #listeners = new Map<string, Set<(event: unknown) => void>>();
  readonly #agentNodeId = "agentmesh-agent-codex-a";

  constructor() {
    queueMicrotask(() => {
      this.readyState = 1;
      this.#emit("open", {});
    });
  }

  send(data: string): void {
    const frame = JSON.parse(data) as AdapterClientFrame;
    this.sent.push(frame);
    if (frame.frameType === "adapter.authenticate") {
      this.#server({
        frameType: "adapter.welcome",
        frameId: randomUUID(),
        protocolVersion: 1,
        runtimeId: "cit-runtime-local",
        heartbeatIntervalMs: 100,
        sentAt: new Date().toISOString(),
      });
    } else if (frame.frameType === "adapter.register") {
      this.#server({
        frameType: "adapter.registered",
        frameId: randomUUID(),
        protocolVersion: 1,
        registeredNodeIds: frame.nodes.map((node) => node.nodeId) as [
          string,
          ...string[],
        ],
        sentAt: new Date().toISOString(),
      });
    } else if (frame.frameType === "adapter.event") {
      if (frame.event.topic === "interaction.intent.agent_prompt") {
        this.#server({
          frameType: "adapter.command",
          frameId: randomUUID(),
          protocolVersion: 1,
          command: {
            commandId: randomUUID(),
            requestMessageId: randomUUID(),
            schemaVersion: "1.0",
            sessionId: "lesson-session-a",
            targetNodeId: this.#agentNodeId,
            action: "agent.prompt.submit",
            parameters: { prompt: frame.event.payload.text },
            priority: "student_interaction",
            idempotencyKey: randomUUID(),
            requestedAt: new Date().toISOString(),
            expiresAt: new Date(Date.now() + 30_000).toISOString(),
            safetyProfile: "agent-session",
            correlationId: frame.event.correlationId ?? frame.event.messageId,
            causationId: frame.event.messageId,
          },
          sentAt: new Date().toISOString(),
        });
      }
      this.#ack(frame.frameId);
    } else if (frame.frameType === "adapter.command_lifecycle") {
      this.#ack(frame.frameId);
    } else if (frame.frameType === "adapter.heartbeat") {
      this.#ack(frame.frameId);
    }
  }

  close(): void {
    this.readyState = 3;
    this.#emit("close", {});
  }

  addEventListener(type: string, listener: (event: unknown) => void): void {
    const listeners = this.#listeners.get(type) ?? new Set();
    listeners.add(listener);
    this.#listeners.set(type, listeners);
  }

  removeEventListener(type: string, listener: (event: unknown) => void): void {
    this.#listeners.get(type)?.delete(listener);
  }

  #ack(frameId: string): void {
    this.#server({
      frameType: "adapter.ack",
      frameId: randomUUID(),
      protocolVersion: 1,
      acknowledgedFrameId: frameId,
      status: "accepted",
      sentAt: new Date().toISOString(),
    });
  }

  #server(frame: AdapterServerFrame): void {
    queueMicrotask(() =>
      this.#emit("message", { data: JSON.stringify(frame) }),
    );
  }

  #emit(type: string, event: unknown): void {
    for (const listener of this.#listeners.get(type) ?? []) listener(event);
  }
}

describe("Agent Mesh bridge transport", () => {
  it("authenticates, registers, durably mirrors, and reports no-duplicate completion", async () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-transport-"));
    roots.push(root);
    const databasePath = path.join(root, "bridge.sqlite3");
    const config: BridgeConfig = {
      fabricAdapterUrl: "ws://127.0.0.1:8765/api/v1/adapters/connect",
      fabricCredential: "cit-adapter-" + "a".repeat(40),
      fabricApiUrl: "http://127.0.0.1:8765",
      fabricReadCredential: "cit-reader-" + "c".repeat(40),
      fabricSessionId: "lesson-session-a",
      projectFabricControls: true,
      agentMeshBaseUrl: "http://127.0.0.1:7342",
      agentMeshDeviceToken: "device_" + "b".repeat(43),
      databasePath,
      siteId: "local-site",
      roomId: "local-room",
      hostId: "agent-mesh-bridge-local",
      pollIntervalMs: 10,
      reconnectDelayMs: 10,
    };
    let delivered = false;
    let unrelatedCompletionDelivered = false;
    let ringDelivered = false;
    let acknowledged = 0;
    let ringAcknowledged = 0;
    const source: AgentMeshBridgeSource = {
      async discovery() {
        return {
          generatedAt: new Date().toISOString(),
          wearables: [
            {
              deviceId: "g2-a",
              displayName: "G2",
              kind: "even_g2",
              scopes: ["read", "prompt", "control"],
              status: "active",
              lastUsedAt: new Date().toISOString(),
            },
          ],
          companionInputs: [
            {
              parentDeviceId: "g2-a",
              displayName: "G2 · Even R1",
              kind: "even_r1",
              status: "active",
              lastUsedAt: new Date().toISOString(),
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
        };
      },
      async interactions(afterSequence) {
        if (ringDelivered || afterSequence > 0) {
          return { interactions: [], nextCursor: afterSequence };
        }
        ringDelivered = true;
        return {
          interactions: [
            {
              interactionId: randomUUID(),
              sequence: 1,
              deviceId: "g2-a",
              deviceKind: "even_g2",
              deviceDisplayName: "G2",
              source: "even_r1",
              gesture: "double_tap",
              createdAt: new Date().toISOString(),
            },
            {
              interactionId: randomUUID(),
              sequence: 2,
              deviceId: "g2-a",
              deviceKind: "even_g2",
              deviceDisplayName: "G2",
              source: "device_control",
              action: "left",
              target: "ground_outputs",
              confirmed: true,
              createdAt: new Date().toISOString(),
            },
          ],
          nextCursor: 2,
        };
      },
      async acknowledgeInteraction() {
        ringAcknowledged += 1;
      },
      async intents(afterSequence) {
        if (delivered || afterSequence > 0)
          return { intents: [], nextCursor: afterSequence };
        delivered = true;
        return {
          intents: [
            {
              intentId: randomUUID(),
              sequence: 1,
              deviceId: "g2-a",
              deviceKind: "even_g2",
              deviceDisplayName: "G2",
              requestedSessionId: "codex-a",
              dispatchedSessionId: "codex-a",
              agentMeshCommandId: randomUUID(),
              prompt: "Run tests.",
              route: "managed",
              createdAt: new Date().toISOString(),
              alreadyDispatched: true,
            },
          ],
          nextCursor: 1,
        };
      },
      async acknowledgeIntent() {
        acknowledged += 1;
      },
      async completions(afterSequence) {
        if (unrelatedCompletionDelivered || afterSequence > 0) {
          return { notifications: [], nextCursor: afterSequence };
        }
        unrelatedCompletionDelivered = true;
        return {
          notifications: [
            {
              notificationId: randomUUID(),
              sequence: 1,
              sessionId: "codex-a",
              agent: "codex",
              nodeId: "desktop-a",
              nodeName: "Desktop",
              workspaceName: "Workspace",
              outcome: "completed",
              title: "Unrouted completion",
              displayText: "This completion predates the Fabric route.",
              speechText: "Unrouted completion.",
              createdAt: new Date().toISOString(),
            },
          ],
          nextCursor: 1,
        };
      },
    };
    const socket = new FakeSocket();
    const outbox = new BridgeOutbox(databasePath);
    const controller = new AbortController();
    try {
      const bridge = new CitAgentMeshBridge(
        config,
        source,
        outbox,
        () => socket,
      );
      const running = bridge.runOnce(controller.signal);
      await waitUntil(
        () =>
          acknowledged === 1 &&
          ringAcknowledged === 2 &&
          socket.sent.filter(
            (frame) =>
              frame.frameType === "adapter.command_lifecycle" &&
              frame.lifecycle.stage === "SUCCEEDED",
          ).length === 1,
      );
      controller.abort();
      await expect(running).resolves.toBe("aborted");
      expect(outbox.pendingEvents()).toEqual([]);
      expect(outbox.pendingLifecycles()).toEqual([]);
      expect(
        socket.sent.filter((frame) => frame.frameType === "adapter.event"),
      ).toHaveLength(4);
      expect(
        socket.sent.flatMap((frame) =>
          frame.frameType === "adapter.event" ? [frame.event.topic] : [],
        ),
      ).toEqual(
        expect.arrayContaining([
          "interaction.gesture.smart_ring",
          "interaction.intent.flight_sequence_start",
          "interaction.intent.device_control",
          "interaction.intent.agent_prompt",
        ]),
      );
      expect(outbox.stateNumber("agent-mesh-completion-cursor")).toBe(1);
    } finally {
      controller.abort();
      outbox.close();
    }
  });
});

const waitUntil = async (condition: () => boolean): Promise<void> => {
  const deadline = Date.now() + 2_000;
  while (!condition()) {
    if (Date.now() >= deadline)
      throw new Error("Timed out waiting for bridge fixture");
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
};
