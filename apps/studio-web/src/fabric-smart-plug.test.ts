import { describe, expect, it } from "vitest";

import {
  assignedSmartPlugNodes,
  currentSmartPlugNodes,
  formatMatterSetupCode,
  isSmartPlugNode,
  isSmartPlugRole,
  isSwitchableLoadVisionLabel,
  latestSmartPlugState,
  preferredSmartPlugControlSession,
  readSmartPlugSelection,
  retainKnownSmartPlugSelection,
  saveSmartPlugSelection,
  SMART_PLUG_SELECTION_STORAGE_KEY,
  smartPlugControlPlan,
  smartPlugStateFromHealth,
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

  it("uses the adapter health snapshot before the lesson emits a state event", () => {
    expect(
      smartPlugStateFromHealth({
        lastSeenAt: "2026-08-24T06:05:00Z",
        metadata: { healthMetrics: { on: false, safeStateOff: true } },
      }),
    ).toEqual({
      on: false,
      observedAt: "2026-08-24T06:05:00Z",
    });
    expect(
      smartPlugStateFromHealth({
        lastSeenAt: "2026-08-24T06:05:00Z",
        metadata: { healthMetrics: { on: "false" } },
      }),
    ).toBeUndefined();
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

  it("plans one independent role for each of up to eight connected plugs", () => {
    const nodes = Array.from({ length: 9 }, (_, index) => ({
      nodeId: `plug-${index + 1}`,
      consumedCapabilities: [{ name: "power.switch.set" }],
    }));

    expect(
      smartPlugControlPlan(nodes).map(({ role, node }) => [role, node.nodeId]),
    ).toEqual([
      ["classroom_plug", "plug-1"],
      ["classroom_plug_2", "plug-2"],
      ["classroom_plug_3", "plug-3"],
      ["classroom_plug_4", "plug-4"],
      ["classroom_plug_5", "plug-5"],
      ["classroom_plug_6", "plug-6"],
      ["classroom_plug_7", "plug-7"],
      ["classroom_plug_8", "plug-8"],
    ]);
  });

  it("keeps known offline plugs after connected plugs in the visible plan", () => {
    const node = (nodeId: string, connectionState: string) => ({
      nodeId,
      connectionState,
      consumedCapabilities: [{ name: "power.switch.set" }],
    });

    expect(
      smartPlugControlPlan([
        node("plug-offline-a", "disconnected"),
        node("plug-connected-a", "connected"),
        node("plug-offline-b", "unavailable"),
        node("plug-connected-b", "degraded"),
      ]).map(({ role, node: plannedNode }) => [role, plannedNode.nodeId]),
    ).toEqual([
      ["classroom_plug", "plug-connected-a"],
      ["classroom_plug_2", "plug-connected-b"],
      ["classroom_plug_3", "plug-offline-a"],
      ["classroom_plug_4", "plug-offline-b"],
    ]);
  });

  it("persists selected plug identities without storing plug state", () => {
    const storage = memoryStorage();

    saveSmartPlugSelection(
      new Set(["matter-13-ep1", "matter-16-ep1"]),
      storage,
    );

    expect(Array.from(readSmartPlugSelection(storage))).toEqual([
      "matter-13-ep1",
      "matter-16-ep1",
    ]);
    expect(storage.getItem(SMART_PLUG_SELECTION_STORAGE_KEY)).toBe(
      '["matter-13-ep1","matter-16-ep1"]',
    );
  });

  it("ignores corrupt selection storage and removes identities no longer shown", () => {
    const storage = memoryStorage();
    storage.setItem(SMART_PLUG_SELECTION_STORAGE_KEY, "not-json");

    expect(Array.from(readSmartPlugSelection(storage))).toEqual([]);
    expect(
      Array.from(
        retainKnownSmartPlugSelection(
          new Set(["plug-connected", "plug-offline", "plug-removed"]),
          new Set(["plug-connected", "plug-offline"]),
        ),
      ),
    ).toEqual(["plug-connected", "plug-offline"]);
  });

  it("replaces a stale controller node with the latest live node for the same setup code", () => {
    const nodes = [
      {
        nodeId: "matter-old-ep1",
        connectionState: "disconnected",
        metadata: { matterNodeId: "8" },
        consumedCapabilities: [{ name: "power.switch.set" }],
      },
      {
        nodeId: "matter-new-ep1",
        connectionState: "connected",
        metadata: { matterNodeId: "27" },
        consumedCapabilities: [{ name: "power.switch.set" }],
      },
    ];

    expect(
      currentSmartPlugNodes(nodes, [
        { setupCode: "12345678901", matterNodeIds: ["8", "27"] },
      ]).map((node) => node.nodeId),
    ).toEqual(["matter-new-ep1"]);
  });

  it("formats an eleven-digit setup code as the printed classroom label", () => {
    expect(formatMatterSetupCode("12345678901")).toBe("1234 567 8901");
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

const memoryStorage = () => {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  };
};
