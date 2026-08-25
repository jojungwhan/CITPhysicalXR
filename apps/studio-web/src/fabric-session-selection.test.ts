import { describe, expect, it } from "vitest";

import {
  automaticRoleAssignments,
  reconciledRoleSelections,
  refreshedSessionSelection,
} from "./fabric-session-selection.js";

describe("Fabric tutor session selection", () => {
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
});
