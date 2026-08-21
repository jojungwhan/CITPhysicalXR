import { randomUUID } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import type {
  AdapterCommandLifecycleFrame,
  AdapterEventFrame,
} from "@citxr/protocol";
import { afterEach, describe, expect, it } from "vitest";

import { BridgeOutbox } from "./outbox.js";

const roots: string[] = [];

afterEach(() => {
  for (const root of roots.splice(0))
    rmSync(root, { recursive: true, force: true });
});

const eventFrame = (nodeId: string, sequence: number): AdapterEventFrame => ({
  frameType: "adapter.event",
  frameId: randomUUID(),
  protocolVersion: 1,
  event: {
    messageId: randomUUID(),
    schemaVersion: "1.0",
    messageType: "event",
    topic: "interaction.intent.agent_prompt",
    sourceNodeId: nodeId,
    sourceCapability: "interaction.intent.agent_prompt",
    siteId: "local-site",
    roomId: "local-room",
    sessionId: "lesson-session-a",
    timestamp: new Date().toISOString(),
    monotonicTimestamp: sequence,
    sequence,
    correlationId: randomUUID(),
    confidence: 1,
    ttlMs: 30_000,
    dataClassification: "voice_transcript",
    payload: { text: "Run the selected tests." },
  },
  sentAt: new Date().toISOString(),
});

describe("Agent Mesh bridge durable outbox", () => {
  it("drops expired and cross-session frames before reconnect delivery", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-bridge-"));
    roots.push(root);
    const store = new BridgeOutbox(path.join(root, "bridge.sqlite3"));
    try {
      const now = new Date("2026-08-21T06:00:00.000Z");
      const expired = eventFrame("agentmesh-wearable-g2-a", 1);
      expired.event.timestamp = "2026-08-21T05:58:00.000Z";
      expired.event.ttlMs = 30_000;
      const crossSession = eventFrame("agentmesh-wearable-g2-a", 2);
      crossSession.event.sessionId = "lesson-session-b";
      const current = eventFrame("agentmesh-wearable-g2-a", 3);
      for (const [key, frame] of [
        ["intent:expired", expired],
        ["intent:cross-session", crossSession],
        ["intent:current", current],
      ] as const) {
        store.enqueueEvent(key, frame, {
          kind: "intent",
          alreadyDispatched: true,
          legacyDisplayDelivered: false,
        });
      }

      expect(store.discardUndeliverableFrames("lesson-session-a", now)).toEqual(
        { events: 2, lifecycles: 0 },
      );
      expect(store.pendingEvents().map((pending) => pending.frameId)).toEqual([
        current.frameId,
      ]);
      expect(store.receiptForMessage(expired.event.messageId)).toBeUndefined();
      expect(
        store.receiptForMessage(crossSession.event.messageId),
      ).toBeUndefined();
    } finally {
      store.close();
    }
  });

  it("replays pending semantic events and purges their payload after a Fabric ack", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-bridge-"));
    roots.push(root);
    const databasePath = path.join(root, "bridge.sqlite3");
    const firstStore = new BridgeOutbox(databasePath);
    const frame = eventFrame("agentmesh-wearable-g2-a", 1);
    firstStore.enqueueEvent("intent:intent-a", frame, {
      kind: "intent",
      agentMeshIntentId: "71ac9029-a169-4e13-ae36-2bfc4f7b1ca1",
      agentMeshCommandId: "e02c0c88-2a06-48ab-9688-b68c15f3cd76",
      agentMeshSessionId: "managed-codex",
      alreadyDispatched: true,
      legacyDisplayDelivered: false,
    });
    expect(firstStore.nextNodeSequence("agentmesh-wearable-g2-a")).toBe(1);
    firstStore.close();

    const reopened = new BridgeOutbox(databasePath);
    try {
      expect(reopened.pendingEvents()).toHaveLength(1);
      const receipt = reopened.acknowledgeFrame(frame.frameId);
      expect(receipt?.alreadyDispatched).toBe(true);
      expect(reopened.pendingEvents()).toEqual([]);
      expect(reopened.receiptForMessage(frame.event.messageId)).toMatchObject({
        sourceKey: "intent:intent-a",
        agentMeshSessionId: "managed-codex",
      });
    } finally {
      reopened.close();
    }
  });

  it("durably replays adapter command lifecycle reports until acknowledged", () => {
    const root = mkdtempSync(path.join(os.tmpdir(), "cit-agent-bridge-"));
    roots.push(root);
    const store = new BridgeOutbox(path.join(root, "bridge.sqlite3"));
    try {
      const commandId = randomUUID();
      const lifecycle: AdapterCommandLifecycleFrame = {
        frameType: "adapter.command_lifecycle",
        frameId: randomUUID(),
        protocolVersion: 1,
        lifecycle: {
          messageId: randomUUID(),
          schemaVersion: "1.0",
          messageType: "command.lifecycle",
          commandId,
          requestMessageId: randomUUID(),
          sessionId: "lesson-session-a",
          targetNodeId: "agentmesh-agent-codex-a",
          stage: "SUCCEEDED",
          occurredAt: new Date().toISOString(),
          correlationId: randomUUID(),
          details: { compatibilityMode: true },
        },
        sentAt: new Date().toISOString(),
      };
      store.enqueueLifecycle(lifecycle);
      store.enqueueLifecycle(lifecycle);
      expect(store.pendingLifecycles()).toEqual([
        { frameId: lifecycle.frameId, frame: lifecycle },
      ]);
      expect(store.acknowledgeLifecycleFrame(lifecycle.frameId)).toBe(true);
      expect(store.pendingLifecycles()).toEqual([]);
    } finally {
      store.close();
    }
  });
});
