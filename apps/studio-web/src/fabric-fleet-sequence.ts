import type { IntegrationNode } from "@citxr/protocol";

import type { StoredFabricEvent } from "./fabric-client.js";

export const FLEET_SEQUENCE_INTENT_CAPABILITY =
  "interaction.intent.flight_sequence_start";
export const FLEET_SEQUENCE_ARM_CAPABILITY =
  "mobility.flight.fleet_sequence.arm";
export const FLEET_SEQUENCE_START_CAPABILITY =
  "mobility.flight.fleet_sequence.start";
export const FLEET_SEQUENCE_STOP_CAPABILITY =
  "mobility.flight.fleet_sequence.stop";
export const FLEET_SEQUENCE_STATUS_CAPABILITY =
  "telemetry.flight.fleet_sequence.status";

export interface FleetSequenceDrone {
  id: string;
  label: string;
  connection: string;
  flight: string;
  batteryPercent?: number;
}

export interface FleetSequenceStatus {
  available: boolean;
  active: boolean;
  armed: boolean;
  phase: string;
  progress: number;
  message: string;
  error?: string;
  triggeredBy?: string;
  selectedDroneIds: string[];
  launchedDroneIds: string[];
  landRequestedDroneIds: string[];
  availableDrones: FleetSequenceDrone[];
  simulated: boolean;
  observedAt: string;
}

export interface FleetSequenceSettings {
  droneIds: string[];
  allowedSourceNodeIds: string[];
  launchIntervalSeconds: number;
  minimumBatteryPercent: number;
  instructorPresent: boolean;
  flightAreaClear: boolean;
  emergencyPlanReady: boolean;
  independentRoutesConfirmed: boolean;
}

export const isFleetSequenceControllerNode = (node: IntegrationNode) => {
  const consumed = new Set(
    node.consumedCapabilities.map((capability) => capability.name),
  );
  return (
    node.pluginId === "cit.brain2devices-fleet" &&
    consumed.has(FLEET_SEQUENCE_ARM_CAPABILITY) &&
    consumed.has(FLEET_SEQUENCE_START_CAPABILITY) &&
    consumed.has(FLEET_SEQUENCE_STOP_CAPABILITY) &&
    ![...consumed].some((capability) =>
      /(?:^|\.)(?:takeoff|move|rotate)$/.test(capability),
    )
  );
};

export const isFleetSequenceInputNode = (node: IntegrationNode) =>
  node.publishedCapabilities.some(
    (capability) => capability.name === FLEET_SEQUENCE_INTENT_CAPABILITY,
  );

export const assignedFleetSequenceInputNodes = (
  nodes: readonly IntegrationNode[],
  roleBindings: readonly { role: string; nodeId: string }[],
): IntegrationNode[] => {
  const boundNodeIds = new Set(roleBindings.map((binding) => binding.nodeId));
  return nodes.filter(
    (node) => boundNodeIds.has(node.nodeId) && isFleetSequenceInputNode(node),
  );
};

interface FleetSequenceControlSession {
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

/** Resolve the adapter-owned fleet session without coupling controls to the lesson picker. */
export function preferredFleetSequenceControlSession<
  T extends FleetSequenceControlSession,
>(sessions: readonly T[], controllerNodeIds: readonly string[]): T | undefined {
  const connectedControllers = new Set(controllerNodeIds);
  return sessions
    .flatMap((session) => {
      const statePriority = CONTROL_SESSION_STATE_PRIORITY[session.state];
      if (statePriority === undefined) return [];
      const binding = session.roleBindings.find(
        (candidate) =>
          candidate.role === "fleet_sequence_controller" &&
          connectedControllers.has(candidate.nodeId),
      );
      if (binding === undefined) return [];
      return [
        {
          session,
          statePriority,
          armedPriority: session.armed === true ? 1 : 0,
          updatedAt: Date.parse(session.updatedAt) || 0,
        },
      ];
    })
    .sort(
      (left, right) =>
        right.statePriority - left.statePriority ||
        right.armedPriority - left.armedPriority ||
        right.updatedAt - left.updatedAt,
    )[0]?.session;
}

export const latestFleetSequenceStatus = (
  events: StoredFabricEvent[],
  nodeId: string | undefined,
): FleetSequenceStatus | undefined => {
  if (nodeId === undefined) return undefined;
  const event = events
    .filter(
      (item) =>
        item.event.sourceNodeId === nodeId &&
        item.event.topic === FLEET_SEQUENCE_STATUS_CAPABILITY,
    )
    .at(-1);
  if (event === undefined) return undefined;
  const payload = event.event.payload as Record<string, unknown>;
  return {
    available: payload.available === true,
    active: payload.active === true,
    armed: payload.armed === true,
    phase: text(payload.phase, "unknown"),
    progress: numberBetween(payload.progress, 0, 1, 0),
    message: text(payload.message, "Waiting for fleet status"),
    ...(typeof payload.error === "string" && payload.error
      ? { error: payload.error }
      : {}),
    ...(typeof payload.triggeredBy === "string" && payload.triggeredBy
      ? { triggeredBy: payload.triggeredBy }
      : {}),
    selectedDroneIds: stringArray(payload.selectedDroneIds),
    launchedDroneIds: stringArray(payload.launchedDroneIds),
    landRequestedDroneIds: stringArray(payload.landRequestedDroneIds),
    availableDrones: droneArray(payload.availableDrones),
    simulated: payload.simulated === true,
    observedAt: event.event.timestamp,
  };
};

const droneArray = (value: unknown): FleetSequenceDrone[] => {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item !== "object" || item === null || Array.isArray(item))
      return [];
    const value = item as Record<string, unknown>;
    if (typeof value.id !== "string" || !value.id) return [];
    const batteryPercent = numberBetween(
      value.batteryPercent,
      0,
      100,
      Number.NaN,
    );
    return [
      {
        id: value.id,
        label: text(value.label, value.id),
        connection: text(value.connection, "unknown"),
        flight: text(value.flight, "unknown"),
        ...(Number.isFinite(batteryPercent) ? { batteryPercent } : {}),
      },
    ];
  });
};

const stringArray = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter(
        (item): item is string => typeof item === "string" && item.length > 0,
      )
    : [];

const numberBetween = (
  value: unknown,
  minimum: number,
  maximum: number,
  fallback: number,
) =>
  typeof value === "number" && Number.isFinite(value)
    ? Math.min(maximum, Math.max(minimum, value))
    : fallback;

const text = (value: unknown, fallback: string) =>
  typeof value === "string" && value.length > 0 ? value : fallback;
