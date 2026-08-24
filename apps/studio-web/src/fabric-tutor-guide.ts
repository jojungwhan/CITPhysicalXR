import type { InteractionSession } from "@citxr/protocol";

import { fabricTranslatorFor, type FabricTranslate } from "./fabric-i18n.js";

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
  actionLabel: string;
}

export const tutorGuide = (
  session: InteractionSession | undefined,
  requiredRoles: readonly string[],
  discoveryScanned: boolean,
  t: FabricTranslate = fabricTranslatorFor("en"),
): TutorGuide => {
  if (!discoveryScanned && session === undefined) {
    return {
      stage: "find_devices",
      step: 1,
      title: t("guide.find.title"),
      description: t("guide.find.description"),
      targetId: "device-discovery",
      actionLabel: t("guide.action.find"),
    };
  }
  if (session === undefined) {
    return {
      stage: "choose_lesson",
      step: 2,
      title: t("guide.choose.title"),
      description: t("guide.choose.description"),
      targetId: "lesson-setup",
      actionLabel: t("guide.action.choose"),
    };
  }
  if (["stopped", "emergency_stopped", "failed"].includes(session.state)) {
    return {
      stage: "lesson_ended",
      step: 2,
      title: t("guide.ended.title"),
      description: t("guide.ended.description"),
      targetId: "lesson-setup",
      actionLabel: t("guide.action.ended"),
    };
  }
  const assigned = new Set(session.roleBindings.map((binding) => binding.role));
  const missing = requiredRoles.filter((role) => !assigned.has(role));
  if (missing.length > 0) {
    return {
      stage: "connect_devices",
      step: 3,
      title: t("guide.connect.title", { count: missing.length }),
      description: t("guide.connect.description"),
      targetId: "device-setup",
      actionLabel: t("guide.action.connect"),
    };
  }
  if (session.mode === "physical" && session.armed !== true) {
    return {
      stage: "review_safety",
      step: 4,
      title: t("guide.safety.title"),
      description: t("guide.safety.description"),
      targetId: "lesson-safety",
      actionLabel: t("guide.action.review"),
    };
  }
  if (session.state === "active") {
    return {
      stage: "teach",
      step: 5,
      title: t("guide.teach.title"),
      description: t("guide.teach.description"),
      targetId: "live-controls",
      actionLabel: t("guide.action.teach"),
    };
  }
  return {
    stage: "start_lesson",
    step: 4,
    title: t("guide.ready.title"),
    description: t("guide.ready.description"),
    targetId: "lesson-safety",
    actionLabel: t("guide.action.review"),
  };
};
