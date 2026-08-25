import type { IntegrationNode } from "@citxr/protocol";

import {
  FLIGHT_MOVE_CAPABILITY,
  supportsManualTelloFlight,
} from "./fabric-drone.js";
import {
  SPHERO_NUDGE_CAPABILITY,
  SPHERO_STOP_CAPABILITY,
} from "./fabric-sphero-bolt.js";

export type SynchronizedMotionDirection =
  "forward" | "backward" | "left" | "right" | "stop";

export type SynchronizedInputKind = "g2" | "r1" | "meta" | "mindwave";

export interface SynchronizedMotionAssignment {
  role: string;
  node: IntegrationNode;
}

export interface SynchronizedMotionCommand {
  role: string;
  nodeId: string;
  action: string;
  parameters: Record<string, unknown>;
  kind: "ground" | "flight";
}

const inputModel: Readonly<Record<string, SynchronizedInputKind>> = {
  "even-realities-g2": "g2",
  "even-realities-r1": "r1",
  "meta-rayban": "meta",
  "mindwave-mobile2": "mindwave",
};

export function synchronizedInputKinds(
  nodes: readonly IntegrationNode[],
): ReadonlySet<SynchronizedInputKind> {
  return new Set(
    nodes.flatMap((node) => {
      if (node.connectionState !== "connected") return [];
      const model =
        typeof node.metadata.model === "string" ? node.metadata.model : "";
      const kind = inputModel[model];
      return kind === undefined ? [] : [kind];
    }),
  );
}

/**
 * Plan one independently auditable command per selected device. The caller
 * dispatches the plan concurrently; there is no compound vendor command.
 */
export function synchronizedMotionCommands({
  direction,
  groundRobots,
  drones,
  includeTello,
  flightConfirmed,
}: {
  direction: SynchronizedMotionDirection;
  groundRobots: readonly SynchronizedMotionAssignment[];
  drones: readonly SynchronizedMotionAssignment[];
  includeTello: boolean;
  flightConfirmed: boolean;
}): SynchronizedMotionCommand[] {
  const commands: SynchronizedMotionCommand[] = groundRobots.map(
    ({ role, node }) => ({
      role,
      nodeId: node.nodeId,
      action:
        direction === "stop" ? SPHERO_STOP_CAPABILITY : SPHERO_NUDGE_CAPABILITY,
      parameters: direction === "stop" ? {} : { direction },
      kind: "ground",
    }),
  );

  if (!includeTello || !flightConfirmed || direction === "stop") {
    return commands;
  }

  const telloDirection = direction === "backward" ? "back" : direction;
  for (const { role, node } of drones) {
    if (!supportsManualTelloFlight(node)) continue;
    commands.push({
      role,
      nodeId: node.nodeId,
      action: FLIGHT_MOVE_CAPABILITY,
      parameters: {
        direction: telloDirection,
        distanceCentimeters: 20,
        instructorPresent: true,
        flightAreaClear: true,
        emergencyPlanReady: true,
      },
      kind: "flight",
    });
  }
  return commands;
}
