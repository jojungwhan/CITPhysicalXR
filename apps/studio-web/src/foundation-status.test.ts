import { describe, expect, it } from "vitest";

import { foundationStatus } from "./foundation-status.js";

describe("Milestone 0 Studio status", () => {
  it("does not claim runtime, hardware, or Agent Mesh operation", () => {
    expect(foundationStatus()).toEqual({
      milestone: 0,
      mode: "foundation-only",
      physicalControl: false,
      agentMeshRequired: false,
    });
  });
});
