import { describe, expect, it } from "vitest";

import {
  directControlSessionActions,
  plannedControlAssignments,
  sessionCoversNodes,
} from "./fabric-control-session.js";

describe("inline device control sessions", () => {
  const nodes = [{ nodeId: "device-a" }, { nodeId: "device-b" }];

  it("requires every visible device to have an accepted role", () => {
    const partial = {
      roleBindings: [{ role: "plug", nodeId: "device-a" }],
    };
    const complete = {
      roleBindings: [
        { role: "plug", nodeId: "device-a" },
        { role: "plug_2", nodeId: "device-b" },
      ],
    };

    expect(sessionCoversNodes(partial, nodes)).toBe(false);
    expect(sessionCoversNodes(complete, nodes)).toBe(true);
    expect(
      sessionCoversNodes(complete, nodes, (role) => role.startsWith("plug")),
    ).toBe(true);
    expect(
      sessionCoversNodes(complete, nodes, (role) => role === "robot"),
    ).toBe(false);
  });

  it("shows deterministic controls before setup and preserves real bindings", () => {
    expect(
      plannedControlAssignments(
        nodes,
        undefined,
        (index) => `plug_${index + 1}`,
      ),
    ).toEqual([
      { role: "plug_1", node: nodes[0] },
      { role: "plug_2", node: nodes[1] },
    ]);

    expect(
      plannedControlAssignments(
        nodes,
        {
          roleBindings: [
            { role: "secondary", nodeId: "device-a" },
            { role: "primary", nodeId: "device-b" },
          ],
        },
        (index) => `fallback_${index}`,
      ),
    ).toEqual([
      { role: "secondary", node: nodes[0] },
      { role: "primary", node: nodes[1] },
    ]);
  });

  it("plans one-click preparation for direct physical controls", () => {
    expect(
      directControlSessionActions({
        mode: "physical",
        state: "ready",
        armed: false,
      }),
    ).toEqual(["arm", "start"]);
    expect(
      directControlSessionActions({
        mode: "physical",
        state: "paused",
        armed: true,
      }),
    ).toEqual(["start"]);
    expect(
      directControlSessionActions({
        mode: "physical",
        state: "active",
        armed: false,
      }),
    ).toEqual(["pause", "arm", "start"]);
    expect(
      directControlSessionActions({
        mode: "physical",
        state: "active",
        armed: true,
      }),
    ).toEqual([]);
  });

  it("starts simulations directly without attempting to arm them", () => {
    expect(
      directControlSessionActions({
        mode: "simulation",
        state: "ready",
      }),
    ).toEqual(["start"]);
    expect(
      directControlSessionActions({
        mode: "simulation",
        state: "active",
      }),
    ).toEqual([]);
  });

  it("does not invent a recovery transition for terminal sessions", () => {
    expect(
      directControlSessionActions({
        mode: "physical",
        state: "stopped",
        armed: false,
      }),
    ).toEqual([]);
  });
});
