import type { IntegrationNode } from "@citxr/protocol";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { FabricDeviceIoPanel } from "./FabricDeviceIoPanel.js";
import { fabricTranslatorFor } from "./fabric-i18n.js";

describe("compact device input/output summary", () => {
  it("keeps live values visible while technical capabilities stay collapsed", () => {
    const node = {
      nodeId: "lego-1",
      displayName: "SPIKE Prime",
      connectionState: "connected",
      healthState: "healthy",
      publishedCapabilities: [],
      consumedCapabilities: [],
    } as unknown as IntegrationNode;
    const html = renderToStaticMarkup(
      <FabricDeviceIoPanel
        nodes={[node]}
        readings={[
          {
            key: "lego-1:battery",
            sourceNodeId: "lego-1",
            topic: "telemetry.battery.state",
            observedAt: "2026-08-25T04:00:00Z",
            values: [{ label: "battery", value: "82%" }],
          },
        ]}
        locale="en"
        t={fabricTranslatorFor("en")}
      />,
    );

    expect(html).toContain("<details");
    expect(html).not.toContain("<details open");
    expect(html).toContain("battery: 82%");
    expect(html).toContain("Inputs from device");
    expect(html).toContain("Outputs to device");
  });
});
