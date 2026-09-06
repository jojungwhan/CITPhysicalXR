import type {
  CoursePack,
  IntegrationNode,
  InteractionSession,
} from "@citxr/protocol";
import { describe, expect, it } from "vitest";

import {
  automaticRoleAssignments,
  compatibleRoleNodes,
  latestCoursePacks,
  reconciledRoleSelections,
  refreshedSessionSelection,
} from "./fabric-session-selection.js";

describe("Fabric tutor session selection", () => {
  it("excludes a takeoff-only controller from a start-and-land fleet role", () => {
    const capability = (
      name: string,
    ): IntegrationNode["consumedCapabilities"][number] =>
      ({
        name,
        safetyClassification: "flight",
      }) as IntegrationNode["consumedCapabilities"][number];
    const node = (nodeId: string, capabilities: string[]): IntegrationNode =>
      ({
        nodeId,
        siteId: "local-site",
        roomId: "local-room",
        connectionState: "connected",
        simulated: false,
        publishedCapabilities: [],
        consumedCapabilities: capabilities.map(capability),
      }) as unknown as IntegrationNode;
    const start = "mobility.flight.fleet_sequence.start";
    const stop = "mobility.flight.fleet_sequence.stop";
    const session = {
      siteId: "local-site",
      roomId: "local-room",
      mode: "physical",
    } as InteractionSession;
    const requirement = {
      role: "fleet_sequence_controller",
      oneOfCapabilities: [start],
      allOfCapabilities: [stop],
      optional: true,
    } as CoursePack["roles"][number];

    expect(
      compatibleRoleNodes(
        [node("unsafe-start-only", [start]), node("safe-fleet", [start, stop])],
        session,
        requirement,
      ).map((candidate) => candidate.nodeId),
    ).toEqual(["safe-fleet"]);
  });

  it("offers only the newest installed version of each course", () => {
    const legacyGlassesCourse = {
      coursePackId: "glasses-device-control",
      version: "1.0.0",
    };
    const currentGlassesCourse = {
      coursePackId: "glasses-device-control",
      version: "1.10.0",
    };
    const robotCourse = {
      coursePackId: "gesture-ground-robot",
      version: "2.0.0",
    };

    expect(
      latestCoursePacks([
        legacyGlassesCourse,
        robotCourse,
        currentGlassesCourse,
      ]),
    ).toEqual([currentGlassesCourse, robotCourse]);
  });

  it("keeps the lesson builder open instead of restoring an old session", () => {
    expect(
      refreshedSessionSelection("", [
        { sessionId: "old-ended-session" },
        { sessionId: "old-stopped-session" },
      ]),
    ).toBe("");
  });

  it("keeps an unsubmitted device choice across background polling", () => {
    expect(
      reconciledRoleSelections(
        { classroom_plug: "matter-8-ep1" },
        true,
        [],
        [
          {
            role: "classroom_plug",
            optional: false,
            candidateNodeIds: ["matter-8-ep1", "matter-c-ep1"],
          },
        ],
      ),
    ).toEqual({ classroom_plug: "matter-8-ep1" });
  });

  it("clears stale choices while retaining saved bindings and current defaults", () => {
    expect(
      reconciledRoleSelections(
        {
          classroom_plug: "old-plug",
          classroom_plug_2: "old-plug-2",
        },
        false,
        [{ role: "classroom_plug", nodeId: "matter-8-ep1" }],
        [
          {
            role: "classroom_plug",
            optional: false,
            candidateNodeIds: ["matter-8-ep1", "matter-c-ep1"],
          },
          {
            role: "classroom_plug_2",
            optional: true,
            candidateNodeIds: ["matter-8-ep1", "matter-c-ep1"],
          },
        ],
      ),
    ).toEqual({
      classroom_plug: "matter-8-ep1",
      classroom_plug_2: "matter-c-ep1",
    });
  });

  it("defaults every connected input and numbered output without reusing a device", () => {
    expect(
      automaticRoleAssignments(
        [],
        [
          {
            role: "smart_ring_input",
            optional: false,
            candidateNodeIds: ["ring-1"],
          },
          {
            role: "ground_output_1",
            optional: true,
            candidateNodeIds: ["robot-a", "robot-b"],
          },
          {
            role: "ground_output_2",
            optional: true,
            candidateNodeIds: ["robot-a", "robot-b"],
          },
          {
            role: "ground_output_3",
            optional: true,
            candidateNodeIds: ["robot-a", "robot-b"],
          },
          {
            role: "power_output_1",
            optional: true,
            candidateNodeIds: ["plug-a", "plug-b"],
          },
          {
            role: "power_output_2",
            optional: true,
            candidateNodeIds: ["plug-a", "plug-b"],
          },
          {
            role: "power_output_3",
            optional: true,
            candidateNodeIds: ["plug-a", "plug-b"],
          },
          {
            role: "fleet_sequence_controller",
            optional: true,
            candidateNodeIds: ["fleet-1"],
          },
        ],
      ),
    ).toEqual({
      smart_ring_input: "ring-1",
      ground_output_1: "robot-a",
      ground_output_2: "robot-b",
      power_output_1: "plug-a",
      power_output_2: "plug-b",
      fleet_sequence_controller: "fleet-1",
    });
  });

  it("lets one bidirectional node fill independent input and output roles", () => {
    expect(
      automaticRoleAssignments(
        [],
        [
          {
            role: "glasses_input_1",
            optional: false,
            candidateNodeIds: ["g2-1"],
          },
          {
            role: "message_output_1",
            optional: true,
            candidateNodeIds: ["g2-1"],
          },
        ],
      ),
    ).toEqual({ glasses_input_1: "g2-1", message_output_1: "g2-1" });
  });

  it("fills arbitrary numbered role banks without a hard-coded family or ceiling", () => {
    expect(
      automaticRoleAssignments(
        [],
        [
          {
            role: "classroom_actuator_9",
            optional: true,
            candidateNodeIds: ["actuator-a", "actuator-b"],
          },
          {
            role: "classroom_actuator_10",
            optional: true,
            candidateNodeIds: ["actuator-a", "actuator-b"],
          },
        ],
      ),
    ).toEqual({
      classroom_actuator_9: "actuator-a",
      classroom_actuator_10: "actuator-b",
    });
  });

  it("does not guess between devices for one ambiguous numbered role", () => {
    expect(
      automaticRoleAssignments(
        [],
        [
          {
            role: "special_output_12",
            optional: true,
            candidateNodeIds: ["device-a", "device-b"],
          },
        ],
      ),
    ).toEqual({});
  });
});
