import { describe, expect, it } from "vitest";

import { authorizeBridgeOperation } from "./policy.js";

describe("Agent Mesh bridge foundation policy", () => {
  it("allows safety stops but never movement initiation", () => {
    expect(authorizeBridgeOperation("emergency_stop")).toEqual({
      allowed: true,
    });
    expect(authorizeBridgeOperation("physical_movement")).toEqual({
      allowed: false,
      reason: "Agent Mesh cannot initiate physical movement",
    });
  });
});
