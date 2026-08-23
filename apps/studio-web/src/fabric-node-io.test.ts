import { describe, expect, it } from "vitest";

import {
  classifyFabricNodeIo,
  groupFabricCourseRolesByIo,
  groupFabricIntegrationsByIo,
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

  it("groups setup cards by their declared direction before nodes connect", () => {
    const grouped = groupFabricIntegrationsByIo([
      { integrationId: "leap", ioType: "input" as const },
      { integrationId: "display", ioType: "output" as const },
      { integrationId: "glasses", ioType: "bidirectional" as const },
    ]);

    expect(grouped.input.map((item) => item.integrationId)).toEqual(["leap"]);
    expect(grouped.output.map((item) => item.integrationId)).toEqual([
      "display",
    ]);
    expect(grouped.bidirectional.map((item) => item.integrationId)).toEqual([
      "glasses",
    ]);
  });

  it("groups course roles and preserves legacy recipes as bidirectional", () => {
    const grouped = groupFabricCourseRolesByIo([
      { role: "gesture", ioType: "input" as const },
      { role: "robot", ioType: "output" as const },
      { role: "legacy" },
    ]);

    expect(grouped.input.map((item) => item.role)).toEqual(["gesture"]);
    expect(grouped.output.map((item) => item.role)).toEqual(["robot"]);
    expect(grouped.bidirectional.map((item) => item.role)).toEqual(["legacy"]);
  });
});
