export const POWER_SET_CAPABILITY = "power.switch.set";
export const POWER_STATE_CAPABILITY = "power.switch.state";

interface SmartPlugNodeCapabilities {
  consumedCapabilities: readonly { name: string }[];
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
