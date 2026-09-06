export const POWER_SET_CAPABILITY = "power.switch.set";
export const POWER_STATE_CAPABILITY = "power.switch.state";
export const SMART_PLUG_SELECTION_STORAGE_KEY =
  "citxr.fabric.smartPlugSelection.v1";

type SmartPlugSelectionStorage = Pick<
  Storage,
  "getItem" | "setItem" | "removeItem"
>;

interface SmartPlugNodeCapabilities {
  consumedCapabilities: readonly { name: string }[];
}

interface SmartPlugNodeIdentity extends SmartPlugNodeCapabilities {
  nodeId: string;
  connectionState?: string;
  metadata?: Readonly<Record<string, unknown>>;
}

export interface MatterSetupCodeMapping {
  setupCode: string;
  matterNodeIds: readonly string[];
  name?: string;
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

interface SmartPlugHealthNode {
  lastSeenAt: string;
  metadata?: Readonly<Record<string, unknown>>;
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

const MAX_SMART_PLUG_CONTROLS = 8;

const validSavedSmartPlugNodeId = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0 && value.length <= 256;

const browserLocalStorage = (): SmartPlugSelectionStorage | undefined => {
  if (typeof window === "undefined") return undefined;
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
};

/** Restore this browser's selected plug identities without trusting storage. */
export function readSmartPlugSelection(
  storage: SmartPlugSelectionStorage | undefined = browserLocalStorage(),
): ReadonlySet<string> {
  if (storage === undefined) return new Set();
  try {
    const saved = storage.getItem(SMART_PLUG_SELECTION_STORAGE_KEY);
    if (saved === null) return new Set();
    const parsed: unknown = JSON.parse(saved);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(
      parsed
        .filter(validSavedSmartPlugNodeId)
        .slice(0, MAX_SMART_PLUG_CONTROLS),
    );
  } catch {
    return new Set();
  }
}

/** Save only UI selection; no plug credential or power state is stored. */
export function saveSmartPlugSelection(
  nodeIds: Iterable<string>,
  storage: SmartPlugSelectionStorage | undefined = browserLocalStorage(),
): void {
  if (storage === undefined) return;
  const normalized = Array.from(new Set(nodeIds))
    .filter(validSavedSmartPlugNodeId)
    .slice(0, MAX_SMART_PLUG_CONTROLS);
  try {
    if (normalized.length === 0) {
      storage.removeItem(SMART_PLUG_SELECTION_STORAGE_KEY);
    } else {
      storage.setItem(
        SMART_PLUG_SELECTION_STORAGE_KEY,
        JSON.stringify(normalized),
      );
    }
  } catch {
    // Browser privacy settings or a full quota must not break plug controls.
  }
}

export function retainKnownSmartPlugSelection(
  selectedNodeIds: ReadonlySet<string>,
  knownNodeIds: ReadonlySet<string>,
): ReadonlySet<string> {
  return new Set(
    Array.from(selectedNodeIds).filter((nodeId) => knownNodeIds.has(nodeId)),
  );
}

/** Build the exact bounded role plan shared by the visible controls and session. */
export function smartPlugControlPlan<T extends SmartPlugNodeIdentity>(
  nodes: readonly T[],
): AssignedSmartPlugNode<T>[] {
  return nodes
    .filter(isSmartPlugNode)
    .sort(
      (left, right) =>
        smartPlugAvailabilityRank(left) - smartPlugAvailabilityRank(right),
    )
    .slice(0, MAX_SMART_PLUG_CONTROLS)
    .map((node, index) => ({
      role: index === 0 ? "classroom_plug" : `classroom_plug_${index + 1}`,
      node,
    }));
}

const smartPlugAvailabilityRank = (node: SmartPlugNodeIdentity): number =>
  node.connectionState === "connected" || node.connectionState === "degraded"
    ? 0
    : 1;

const matterNodeId = (node: SmartPlugNodeIdentity): string | undefined => {
  const value = node.metadata?.matterNodeId;
  return typeof value === "string" && /^[1-9][0-9]*$/.test(value)
    ? value
    : undefined;
};

/** Hide an older controller record after the same physical plug is recommissioned. */
export function currentSmartPlugNodes<T extends SmartPlugNodeIdentity>(
  nodes: readonly T[],
  setupCodes: readonly MatterSetupCodeMapping[],
): T[] {
  const byMatterNodeId = new Map(
    nodes.flatMap((node) => {
      const id = matterNodeId(node);
      return id === undefined ? [] : ([[id, node]] as const);
    }),
  );
  const superseded = new Set<string>();
  for (const mapping of setupCodes) {
    const mapped = mapping.matterNodeIds.flatMap((id) => {
      const node = byMatterNodeId.get(id);
      return node === undefined ? [] : [node];
    });
    if (mapped.length < 2) continue;
    const current =
      mapped.findLast((node) => smartPlugAvailabilityRank(node) === 0) ??
      mapped.at(-1);
    for (const node of mapped) {
      if (node !== current) superseded.add(node.nodeId);
    }
  }
  return nodes.filter((node) => !superseded.has(node.nodeId));
}

export const setupCodeMappingForMatterNode = (
  node: SmartPlugNodeIdentity,
  setupCodes: readonly MatterSetupCodeMapping[],
): MatterSetupCodeMapping | undefined => {
  const id = matterNodeId(node);
  return id === undefined
    ? undefined
    : setupCodes.find((mapping) => mapping.matterNodeIds.includes(id));
};

export const setupCodeForMatterNode = (
  node: SmartPlugNodeIdentity,
  setupCodes: readonly MatterSetupCodeMapping[],
): string | undefined =>
  setupCodeMappingForMatterNode(node, setupCodes)?.setupCode;

export const formatMatterSetupCode = (setupCode: string): string => {
  const digits = setupCode.replace(/\D/g, "");
  return digits.length === 11
    ? `${digits.slice(0, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}`
    : setupCode;
};

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

export const smartPlugStateFromHealth = (
  node: SmartPlugHealthNode,
): SmartPlugState | undefined => {
  const metrics = node.metadata?.healthMetrics;
  if (
    metrics === null ||
    typeof metrics !== "object" ||
    Array.isArray(metrics)
  ) {
    return undefined;
  }
  const on = (metrics as Readonly<Record<string, unknown>>).on;
  if (typeof on !== "boolean" || node.lastSeenAt.trim() === "") {
    return undefined;
  }
  return {
    on,
    observedAt: node.lastSeenAt,
  };
};
