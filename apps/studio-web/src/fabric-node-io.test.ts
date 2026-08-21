import { describe, expect, it } from "vitest";

import { classifyFabricNodeIo } from "./fabric-node-io.js";

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
});
