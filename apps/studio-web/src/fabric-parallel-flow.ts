import type { CoursePack } from "@citxr/protocol";

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

  coursePack.flows.forEach((flow) => {
    if (flow.parallelGroup === undefined || !flow.enabled) return;
    const current = groups.get(flow.parallelGroup) ?? {
      groupId: flow.parallelGroup,
      trigger: flow.trigger.event,
      outputs: [],
    };
    const alreadyShown = current.outputs.some(
      (output) =>
        output.role === flow.target.role &&
        output.action === flow.command.action,
    );
    if (!alreadyShown) {
      current.outputs.push({
        flowId: flow.flowId,
        role: flow.target.role,
        action: flow.command.action,
      });
    }
    groups.set(flow.parallelGroup, current);
  });

  return [...groups.values()];
}
