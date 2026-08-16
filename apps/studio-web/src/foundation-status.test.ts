import { describe, expect, it } from "vitest";

import { foundationStatus } from "./foundation-status.js";

describe("Milestone 1 Studio status", () => {
  it("claims a local runtime but no hardware or Agent Mesh operation", () => {
    expect(foundationStatus()).toEqual({
      milestone: 1,
      mode: "runtime-simulation",
      physicalControl: false,
      agentMeshRequired: false,
      localRuntimeApi: true,
    });
  });
});
