import { describe, expect, it } from "vitest";

import {
  classifyFabricNodeIo,
  isAvailableFabricNode,
} from "./fabric-node-io.js";

describe("Fabric node I/O classification", () => {
  it("classifies a publisher as an input", () => {
    expect(
      classifyFabricNodeIo({
        publishedCapabilities: ["interaction.gesture.hand"],
        consumedCapabilities: [],
      }),
    ).toBe("input");
  });

  it("classifies a command consumer as an output", () => {
    expect(
      classifyFabricNodeIo({
        publishedCapabilities: [],
        consumedCapabilities: ["power.switch.set"],
      }),
    ).toBe("output");
  });

  it("classifies glasses, robots, and agents as bidirectional when they do both", () => {
    expect(
      classifyFabricNodeIo({
        publishedCapabilities: ["telemetry.battery"],
        consumedCapabilities: ["mobility.ground.drive"],
      }),
    ).toBe("bidirectional");
  });

  it("keeps disconnected history out of the live classroom inventory", () => {
    expect(isAvailableFabricNode({ connectionState: "connected" })).toBe(true);
    expect(isAvailableFabricNode({ connectionState: "degraded" })).toBe(true);
    expect(isAvailableFabricNode({ connectionState: "disconnected" })).toBe(
      false,
    );
    expect(isAvailableFabricNode({ connectionState: "unavailable" })).toBe(
      false,
    );
  });
});
