import { describe, expect, it } from "vitest";

import { isSmartPlugNode, latestSmartPlugState } from "./fabric-smart-plug.js";

describe("Fabric smart-plug presentation", () => {
  it("recognizes the canonical power switch without using a model allowlist", () => {
    const node = {
      publishedCapabilities: [],
      consumedCapabilities: [{ name: "power.switch.set" }],
    };

    expect(isSmartPlugNode(node)).toBe(true);
  });

  it("returns the latest valid normalized state for the bound node", () => {
    const events = [
      stateEvent(1, "plug-a", false, "initial"),
      stateEvent(2, "plug-b", true, "poll"),
      stateEvent(3, "plug-a", true, "command"),
    ];

    expect(latestSmartPlugState(events, "plug-a")).toEqual({
      on: true,
      observedAt: "2026-08-21T03:00:03Z",
      source: "command",
    });
    expect(latestSmartPlugState(events, "missing")).toBeUndefined();
  });
});

const stateEvent = (
  streamSequence: number,
  sourceNodeId: string,
  on: boolean,
  source: string,
) => ({
  streamSequence,
  event: {
    topic: "power.switch.state",
    sourceNodeId,
    timestamp: `2026-08-21T03:00:0${streamSequence}Z`,
    payload: { on, source },
  },
});
