import { describe, expect, it } from "vitest";

import {
  assignedSmartPlugNodes,
  isSmartPlugNode,
  isSmartPlugRole,
  isSwitchableLoadVisionLabel,
  latestSmartPlugState,
  preferredSmartPlugControlSession,
} from "./fabric-smart-plug.js";

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

  it("keeps independently assigned classroom plugs separate", () => {
    const nodes = ["plug-a", "plug-b"].map((nodeId) => ({
      nodeId,
      consumedCapabilities: [{ name: "power.switch.set" }],
    }));

    expect(isSmartPlugRole("classroom_plug")).toBe(true);
    expect(isSmartPlugRole("classroom_plug_2")).toBe(true);
    expect(isSmartPlugRole("student_robot")).toBe(false);
    expect(
      assignedSmartPlugNodes(
        [
          { role: "classroom_plug", nodeId: "plug-a" },
          { role: "classroom_plug_2", nodeId: "plug-b" },
          { role: "student_robot", nodeId: "plug-a" },
        ],
        nodes,
      ).map(({ role, node }) => [role, node.nodeId]),
    ).toEqual([
      ["classroom_plug", "plug-a"],
      ["classroom_plug_2", "plug-b"],
    ]);
  });

  it("offers outlet actions only for explicitly switchable visual classes", () => {
    expect(isSwitchableLoadVisionLabel("lamp")).toBe(true);
    expect(isSwitchableLoadVisionLabel(" Light ")).toBe(true);
    expect(isSwitchableLoadVisionLabel("smart plug")).toBe(true);
    expect(isSwitchableLoadVisionLabel("drone")).toBe(false);
    expect(isSwitchableLoadVisionLabel("robot")).toBe(false);
  });

  it("finds the prepared session that controls the most connected plugs", () => {
    const sessions = [
      controlSession("single-active", "active", [
        { role: "classroom_plug", nodeId: "plug-a" },
      ]),
      controlSession("both-ready", "ready", [
        { role: "classroom_plug", nodeId: "plug-a" },
        { role: "classroom_plug_2", nodeId: "plug-b" },
      ]),
      controlSession("both-stopped", "stopped", [
        { role: "classroom_plug", nodeId: "plug-a" },
        { role: "classroom_plug_2", nodeId: "plug-b" },
      ]),
      {
        ...controlSession("unrelated", "active", [
          { role: "classroom_plug", nodeId: "plug-a" },
        ]),
        coursePackId: "device-monitoring",
      },
    ];

    expect(
      preferredSmartPlugControlSession(sessions, ["plug-a", "plug-b"])
        ?.sessionId,
    ).toBe("both-ready");
    expect(preferredSmartPlugControlSession(sessions, [])).toBeUndefined();
  });
});

const controlSession = (
  sessionId: string,
  state: string,
  roleBindings: { role: string; nodeId: string }[],
) => ({
  sessionId,
  coursePackId: "smart-plug-control",
  state,
  updatedAt: `2026-08-24T00:00:0${roleBindings.length}Z`,
  roleBindings,
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
