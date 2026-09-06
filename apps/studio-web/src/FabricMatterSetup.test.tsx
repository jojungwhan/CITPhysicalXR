import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { FabricDiscoveryCandidate } from "./fabric-client.js";
import { fabricTranslatorFor } from "./fabric-i18n.js";
import { FabricMatterSetup } from "./FabricMatterSetup.js";

const candidate = (
  candidateId: string,
  status: FabricDiscoveryCandidate["status"],
  diagnosticCode?: string,
): FabricDiscoveryCandidate => ({
  candidateId,
  displayName: candidateId,
  transport: "Local Matter controller",
  status,
  detail: "Diagnostic detail from the local controller.",
  ...(diagnosticCode === undefined ? {} : { diagnosticCode }),
});

describe("Matter plug setup feedback", () => {
  it("blocks commissioning and identifies a missing Bluetooth adapter", () => {
    const html = renderToStaticMarkup(
      <FabricMatterSetup
        candidates={[
          candidate("matter-controller-wifi", "ready"),
          candidate(
            "matter-controller-bluetooth",
            "setup_required",
            "MATTER_BLUETOOTH_ADAPTER_MISSING",
          ),
        ]}
        commissioning={false}
        configuringWifi={false}
        canConnect
        connected
        commissionError={null}
        onCommission={vi.fn(async () => true)}
        onConfigureWifi={vi.fn(async () => true)}
        t={fabricTranslatorFor("en")}
      />,
    );

    expect(html).toContain("Bluetooth setup required");
    expect(html).toContain(
      "No Bluetooth LE adapter is connected. Connect the adapter, then choose Find devices again.",
    );
    expect(html).toMatch(
      /<button[^>]*disabled=""[^>]*>Add another plug<\/button>/,
    );
  });

  it("renders the exact commissioning failure beside the Matter form", () => {
    const message =
      "The plug was reached, but it could not join the saved Wi-Fi.";
    const html = renderToStaticMarkup(
      <FabricMatterSetup
        candidates={[
          candidate("matter-controller-wifi", "ready"),
          candidate("matter-controller-bluetooth", "ready"),
        ]}
        commissioning={false}
        configuringWifi={false}
        canConnect
        connected
        commissionError={message}
        onCommission={vi.fn(async () => false)}
        onConfigureWifi={vi.fn(async () => true)}
        t={fabricTranslatorFor("en")}
      />,
    );

    expect(html).toContain('class="fabric-matter-error"');
    expect(html).toContain('role="alert"');
    expect(html).toContain(message);
  });

  it("allows an on-network setup-mode device when local Bluetooth is unavailable", () => {
    const html = renderToStaticMarkup(
      <FabricMatterSetup
        candidates={[
          candidate("matter-controller-wifi", "ready"),
          candidate(
            "matter-controller-bluetooth",
            "setup_required",
            "MATTER_BLUETOOTH_ADAPTER_MISSING",
          ),
          candidate("matter-on-network-plug", "found"),
        ]}
        commissioning={false}
        configuringWifi={false}
        canConnect
        connected
        commissionError={null}
        onCommission={vi.fn(async () => true)}
        onConfigureWifi={vi.fn(async () => true)}
        t={fabricTranslatorFor("en")}
      />,
    );

    const setupInput = html.match(
      /<input[^>]+placeholder="MT:… or 1234-567-8901"[^>]*>/,
    )?.[0];
    expect(html).toContain("On-network setup ready");
    expect(setupInput).toBeDefined();
    expect(setupInput).not.toContain("disabled");
  });
});
