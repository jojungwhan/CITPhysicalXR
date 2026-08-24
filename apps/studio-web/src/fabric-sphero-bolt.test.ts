import { describe, expect, it } from "vitest";

import type { FabricDiscoveryCandidate } from "./fabric-client.js";
import {
  preferredSpheroControlSession,
  selectableSpheroCandidates,
  spheroControlAvailability,
  spheroNudgeVelocity,
} from "./fabric-sphero-bolt.js";

const candidate = (
  candidateId: string,
  displayName: string,
  model: FabricDiscoveryCandidate["model"] = "sphero-bolt",
  status: FabricDiscoveryCandidate["status"] = "found",
): FabricDiscoveryCandidate => ({
  candidateId,
  displayName,
  transport: "Bluetooth Low Energy",
  status,
  detail: "Read-only advertisement",
  model,
});

describe("Sphero BOLT UI policy", () => {
  it("selects only exact opaque SB-XXXX candidates", () => {
    const values = [
      candidate("sphero-aabbccddeeff", "SB-G1Q9"),
      candidate("sphero-paired-1", "SB-B2E8"),
      candidate("sphero-001122334455", "Sphero BOLT"),
      candidate("sphero-ffffffffffff", "SB-C3D7", "dash"),
      candidate(
        "sphero-112233445566",
        "SB-D4C6",
        "sphero-bolt",
        "setup_required",
      ),
    ];

    expect(
      selectableSpheroCandidates(values).map((item) => item.candidateId),
    ).toEqual(["sphero-aabbccddeeff"]);
  });

  it("keeps aim and movement locked until active and armed", () => {
    const physicalNode = { simulated: false } as Parameters<
      typeof spheroControlAvailability
    >[0];
    const simulatedNode = { simulated: true } as Parameters<
      typeof spheroControlAvailability
    >[0];

    expect(spheroControlAvailability(physicalNode, "active", false)).toEqual({
      light: true,
      physical: false,
      stop: true,
    });
    expect(
      spheroControlAvailability(physicalNode, "active", true).physical,
    ).toBe(true);
    expect(
      spheroControlAvailability(simulatedNode, "active", false).physical,
    ).toBe(true);
  });

  it("uses the bounded classroom maximum for a visible short nudge", () => {
    expect(spheroNudgeVelocity(1, 0)).toEqual({
      forwardMetersPerSecond: 0.2,
      rightMetersPerSecond: 0,
      clockwiseRadiansPerSecond: 0,
    });
    expect(spheroNudgeVelocity(0, -1)).toEqual({
      forwardMetersPerSecond: 0,
      rightMetersPerSecond: -0.2,
      clockwiseRadiansPerSecond: 0,
    });
  });

  it("finds the reusable session that exposes the most connected BOLT robots", () => {
    const sessions = [
      controlSession("single-active", "active", [
        { role: "student_robot", nodeId: "sphero-a" },
      ]),
      controlSession("both-ready", "ready", [
        { role: "robot_sensor_1", nodeId: "sphero-a" },
        { role: "robot_sensor_2", nodeId: "sphero-b" },
      ]),
      controlSession("both-stopped", "stopped", [
        { role: "robot_sensor_1", nodeId: "sphero-a" },
        { role: "robot_sensor_2", nodeId: "sphero-b" },
      ]),
    ];

    expect(
      preferredSpheroControlSession(sessions, ["sphero-a", "sphero-b"])
        ?.sessionId,
    ).toBe("both-ready");
    expect(preferredSpheroControlSession(sessions, [])).toBeUndefined();
  });
});

const controlSession = (
  sessionId: string,
  state: string,
  roleBindings: { role: string; nodeId: string }[],
) => ({
  sessionId,
  coursePackId: "device-monitoring",
  state,
  armed: false,
  updatedAt: `2026-08-24T00:00:0${roleBindings.length}Z`,
  roleBindings,
});
