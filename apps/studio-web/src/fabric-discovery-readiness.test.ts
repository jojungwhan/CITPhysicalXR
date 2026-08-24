import { describe, expect, it } from "vitest";

import {
  connectedFabricDeviceCount,
  fabricDiscoveryReadiness,
  groupFabricIntegrationsByReadiness,
} from "./fabric-discovery-readiness.js";

describe("Fabric discovery readiness", () => {
  it("puts connected hardware first, actionable hardware next, and the rest last", () => {
    expect(fabricDiscoveryReadiness("connected")).toBe("connected");
    expect(fabricDiscoveryReadiness("found")).toBe("available");
    expect(fabricDiscoveryReadiness("ready")).toBe("available");
    expect(fabricDiscoveryReadiness("setup_required")).toBe("unavailable");
    expect(fabricDiscoveryReadiness("not_found")).toBe("unavailable");
    expect(fabricDiscoveryReadiness("unavailable")).toBe("unavailable");
    expect(fabricDiscoveryReadiness("not_scanned")).toBe("unavailable");
  });

  it("keeps the most actionable status first within each readiness tier", () => {
    const grouped = groupFabricIntegrationsByReadiness([
      item("not-found", "not_found"),
      item("host-ready", "ready"),
      item("connected", "connected"),
      item("setup", "setup_required"),
      item("hardware-found", "found"),
      item("not-scanned", "not_scanned"),
    ]);

    expect(grouped.connected.map(({ integrationId }) => integrationId)).toEqual(
      ["connected"],
    );
    expect(grouped.available.map(({ integrationId }) => integrationId)).toEqual(
      ["hardware-found", "host-ready"],
    );
    expect(
      grouped.unavailable.map(({ integrationId }) => integrationId),
    ).toEqual(["setup", "not-found", "not-scanned"]);
  });

  it("counts concrete connected nodes instead of only integration cards", () => {
    expect(
      connectedFabricDeviceCount([
        {
          status: "connected",
          connectedNodeIds: ["matter-a", "matter-b"],
        },
        { status: "connected", connectedNodeIds: ["g2-a"] },
        { status: "ready", connectedNodeIds: [] },
      ]),
    ).toBe(3);
  });
});

const item = (
  integrationId: string,
  status:
    | "not_scanned"
    | "connected"
    | "found"
    | "ready"
    | "setup_required"
    | "not_found"
    | "unavailable",
) => ({ integrationId, status });
