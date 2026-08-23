import type { InteractionSession } from "@citxr/protocol";
import { describe, expect, it } from "vitest";

import { tutorGuide } from "./fabric-tutor-guide.js";
import { fabricTranslatorFor } from "./fabric-i18n.js";

describe("tutor next-step guide", () => {
  it("starts with a plain lesson choice", () => {
    expect(tutorGuide(undefined, [], false).stage).toBe("find_devices");
    expect(tutorGuide(undefined, [], true).stage).toBe("choose_lesson");
    expect(tutorGuide(undefined, [], true).title).toBe("Choose today’s lesson");
  });

  it("directs the tutor through devices, safety, and teaching", () => {
    const draft = session({ state: "draft" });
    expect(tutorGuide(draft, ["student_robot"], true).stage).toBe(
      "connect_devices",
    );

    const physicalReady = session({
      mode: "physical",
      state: "ready",
      roleBindings: [binding("student_robot")],
    });
    expect(tutorGuide(physicalReady, ["student_robot"], true).stage).toBe(
      "review_safety",
    );

    const active = session({
      mode: "physical",
      state: "active",
      armed: true,
      roleBindings: [binding("student_robot")],
    });
    expect(tutorGuide(active, ["student_robot"], true).stage).toBe("teach");
  });

  it("resumes an existing lesson at its real stage after a page reload", () => {
    const active = session({
      state: "active",
      roleBindings: [binding("student_robot")],
    });
    expect(tutorGuide(active, ["student_robot"], false).stage).toBe("teach");

    const draft = session({ state: "draft" });
    expect(tutorGuide(draft, ["student_robot"], false).stage).toBe(
      "connect_devices",
    );
  });

  it("returns Korean tutor guidance when Korean is selected", () => {
    const guide = tutorGuide(undefined, [], false, fabricTranslatorFor("ko"));
    expect(guide.title).toBe("교실 장치 찾기");
    expect(guide.description).toContain("USB");
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
