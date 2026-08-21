import type { InteractionSession } from "@citxr/protocol";

export type TutorStage =
  | "find_devices"
  | "choose_lesson"
  | "connect_devices"
  | "review_safety"
  | "start_lesson"
  | "teach"
  | "lesson_ended";

export interface TutorGuide {
  stage: TutorStage;
  step: 1 | 2 | 3 | 4 | 5;
  title: string;
  description: string;
  targetId: string;
}

export const tutorGuide = (
  session: InteractionSession | undefined,
  requiredRoles: readonly string[],
  discoveryScanned: boolean,
): TutorGuide => {
  if (!discoveryScanned) {
    return {
      stage: "find_devices",
      step: 1,
      title: "Find the classroom devices",
      description:
        "Power on today’s equipment, plug in USB devices, then let CIT check this computer and its local connections.",
      targetId: "device-discovery",
    };
  }
  if (session === undefined) {
    return {
      stage: "choose_lesson",
      step: 2,
      title: "Choose today’s lesson",
      description:
        "Pick an experience below. CIT will create a safe classroom session and find matching devices.",
      targetId: "lesson-setup",
    };
  }
  if (["stopped", "emergency_stopped", "failed"].includes(session.state)) {
    return {
      stage: "lesson_ended",
      step: 2,
      title: "This lesson has ended",
      description:
        "Choose a lesson to create a fresh session. Connected devices remain available.",
      targetId: "lesson-setup",
    };
  }
  const assigned = new Set(session.roleBindings.map((binding) => binding.role));
  const missing = requiredRoles.filter((role) => !assigned.has(role));
  if (missing.length > 0) {
    return {
      stage: "connect_devices",
      step: 3,
      title: `Connect ${missing.length} more ${missing.length === 1 ? "device" : "devices"}`,
      description:
        "Choose a connected device for each empty slot. If nothing is listed, start that device’s CIT adapter and refresh.",
      targetId: "device-setup",
    };
  }
  if (session.mode === "physical" && session.armed !== true) {
    return {
      stage: "review_safety",
      step: 4,
      title: "Review safety before enabling devices",
      description:
        "Check the room, keep the emergency stop visible, then confirm that physical control can be enabled.",
      targetId: "lesson-safety",
    };
  }
  if (session.state === "active") {
    return {
      stage: "teach",
      step: 5,
      title: "Lesson running",
      description:
        "Devices are ready. Use the lesson controls below and end the session when class is finished.",
      targetId: "live-controls",
    };
  }
  return {
    stage: "start_lesson",
    step: 4,
    title: "Everything is ready",
    description:
      "Review the summary, then start the lesson when your students are ready.",
    targetId: "lesson-safety",
  };
};
