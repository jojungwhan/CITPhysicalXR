import type { IntegrationNode } from "@citxr/protocol";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { FabricIntegrationDiscovery } from "./fabric-client.js";
import { FabricDiscoveryCard } from "./FabricConsole.js";
import { fabricTranslatorFor } from "./fabric-i18n.js";

describe("connected device card density", () => {
  it("keeps primary controls first and consolidates connection diagnostics", () => {
    const integration: FabricIntegrationDiscovery = {
      integrationId: "tello-drones",
      displayName: "DJI / Ryze Tello drones",
      category: "drone",
      ioType: "bidirectional",
      status: "connected",
      summary: "One Tello is connected.",
      connectionMethod: "One Wi-Fi route per aircraft",
      connectedNodeIds: ["tello-01"],
      candidates: [
        {
          candidateId: "route-1",
          displayName: "TELLO-58C5B7",
          transport: "Tello Wi-Fi",
          status: "found",
          detail: "Visible on the dedicated USB Wi-Fi route.",
        },
      ],
      setupSteps: ["Keep the aircraft grounded while connecting."],
      actionId: "brain2devices.tello.connect-all",
      actionLabel: "Connect all available grounded drones",
      requiresGroundedConfirmation: true,
      safetyNote: "Connection does not issue a flight command.",
    };
    const node = {
      nodeId: "tello-01",
      displayName: "DJI / Ryze Tello",
      connectionState: "connected",
      healthState: "healthy",
      publishedCapabilities: [],
      consumedCapabilities: [],
    } as unknown as IntegrationNode;
    const html = renderToStaticMarkup(
      <FabricDiscoveryCard
        integration={integration}
        connectedNodes={[node]}
        readings={[]}
        inlineControls={<button type="button">Primary flight control</button>}
        locale="en"
        t={fabricTranslatorFor("en")}
        busy={null}
        actionFeedback={{ tone: "success", message: "First Tello connected." }}
        canConnect
        groundedConfirmed
        onScan={vi.fn()}
        onConnect={vi.fn()}
        onCopySetup={vi.fn()}
        onMatterCommission={vi.fn(async () => true)}
        onMatterWifiConfigure={vi.fn(async () => true)}
        onLegoConnect={vi.fn()}
        onWonderConnect={vi.fn()}
        onSpheroConnect={vi.fn()}
      />,
    );

    expect(html.indexOf("Primary flight control")).toBeLessThan(
      html.indexOf("Live input and output"),
    );
    expect(html).not.toContain("fabric-connected-devices");
    expect(html.indexOf("Connection details")).toBeLessThan(
      html.indexOf("TELLO-58C5B7"),
    );
    expect(html).toContain("First Tello connected.");
  });
});
