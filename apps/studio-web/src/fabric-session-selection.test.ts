import { describe, expect, it } from "vitest";

import { refreshedSessionSelection } from "./fabric-session-selection.js";

describe("Fabric tutor session selection", () => {
  it("keeps the lesson builder open instead of restoring an old session", () => {
    expect(
      refreshedSessionSelection("", [
        { sessionId: "old-ended-session" },
        { sessionId: "old-stopped-session" },
      ]),
    ).toBe("");
  });
});
