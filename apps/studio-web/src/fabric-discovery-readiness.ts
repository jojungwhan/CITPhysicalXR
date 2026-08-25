import type {
  FabricDiscoveryStatus,
  FabricIntegrationDiscovery,
} from "./fabric-client.js";

export type FabricDiscoveryReadiness =
  "connected" | "available" | "unavailable";

const READINESS_BY_STATUS: Record<
  FabricDiscoveryStatus,
  FabricDiscoveryReadiness
> = {
  connected: "connected",
  found: "available",
  ready: "available",
  setup_required: "unavailable",
  not_found: "unavailable",
  unavailable: "unavailable",
  not_scanned: "unavailable",
};

const STATUS_PRIORITY: Record<FabricDiscoveryStatus, number> = {
  connected: 0,
  found: 1,
  ready: 2,
  setup_required: 3,
  not_found: 4,
  unavailable: 5,
  not_scanned: 6,
};

export const fabricDiscoveryReadiness = (
  status: FabricDiscoveryStatus,
): FabricDiscoveryReadiness => READINESS_BY_STATUS[status];

/**
 * Present classroom hardware by immediate usefulness. I/O direction remains a
 * card attribute; it must not hide a live device below disconnected hardware.
 */
export function groupFabricIntegrationsByReadiness<
  T extends Pick<FabricIntegrationDiscovery, "status">,
>(integrations: readonly T[]): Record<FabricDiscoveryReadiness, T[]> {
  const groups: Record<FabricDiscoveryReadiness, T[]> = {
    connected: [],
    available: [],
    unavailable: [],
  };
  integrations.forEach((integration) =>
    groups[fabricDiscoveryReadiness(integration.status)].push(integration),
  );
  Object.values(groups).forEach((items) =>
    items.sort(
      (left, right) =>
        STATUS_PRIORITY[left.status] - STATUS_PRIORITY[right.status],
    ),
  );
  return groups;
}

export const connectedFabricDeviceCount = (
  integrations: readonly Pick<
    FabricIntegrationDiscovery,
    "status" | "connectedNodeIds"
  >[],
): number =>
  integrations.reduce(
    (count, integration) =>
      integration.status === "connected"
        ? count + Math.max(1, integration.connectedNodeIds.length)
        : count,
    0,
  );

export const fabricDiscoveryTierOpenByDefault = (
  kind: FabricDiscoveryReadiness,
  connectedIntegrationCount: number,
): boolean =>
  (kind === "connected" && connectedIntegrationCount > 0) ||
  (kind === "available" && connectedIntegrationCount === 0);
