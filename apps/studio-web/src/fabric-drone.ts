import type { IntegrationNode } from "@citxr/protocol";

export const FLIGHT_LAND_CAPABILITY = "mobility.flight.land";
export const FLIGHT_EMERGENCY_STOP_CAPABILITY =
  "mobility.flight.emergency_stop";
export const FLIGHT_TAKEOFF_CAPABILITY = "mobility.flight.takeoff";
export const FLIGHT_MOVE_CAPABILITY = "mobility.flight.move";
export const FLIGHT_ROTATE_CAPABILITY = "mobility.flight.rotate";

export const isSafetyDroneRole = (role: string) =>
  /^safety_drone_[1-8]$/.test(role);

export const isTelloNode = (node: IntegrationNode) => {
  const consumed = new Set(
    node.consumedCapabilities.map((capability) => capability.name),
  );
  return (
    node.pluginId === "cit.tello" &&
    consumed.has(FLIGHT_LAND_CAPABILITY) &&
    consumed.has(FLIGHT_EMERGENCY_STOP_CAPABILITY)
  );
};

/** Compatibility name retained while existing pages migrate to the full node. */
export const isSafeStateTelloNode = isTelloNode;

export const supportsManualTelloFlight = (node: IntegrationNode) => {
  const consumed = new Set(
    node.consumedCapabilities.map((capability) => capability.name),
  );
  return (
    isTelloNode(node) &&
    node.connectionState === "connected" &&
    node.healthState === "healthy" &&
    consumed.has(FLIGHT_TAKEOFF_CAPABILITY) &&
    consumed.has(FLIGHT_MOVE_CAPABILITY) &&
    consumed.has(FLIGHT_ROTATE_CAPABILITY)
  );
};

interface TelloControlSession {
  sessionId: string;
  state: string;
  armed?: boolean;
  updatedAt: string;
  roleBindings: readonly { role: string; nodeId: string }[];
}

const CONTROL_SESSION_STATE_PRIORITY: Readonly<Record<string, number>> = {
  active: 3,
  paused: 2,
  ready: 1,
  draft: 0,
};

export function preferredTelloControlSession<T extends TelloControlSession>(
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
          .filter(
            (binding) =>
              isSafetyDroneRole(binding.role) && connected.has(binding.nodeId),
          )
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
