import type { IntegrationNode } from "@citxr/protocol";

import type { StoredFabricEvent } from "./fabric-client.js";

export const BRAIN_DEMO_ARM_CAPABILITY = "mobility.flight.brain_demo.arm";
export const BRAIN_DEMO_STOP_CAPABILITY = "mobility.flight.brain_demo.stop";
export const BRAIN_DEMO_STATUS_CAPABILITY =
  "telemetry.flight.brain_demo.status";

export interface BrainDemoSettings {
  attentionEnabled: boolean;
  attentionThreshold: number;
  meditationEnabled: boolean;
  meditationThreshold: number;
  blinkEnabled: boolean;
  blinkThreshold: number;
  dwellSeconds: number;
  instructorPresent: boolean;
  flightAreaClear: boolean;
  emergencyPlanReady: boolean;
}

export interface BrainDemoStatus {
  available: boolean;
  active: boolean;
  armed: boolean;
  phase: string;
  progress: number;
  message: string;
  error?: string;
  triggeredBy?: string;
  demoRunning: boolean;
  simulated: boolean;
  observedAt: string;
}

export const isBrainDemoControllerNode = (node: IntegrationNode) => {
  const consumed = new Set(
    node.consumedCapabilities.map((capability) => capability.name),
  );
  return (
    node.pluginId === "cit.brain2devices-demo" &&
    consumed.has(BRAIN_DEMO_ARM_CAPABILITY) &&
    consumed.has(BRAIN_DEMO_STOP_CAPABILITY) &&
    ![...consumed].some((capability) =>
      /(?:^|\.)(?:takeoff|move|rotate)$/.test(capability),
    )
  );
};

export const latestBrainDemoStatus = (
  events: StoredFabricEvent[],
  nodeId: string | undefined,
): BrainDemoStatus | undefined => {
  if (nodeId === undefined) return undefined;
  const event = events
    .filter(
      (item) =>
        item.event.sourceNodeId === nodeId &&
        item.event.topic === BRAIN_DEMO_STATUS_CAPABILITY,
    )
    .at(-1);
  if (event === undefined) return undefined;
  const payload = event.event.payload as Record<string, unknown>;
  const progress = numberBetween(payload.progress, 0, 1, 0);
  return {
    available: payload.available === true,
    active: payload.active === true,
    armed: payload.armed === true,
    phase: text(payload.phase, "unknown"),
    progress,
    message: text(payload.message, "Waiting for demo status"),
    ...(typeof payload.error === "string" && payload.error
      ? { error: payload.error }
      : {}),
    ...(typeof payload.triggeredBy === "string" && payload.triggeredBy
      ? { triggeredBy: payload.triggeredBy }
      : {}),
    demoRunning: payload.demoRunning === true,
    simulated: payload.simulated === true,
    observedAt: event.event.timestamp,
  };
};

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
