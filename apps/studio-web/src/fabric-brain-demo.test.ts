import { describe, expect, it } from "vitest";

import type { StoredFabricEvent } from "./fabric-client.js";
import {
  BRAIN_DEMO_ARM_CAPABILITY,
  BRAIN_DEMO_STATUS_CAPABILITY,
  BRAIN_DEMO_STOP_CAPABILITY,
  isBrainDemoControllerNode,
  latestBrainDemoStatus,
} from "./fabric-brain-demo.js";

describe("bounded Brain2Devices demo UI boundary", () => {
  it("recognizes only the separate controller without general flight commands", () => {
    const node = (consumed: string[]) =>
      ({
        pluginId: "cit.brain2devices-demo",
        consumedCapabilities: consumed.map((name) => ({ name })),
      }) as Parameters<typeof isBrainDemoControllerNode>[0];

    expect(
      isBrainDemoControllerNode(
        node([BRAIN_DEMO_ARM_CAPABILITY, BRAIN_DEMO_STOP_CAPABILITY]),
      ),
    ).toBe(true);
    expect(
      isBrainDemoControllerNode(
        node([
          BRAIN_DEMO_ARM_CAPABILITY,
          BRAIN_DEMO_STOP_CAPABILITY,
          "mobility.flight.takeoff",
        ]),
      ),
    ).toBe(false);
  });

  it("uses only the latest controller status and clamps progress", () => {
    const events = [statusEvent(1, 0.25), statusEvent(2, 4)];

    expect(latestBrainDemoStatus(events, "brain-demo-a")).toMatchObject({
      armed: true,
      phase: "waiting",
      progress: 1,
      message: "Waiting for threshold",
    });
    expect(latestBrainDemoStatus(events, "another-node")).toBeUndefined();
  });
});

const statusEvent = (
  streamSequence: number,
  progress: number,
): StoredFabricEvent => ({
  streamSequence,
  event: {
    messageId: `00000000-0000-4000-8000-${String(streamSequence).padStart(12, "0")}`,
    schemaVersion: "1.0",
    messageType: "event",
    topic: BRAIN_DEMO_STATUS_CAPABILITY,
    sourceNodeId: "brain-demo-a",
    sourceCapability: BRAIN_DEMO_STATUS_CAPABILITY,
    siteId: "cit-site",
    roomId: "room-a",
    sessionId: "00000000-0000-4000-8000-000000000001",
    timestamp: `2026-08-23T00:00:0${streamSequence}Z`,
    monotonicTimestamp: streamSequence,
    sequence: streamSequence,
    ttlMs: 2_000,
    dataClassification: "biosignal_derived",
    payload: {
      available: true,
      active: true,
      armed: true,
      phase: "waiting",
      progress,
      message: "Waiting for threshold",
      demoRunning: false,
      simulated: true,
    },
  },
});
