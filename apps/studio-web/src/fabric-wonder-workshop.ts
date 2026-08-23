import type { IntegrationNode } from "@citxr/protocol";

import type {
  FabricDiscoveryCandidate,
  WonderRobotSelection,
} from "./fabric-client.js";

export const WONDER_PLUGIN_ID = "cit.wonder-workshop";
export const WONDER_LIGHT_CAPABILITY = "robot.light.set";
export const WONDER_SOUND_CAPABILITY = "media.audio.cue.play";
export const WONDER_VELOCITY_CAPABILITY = "mobility.ground.set_velocity";
export const WONDER_STOP_CAPABILITY = "mobility.ground.stop";
export const WONDER_HEAD_CAPABILITY = "robot.head.set_pose";

export type WonderModel = "dash" | "dot";

export const isWonderCandidateId = (candidateId: string): boolean =>
  /^wonder-[a-f0-9]{12}$/.test(candidateId);

export const wonderCandidateModel = (
  candidate: FabricDiscoveryCandidate,
): WonderModel | undefined =>
  candidate.model === "dash" || candidate.model === "dot"
    ? candidate.model
    : undefined;

export const selectableWonderCandidates = (
  candidates: FabricDiscoveryCandidate[],
) =>
  candidates.filter(
    (candidate) =>
      candidate.status === "found" &&
      isWonderCandidateId(candidate.candidateId) &&
      wonderCandidateModel(candidate) !== undefined,
  );

export const wonderSelection = (
  candidate: FabricDiscoveryCandidate,
): WonderRobotSelection | undefined => {
  const model = wonderCandidateModel(candidate);
  return model === undefined || !isWonderCandidateId(candidate.candidateId)
    ? undefined
    : { candidateId: candidate.candidateId, model };
};

export const isWonderNode = (node: IntegrationNode): boolean =>
  node.pluginId === WONDER_PLUGIN_ID && wonderNodeModel(node) !== undefined;

export const wonderNodeModel = (
  node: IntegrationNode,
): WonderModel | undefined => {
  const model = node.metadata.model;
  return model === "dash" || model === "dot" ? model : undefined;
};

export const wonderControlAvailability = (
  node: IntegrationNode,
  sessionState: string,
  sessionArmed: boolean,
) => ({
  light: sessionState === "active",
  physical:
    sessionState === "active" && (node.simulated || sessionArmed === true),
  stop: sessionState !== "stopped",
});
