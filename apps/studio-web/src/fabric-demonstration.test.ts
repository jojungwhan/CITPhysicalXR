import { describe, expect, it } from "vitest";

import {
  allDemonstrationNodeIds,
  selectedDemonstrationNodes,
  toggledDemonstrationNodeIds,
} from "./fabric-demonstration.js";
import { smartPlugControlPlan } from "./fabric-smart-plug.js";

describe("direct demonstration device selection", () => {
  const nodes = [
    { nodeId: "matter-13-ep1" },
    { nodeId: "tello-1" },
    { nodeId: "sphero-1" },
  ];

  it("selects every connected device without a lesson", () => {
    expect([...allDemonstrationNodeIds(nodes)]).toEqual([
      "matter-13-ep1",
      "tello-1",
      "sphero-1",
    ]);
  });

  it("filters direct controls to the selected devices", () => {
    expect(
      selectedDemonstrationNodes(
        nodes,
        new Set(["matter-13-ep1", "sphero-1"]),
      ).map((node) => node.nodeId),
    ).toEqual(["matter-13-ep1", "sphero-1"]);
  });

  it("updates one device without mutating the prior selection", () => {
    const current = new Set(["matter-13-ep1"]);
    const added = toggledDemonstrationNodeIds(current, "tello-1", true);
    const removed = toggledDemonstrationNodeIds(added, "matter-13-ep1", false);

    expect([...current]).toEqual(["matter-13-ep1"]);
    expect([...added]).toEqual(["matter-13-ep1", "tello-1"]);
    expect([...removed]).toEqual(["tello-1"]);
  });

  it("reindexes a selected plug subset onto the required first control role", () => {
    const plugs = ["plug-a", "plug-b", "plug-c"].map((nodeId) => ({
      nodeId,
      consumedCapabilities: [{ name: "power.switch.set" }],
    }));
    const selected = selectedDemonstrationNodes(plugs, new Set(["plug-c"]));

    expect(
      smartPlugControlPlan(selected).map(({ role, node }) => [
        role,
        node.nodeId,
      ]),
    ).toEqual([["classroom_plug", "plug-c"]]);
  });
});
