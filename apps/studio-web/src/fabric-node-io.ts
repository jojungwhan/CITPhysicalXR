export type FabricNodeIoKind = "input" | "output" | "bidirectional";

type NodeConnection = {
  connectionState: string;
};

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

/**
 * Group discovery/catalog entries before an adapter has registered concrete
 * capabilities. Once connected, `classifyFabricNodeIo` is authoritative.
 */
export function groupFabricIntegrationsByIo<
  T extends { ioType: FabricNodeIoKind },
>(integrations: readonly T[]): Record<FabricNodeIoKind, T[]> {
  const groups: Record<FabricNodeIoKind, T[]> = {
    input: [],
    bidirectional: [],
    output: [],
  };
  integrations.forEach((integration) =>
    groups[integration.ioType].push(integration),
  );
  return groups;
}

/** Group course roles without making older third-party recipes invalid. */
export function groupFabricCourseRolesByIo<
  T extends { ioType?: FabricNodeIoKind },
>(roles: readonly T[]): Record<FabricNodeIoKind, T[]> {
  const groups: Record<FabricNodeIoKind, T[]> = {
    input: [],
    bidirectional: [],
    output: [],
  };
  roles.forEach((role) => groups[role.ioType ?? "bidirectional"].push(role));
  return groups;
}

/** Only live or explicitly degraded adapters belong in classroom controls. */
export function isAvailableFabricNode(node: NodeConnection): boolean {
  return (
    node.connectionState === "connected" || node.connectionState === "degraded"
  );
}
