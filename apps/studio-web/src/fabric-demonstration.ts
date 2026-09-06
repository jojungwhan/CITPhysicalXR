interface DemonstrationNodeIdentity {
  nodeId: string;
}

export const allDemonstrationNodeIds = <T extends DemonstrationNodeIdentity>(
  nodes: readonly T[],
): ReadonlySet<string> => new Set(nodes.map((node) => node.nodeId));

export const selectedDemonstrationNodes = <T extends DemonstrationNodeIdentity>(
  nodes: readonly T[],
  selectedNodeIds: ReadonlySet<string>,
): T[] => nodes.filter((node) => selectedNodeIds.has(node.nodeId));

export const toggledDemonstrationNodeIds = (
  selectedNodeIds: ReadonlySet<string>,
  nodeId: string,
  selected: boolean,
): ReadonlySet<string> => {
  const next = new Set(selectedNodeIds);
  if (selected) next.add(nodeId);
  else next.delete(nodeId);
  return next;
};
