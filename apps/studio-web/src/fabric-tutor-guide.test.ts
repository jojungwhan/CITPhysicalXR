import type { InteractionSession } from "@citxr/protocol";
import { describe, expect, it } from "vitest";

import { tutorGuide } from "./fabric-tutor-guide.js";

describe("tutor next-step guide", () => {
  it("starts with a plain lesson choice", () => {
    expect(tutorGuide(undefined, []).stage).toBe("choose_lesson");
    expect(tutorGuide(undefined, []).title).toBe("Choose today’s lesson");
  });

  it("directs the tutor through devices, safety, and teaching", () => {
    const draft = session({ state: "draft" });
    expect(tutorGuide(draft, ["student_robot"]).stage).toBe("connect_devices");

    const physicalReady = session({
      mode: "physical",
      state: "ready",
      roleBindings: [binding("student_robot")],
    });
    expect(tutorGuide(physicalReady, ["student_robot"]).stage).toBe(
      "review_safety",
    );

    const active = session({
      mode: "physical",
      state: "active",
      armed: true,
      roleBindings: [binding("student_robot")],
    });
    expect(tutorGuide(active, ["student_robot"]).stage).toBe("teach");
  });
});

const binding = (role: string) => ({
  role,
  nodeId: `${role}-node`,
  requiredCapability: "test.capability",
  assignedAt: "2026-08-21T03:00:00Z",
  assignedBy: "tutor-a",
});

const session = (
  overrides: Partial<InteractionSession>,
): InteractionSession => ({
  schemaVersion: "1.0",
  sessionId: "session-a",
  coursePackId: "course-a",
  coursePackVersion: "1.0.0",
  siteId: "local-site",
  roomId: "local-room",
  mode: "simulation",
  state: "draft",
  armed: false,
  participantIds: [],
  roleBindings: [],
  safetyProfile: "classroom-safe",
  createdAt: "2026-08-21T03:00:00Z",
  updatedAt: "2026-08-21T03:00:00Z",
  createdBy: "tutor-a",
  ...overrides,
});
