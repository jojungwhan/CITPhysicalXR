import type { IntegrationNode } from "@citxr/protocol";

import type {
  FabricDiscoveryCandidate,
  SpheroBoltSelection,
} from "./fabric-client.js";

export const SPHERO_PLUGIN_ID = "cit.sphero-bolt";
export const SPHERO_LIGHT_CAPABILITY = "robot.light.set";
export const SPHERO_VELOCITY_CAPABILITY = "mobility.ground.set_velocity";
export const SPHERO_STOP_CAPABILITY = "mobility.ground.stop";
export const SPHERO_AIM_CAPABILITY = "sphero.aim.reset";
export const SPHERO_NUDGE_METERS_PER_SECOND = 0.2;

export const spheroNudgeVelocity = (forward: number, right: number) => ({
  forwardMetersPerSecond: forward * SPHERO_NUDGE_METERS_PER_SECOND,
  rightMetersPerSecond: right * SPHERO_NUDGE_METERS_PER_SECOND,
  clockwiseRadiansPerSecond: 0,
});

interface SpheroControlSession {
  sessionId: string;
  state: string;
  armed?: boolean;
  updatedAt: string;
  roleBindings: readonly { role: string; nodeId: string }[];
}

export const isSpheroCandidateId = (candidateId: string): boolean =>
  /^sphero-[a-f0-9]{12}$/.test(candidateId);

export const selectableSpheroCandidates = (
  candidates: FabricDiscoveryCandidate[],
) =>
  candidates.filter(
    (candidate) =>
      candidate.status === "found" &&
      candidate.model === "sphero-bolt" &&
      /^SB-[0-9A-Z]{4}$/i.test(candidate.displayName) &&
      isSpheroCandidateId(candidate.candidateId),
  );

export const spheroSelection = (
  candidate: FabricDiscoveryCandidate,
): SpheroBoltSelection | undefined =>
  candidate.model === "sphero-bolt" &&
  isSpheroCandidateId(candidate.candidateId)
    ? { candidateId: candidate.candidateId }
    : undefined;

export const isSpheroNode = (node: IntegrationNode): boolean =>
  node.pluginId === SPHERO_PLUGIN_ID && node.metadata.model === "sphero-bolt";

const CONTROL_SESSION_STATE_PRIORITY: Readonly<Record<string, number>> = {
  active: 3,
  paused: 2,
  ready: 1,
  draft: 0,
};

/** Select a reusable lesson context without coupling BOLT to one course pack. */
export function preferredSpheroControlSession<T extends SpheroControlSession>(
  sessions: readonly T[],
  connectedNodeIds: readonly string[],
): T | undefined {
  const connected = new Set(connectedNodeIds);
  return sessions
    .flatMap((session) => {
      const statePriority = CONTROL_SESSION_STATE_PRIORITY[session.state];
      if (statePriority === undefined) return [];
      const assignedNodeCount = new Set(
        session.roleBindings
          .filter((binding) => connected.has(binding.nodeId))
          .map((binding) => binding.nodeId),
      ).size;
      if (assignedNodeCount === 0) return [];
      return [
        {
          session,
          assignedNodeCount,
          statePriority,
          armedPriority: session.armed === true ? 1 : 0,
          updatedAt: Date.parse(session.updatedAt) || 0,
        },
      ];
    })
    .sort(
      (left, right) =>
        right.assignedNodeCount - left.assignedNodeCount ||
        right.statePriority - left.statePriority ||
        right.armedPriority - left.armedPriority ||
        right.updatedAt - left.updatedAt,
    )[0]?.session;
}

export const spheroControlAvailability = (
  node: IntegrationNode,
  sessionState: string,
  sessionArmed: boolean,
) => ({
  light: sessionState === "active",
  physical:
    sessionState === "active" && (node.simulated || sessionArmed === true),
  stop: sessionState !== "stopped",
});
