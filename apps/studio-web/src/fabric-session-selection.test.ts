import { describe, expect, it } from "vitest";

import {
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

  it("clears choices when the tutor switches sessions and trusts saved bindings", () => {
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
    ).toEqual({ classroom_plug: "matter-8-ep1" });
  });
});
