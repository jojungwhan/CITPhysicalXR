import { describe, expect, it } from "vitest";

import { fabricMediaFrameAvailable } from "./fabric-media.js";

describe("Fabric media frame readiness", () => {
  it("does not poll a registered Tello source before its first frame", () => {
    expect(
      fabricMediaFrameAvailable({
        state: "waiting",
        lastFrameAt: null,
        frameSequence: 0,
        contentType: null,
      }),
    ).toBe(false);
  });

  it("polls only after an online source has published a frame", () => {
    expect(
      fabricMediaFrameAvailable({
        state: "online",
        lastFrameAt: "2026-08-25T05:00:00Z",
        frameSequence: 1,
        contentType: "image/jpeg",
      }),
    ).toBe(true);
  });
});
