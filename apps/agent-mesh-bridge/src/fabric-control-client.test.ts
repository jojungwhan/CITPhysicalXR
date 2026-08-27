import type {
  CapabilityDescriptor,
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
  constraints: {},
});

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
  coursePackVersion: "1.0.0",
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
      const body = url.includes("/sessions/") ? session : nodes;
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

    const inventory = await new FabricControlApiClient(
      config,
      fetchMock as unknown as typeof fetch,
    ).inventory();

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
    expect(fetchMock).toHaveBeenCalledTimes(2);
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
    } as InteractionSession;
    const nodes = [
      node("sphero-a", "Sphero Ollie 2B-2DF3", ["mobility.ground.nudge"]),
      node("tello-fleet-a", "Tello fleet", [
        "mobility.flight.fleet_sequence.start",
        "mobility.flight.fleet_sequence.stop",
      ]),
    ];
    const fetchMock = vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            String(input).includes("/sessions/") ? synchronized : nodes,
          ),
          { status: 200 },
        ),
      ),
    );

    const inventory = await new FabricControlApiClient(
      config,
      fetchMock as unknown as typeof fetch,
    ).inventory();

    expect(inventory.coursePackId).toBe("synchronized-motor-control");
    expect(inventory.targets.map((target) => target.nodeId)).toEqual([
      "sphero-a",
      "tello-fleet-a",
    ]);
  });
});
