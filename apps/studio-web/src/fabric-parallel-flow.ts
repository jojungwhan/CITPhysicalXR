import type { CoursePack } from "@citxr/protocol";
import { flowTargetRoles } from "@citxr/protocol/flow-target";

export interface FabricParallelOutput {
  flowId: string;
  role: string;
  action: string;
}

export interface FabricParallelFlowGroup {
  groupId: string;
  trigger: string;
  outputs: FabricParallelOutput[];
}

/** Build tutor-facing fan-out plans from the canonical course recipe. */
export function parallelFlowGroups(
  coursePack: Pick<CoursePack, "flows"> | undefined,
): FabricParallelFlowGroup[] {
  if (coursePack === undefined) return [];
  const groups = new Map<string, FabricParallelFlowGroup>();
  const seenOutputs = new Map<string, Set<string>>();

  coursePack.flows.forEach((flow) => {
    if (flow.parallelGroup === undefined || !flow.enabled) return;
    const current = groups.get(flow.parallelGroup) ?? {
      groupId: flow.parallelGroup,
      trigger: flow.trigger.event,
      outputs: [],
    };
    const seen = seenOutputs.get(flow.parallelGroup) ?? new Set<string>();
    for (const role of flowTargetRoles(flow.target)) {
      const key = `${role}\u0000${flow.command.action}`;
      if (!seen.has(key)) {
        current.outputs.push({
          flowId: flow.flowId,
          role,
          action: flow.command.action,
        });
        seen.add(key);
      }
    }
    groups.set(flow.parallelGroup, current);
    seenOutputs.set(flow.parallelGroup, seen);
  });

  return [...groups.values()];
}
