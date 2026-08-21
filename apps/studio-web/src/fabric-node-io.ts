export type FabricNodeIoKind = "input" | "output" | "bidirectional";

type NodeCapabilityLists = {
  publishedCapabilities: readonly unknown[];
  consumedCapabilities: readonly unknown[];
};

/**
 * Classify a node by its relationship to the Fabric. Publishing is the input
 * side of an interaction; consuming commands is the output side. A node that
 * does both (for example glasses, robots, and coding agents) is bidirectional.
 */
export function classifyFabricNodeIo(
  node: NodeCapabilityLists,
): FabricNodeIoKind {
  const publishes = node.publishedCapabilities.length > 0;
  const consumes = node.consumedCapabilities.length > 0;

  if (publishes && consumes) return "bidirectional";
  if (consumes) return "output";
  return "input";
}
