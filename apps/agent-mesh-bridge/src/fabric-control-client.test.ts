import { readFileSync } from "node:fs";

import type {
  CapabilityDescriptor,
  CoursePack,
  IntegrationNode,
  InteractionSession,
} from "@citxr/protocol";
import { describe, expect, it, vi } from "vitest";

import type { BridgeConfig } from "./config.js";
import { FabricControlApiClient } from "./fabric-control-client.js";

const AT = "2026-08-25T00:00:00.000Z";

const config: BridgeConfig = {
  fabricAdapterUrl: "ws://127.0.0.1:8766/api/v1/adapters/connect",
  fabricCredential: `cit-adapter-${"a".repeat(40)}`,
  fabricApiUrl: "http://127.0.0.1:8766",
  fabricReadCredential: `cit-reader-${"b".repeat(40)}`,
  fabricSessionId: "lesson-session-a",
  projectFabricControls: true,
  agentMeshBaseUrl: "http://127.0.0.1:7342",
  agentMeshDeviceToken: `device_${"c".repeat(43)}`,
  databasePath: "D:\\temp\\agent-mesh-bridge.sqlite3",
  siteId: "local-site",
  roomId: "local-room",
  hostId: "agent-mesh-bridge-local",
  pollIntervalMs: 2_000,
  reconnectDelayMs: 2_000,
};

const capability = (name: string): CapabilityDescriptor => ({
  name,
  version: "1.0",
  direction: "consume",
  maximumRateHz: 10,
  latencyClass: "interactive",
  safetyClassification: "bounded_physical",
  dataClassification: "operational",
  constraints:
    name === "mobility.ground.nudge"
      ? {
          arguments: {
            direction: {
              enum: ["forward", "backward", "left", "right", "stop"],
            },
          },
        }
      : {},
});

const coursePackFixture = (filename: string): CoursePack =>
  JSON.parse(
    readFileSync(
      new URL(
        `../../runtime-py/src/cit_runtime/course-packs/${filename}.generated.json`,
        import.meta.url,
      ),
      "utf8",
    ),
  ) as CoursePack;

const glassesCoursePack = coursePackFixture("glasses-device-control");
const synchronizedCoursePack = coursePackFixture("synchronized-motor-control");

const node = (
  nodeId: string,
  displayName: string,
  capabilities: string[],
): IntegrationNode => ({
  schemaVersion: "1.0",
  nodeId,
  pluginId: `cit.${nodeId}`,
  pluginVersion: "1.0.0",
  runtimeVersion: "1.0.0",
  hostId: "edge-host-a",
  siteId: "local-site",
  roomId: "local-room",
  displayName,
  connectionState: "connected",
  healthState: "healthy",
  physical: false,
  simulated: true,
  publishedCapabilities: [],
  consumedCapabilities: capabilities.map(capability),
  configurationSchema: {},
  safetyClassification: "bounded_physical",
  dataClassifications: ["operational"],
  simulatorAvailable: true,
  requiredPermissions: [],
  lastSeenAt: AT,
  metadata: {},
});

const session: InteractionSession = {
  schemaVersion: "1.0",
  sessionId: "lesson-session-a",
  coursePackId: "glasses-device-control",
  coursePackVersion: "1.3.0",
  siteId: "local-site",
  roomId: "local-room",
  mode: "simulation",
  state: "active",
  armed: true,
  participantIds: [],
  roleBindings: [
    {
      role: "ground_output_1",
      nodeId: "sphero-a",
      requiredCapability: "mobility.ground.nudge",
      assignedAt: AT,
      assignedBy: "instructor-a",
    },
    {
      role: "fleet_sequence_controller",
      nodeId: "tello-fleet-a",
      requiredCapability: "mobility.flight.fleet_sequence.start",
      assignedAt: AT,
      assignedBy: "instructor-a",
    },
    {
      role: "power_output_1",
      nodeId: "matter-plug-a",
      requiredCapability: "power.switch.set",
      assignedAt: AT,
      assignedBy: "instructor-a",
    },
  ],
  safetyProfile: "classroom-drone-monitoring",
  createdAt: AT,
  updatedAt: AT,
  startedAt: AT,
  createdBy: "instructor-a",
};

