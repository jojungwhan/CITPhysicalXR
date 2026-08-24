export const POWER_SET_CAPABILITY = "power.switch.set";
export const POWER_STATE_CAPABILITY = "power.switch.state";

interface SmartPlugNodeCapabilities {
  consumedCapabilities: readonly { name: string }[];
}

interface SmartPlugNodeIdentity extends SmartPlugNodeCapabilities {
  nodeId: string;
}

interface SmartPlugRoleBinding {
  role: string;
  nodeId: string;
}

interface SmartPlugControlSession {
  sessionId: string;
  coursePackId: string;
  state: string;
  updatedAt: string;
  roleBindings: readonly SmartPlugRoleBinding[];
}

export interface AssignedSmartPlugNode<T extends SmartPlugNodeIdentity> {
  role: string;
  node: T;
}

interface SmartPlugStoredEvent {
  event: {
    sourceNodeId: string;
    topic: string;
    timestamp: string;
    payload: Record<string, unknown>;
  };
}

export interface SmartPlugState {
  on: boolean;
  observedAt: string;
  source?: string;
}

export const isSmartPlugNode = (node: SmartPlugNodeCapabilities): boolean =>
  node.consumedCapabilities.some(
    (capability) => capability.name === POWER_SET_CAPABILITY,
  );

export const isSmartPlugRole = (role: string): boolean =>
  /^classroom_plug(?:_[2-8])?$/.test(role);

export function assignedSmartPlugNodes<T extends SmartPlugNodeIdentity>(
  bindings: readonly SmartPlugRoleBinding[],
  nodes: readonly T[],
): AssignedSmartPlugNode<T>[] {
  return bindings.flatMap((binding) => {
    if (!isSmartPlugRole(binding.role)) return [];
    const node = nodes.find(
      (candidate) =>
        candidate.nodeId === binding.nodeId && isSmartPlugNode(candidate),
    );
    return node === undefined ? [] : [{ role: binding.role, node }];
  });
}

const CONTROL_SESSION_STATE_PRIORITY: Readonly<Record<string, number>> = {
  active: 3,
  paused: 2,
  ready: 1,
  draft: 0,
};

/** Select the safest reusable lesson context that exposes the most live plugs. */
export function preferredSmartPlugControlSession<
  T extends SmartPlugControlSession,
>(sessions: readonly T[], connectedNodeIds: readonly string[]): T | undefined {
  const connected = new Set(connectedNodeIds);
  return sessions
    .flatMap((session) => {
      const statePriority = CONTROL_SESSION_STATE_PRIORITY[session.state];
      if (
        session.coursePackId !== "smart-plug-control" ||
        statePriority === undefined
      ) {
        return [];
      }
      const assignedNodeCount = new Set(
        session.roleBindings
          .filter(
            (binding) =>
              isSmartPlugRole(binding.role) && connected.has(binding.nodeId),
          )
          .map((binding) => binding.nodeId),
      ).size;
      if (assignedNodeCount === 0) return [];
      return [
        {
          session,
          assignedNodeCount,
          statePriority,
          updatedAt: Date.parse(session.updatedAt) || 0,
        },
      ];
    })
    .sort(
      (left, right) =>
        right.assignedNodeCount - left.assignedNodeCount ||
        right.statePriority - left.statePriority ||
        right.updatedAt - left.updatedAt,
    )[0]?.session;
}

const SWITCHABLE_LOAD_VISION_LABELS = new Set(["lamp", "light", "smart plug"]);

export const isSwitchableLoadVisionLabel = (label: string): boolean =>
  SWITCHABLE_LOAD_VISION_LABELS.has(label.trim().toLowerCase());

export const latestSmartPlugState = (
  events: readonly SmartPlugStoredEvent[],
  nodeId: string | undefined,
): SmartPlugState | undefined => {
  if (nodeId === undefined) return undefined;
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index]?.event;
    if (
      event?.sourceNodeId !== nodeId ||
      event.topic !== POWER_STATE_CAPABILITY
    ) {
      continue;
    }
    const on = event.payload.on;
    if (typeof on !== "boolean") continue;
    const source = event.payload.source;
    return {
      on,
      observedAt: event.timestamp,
      ...(typeof source === "string" ? { source } : {}),
    };
  }
  return undefined;
};