describe("Fabric control inventory", () => {
  it("projects only exact lesson assignments and capability-supported actions", async () => {
    let now = 1_000;
    const nodes = [
      node("sphero-a", "Sphero BOLT SB-B7BE", [
        "mobility.ground.nudge",
        "mobility.ground.demonstration.start",
        "robot.light.set",
      ]),
      node("tello-fleet-a", "Tello fleet", [
        "mobility.flight.fleet_sequence.start",
        "mobility.flight.fleet_sequence.stop",
      ]),
      node("unassigned-robot", "Unassigned robot", ["mobility.ground.nudge"]),
      node("matter-plug-a", "Tapo P110M 1", ["power.switch.set"]),
    ];
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const body = url.includes("/sessions/")
        ? session
        : url.includes("/course-packs")
          ? [glassesCoursePack]
          : nodes;
      expect(new Headers(init?.headers).get("authorization")).toBe(
        `Bearer ${config.fabricReadCredential}`,
      );
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    });

    const client = new FabricControlApiClient(
      config,
      fetchMock as unknown as typeof fetch,
      () => now,
    );
    const inventory = await client.inventory();

    expect(inventory).toMatchObject({
      sessionId: "lesson-session-a",
      coursePackId: "glasses-device-control",
      sessionState: "active",
      armed: true,
      targets: [
        {
          role: "ground_output_1",
          nodeId: "sphero-a",
          kind: "ground_robot",
          actions: [
            "forward",
            "backward",
            "left",
            "right",
            "stop",
            "light",
            "demo",
          ],
        },
        {
          role: "fleet_sequence_controller",
          nodeId: "tello-fleet-a",
          kind: "drone_fleet",
          actions: ["takeoff", "land"],
        },
        {
          role: "power_output_1",
          nodeId: "matter-plug-a",
          kind: "smart_plug",
          actions: ["power_on", "power_off"],
        },
      ],
    });
    expect(
      inventory.targets.some((target) => target.nodeId === "unassigned-robot"),
    ).toBe(false);
    expect(inventory.routes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          target: "ground_outputs",
          actions: [
            "forward",
            "backward",
            "left",
            "right",
            "stop",
            "demo",
            "light",
          ],
        }),
        expect.objectContaining({
          target: "tello_fleet",
          actions: ["takeoff", "land"],
        }),
        expect.objectContaining({
          target: "power_outputs",
          actions: ["power_on", "power_off"],
        }),
        expect.objectContaining({
          target: "all_outputs",
          actions: ["activate", "stop"],
        }),
      ]),
    );
    expect(fetchMock).toHaveBeenCalledTimes(3);

    await client.inventory();
    expect(fetchMock).toHaveBeenCalledTimes(5);

    now += config.pollIntervalMs;
    await client.inventory();
    expect(fetchMock).toHaveBeenCalledTimes(8);
  });

  it("projects a light-only robot without inventing movement support", async () => {
    const dotSession = {
      ...session,
      roleBindings: [
        ...session.roleBindings,
        {
          role: "ground_output_2",
          nodeId: "dot-a",
          requiredCapability: "robot.light.set",
          assignedAt: AT,
          assignedBy: "instructor-a",
        },
      ],
    } satisfies InteractionSession;
    const nodes = [node("dot-a", "Sphero Mini Dot", ["robot.light.set"])];
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.includes("/sessions/")
        ? dotSession
        : url.includes("/course-packs")
          ? [glassesCoursePack]
          : nodes;
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    });

    const inventory = await new FabricControlApiClient(
      config,
      fetchMock as unknown as typeof fetch,
    ).inventory();

    expect(inventory.targets).toEqual([
      expect.objectContaining({
        role: "ground_output_2",
        nodeId: "dot-a",
        kind: "ground_robot",
        actions: ["light"],
      }),
    ]);
  });

  it("rejects a session from another course pack", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            String(input).includes("/sessions/")
              ? { ...session, coursePackId: "another-course" }
              : [],
          ),
          { status: 200 },
        ),
      ),
    );

    await expect(
      new FabricControlApiClient(
        config,
        fetchMock as unknown as typeof fetch,
      ).inventory(),
    ).rejects.toThrow("not a device-control lesson");
  });

  it("projects the same bounded inventory for synchronized control", async () => {
    const synchronized = {
      ...session,
      coursePackId: "synchronized-motor-control",
      coursePackVersion: "1.0.0",
    } as InteractionSession;
    const nodes = [
      node("sphero-a", "Sphero Ollie 2B-2DF3", ["mobility.ground.nudge"]),
      node("tello-fleet-a", "Tello fleet", [
        "mobility.flight.fleet_sequence.start",
        "mobility.flight.fleet_sequence.stop",
      ]),
    ];
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.includes("/sessions/")
        ? synchronized
        : url.includes("/course-packs")
          ? [synchronizedCoursePack]
          : nodes;
      return Promise.resolve(
        new Response(JSON.stringify(body), { status: 200 }),
      );
    });

    const inventory = await new FabricControlApiClient(
      config,
      fetchMock as unknown as typeof fetch,
    ).inventory();

    expect(inventory.coursePackId).toBe("synchronized-motor-control");
    expect(inventory.targets.map((target) => target.nodeId)).toEqual([
      "sphero-a",
      "tello-fleet-a",
    ]);
    expect(inventory.routes).toEqual([
      {
        target: "ground_outputs",
        actions: ["forward", "backward", "left", "right", "stop"],
      },
      { target: "tello_fleet", actions: ["takeoff", "land"] },
    ]);
  });

  it("does not advertise actions contributed only by a disconnected output", async () => {
    const mixedSession = {
      ...session,
      roleBindings: [
        {
          role: "ground_output_1",
          nodeId: "sphero-offline",
          requiredCapability: "mobility.ground.nudge",
          assignedAt: AT,
          assignedBy: "instructor-a",
        },
        {
          role: "ground_output_2",
          nodeId: "dot-online",
          requiredCapability: "robot.light.set",
          assignedAt: AT,
          assignedBy: "instructor-a",
        },
      ],
    } satisfies InteractionSession;
    const offlineRobot = {
      ...node("sphero-offline", "Offline Sphero", [
        "mobility.ground.nudge",
        "mobility.ground.demonstration.start",
        "robot.light.set",
      ]),
      connectionState: "disconnected" as const,
    };
    const nodes = [
      offlineRobot,
      node("dot-online", "Online Dot", ["robot.light.set"]),
    ];
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.includes("/sessions/")
        ? mixedSession
        : url.includes("/course-packs")
          ? [glassesCoursePack]
          : nodes;
      return Promise.resolve(
        new Response(JSON.stringify(body), { status: 200 }),
      );
    });

    const inventory = await new FabricControlApiClient(
      config,
      fetchMock as unknown as typeof fetch,
    ).inventory();

    expect(
      inventory.routes.find((route) => route.target === "ground_outputs"),
    ).toEqual({ target: "ground_outputs", actions: ["light"] });
    expect(
      inventory.routes.find(
        (route) =>
          route.target === "assigned_output" &&
          route.targetRole === "ground_output_1",
      ),
    ).toBeUndefined();
  });

  it("fails closed when a legacy fleet binding can take off but cannot land", async () => {
    const fleetOnlySession = {
      ...session,
      roleBindings: [
        {
          role: "fleet_sequence_controller",
          nodeId: "start-only-fleet",
          requiredCapability: "mobility.flight.fleet_sequence.start",
          assignedAt: AT,
          assignedBy: "instructor-a",
        },
      ],
    } satisfies InteractionSession;
    const nodes = [
      node("start-only-fleet", "Unsafe legacy fleet", [
        "mobility.flight.fleet_sequence.start",
      ]),
    ];
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.includes("/sessions/")
        ? fleetOnlySession
        : url.includes("/course-packs")
          ? [glassesCoursePack]
          : nodes;
      return Promise.resolve(
        new Response(JSON.stringify(body), { status: 200 }),
      );
    });

    const inventory = await new FabricControlApiClient(
      config,
      fetchMock as unknown as typeof fetch,
    ).inventory();

    expect(inventory.targets).toEqual([]);
    expect(
      inventory.routes.some(
        (route) =>
          route.actions.includes("takeoff") ||
          route.actions.includes("activate"),
      ),
    ).toBe(false);
  });
});
