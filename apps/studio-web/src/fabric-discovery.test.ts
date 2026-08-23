import { describe, expect, it } from "vitest";

import type { FabricDiscoveryCandidate } from "./fabric-client.js";
import { discoveryLinkLabel } from "./fabric-discovery.js";
import { fabricTranslatorFor } from "./fabric-i18n.js";

const candidate = (
  linkState?: FabricDiscoveryCandidate["linkState"],
): FabricDiscoveryCandidate => ({
  candidateId: "candidate-1",
  displayName: "Classroom device",
  transport: "USB",
  status: "found",
  detail: "Read-only discovery evidence.",
  ...(linkState === undefined ? {} : { linkState }),
});

describe("discoveryLinkLabel", () => {
  it("distinguishes current links from visibility and configuration", () => {
    expect(discoveryLinkLabel(candidate("attached"))).toBe("Attached now");
    expect(discoveryLinkLabel(candidate("connected"))).toBe("Connected now");
    expect(discoveryLinkLabel(candidate("recently_active"))).toBe(
      "Recently active",
    );
    expect(discoveryLinkLabel(candidate("visible"))).toBe("Visible nearby");
    expect(discoveryLinkLabel(candidate("provisioned"))).toBe("Configured");
  });

  it("does not invent link evidence for older discovery reports", () => {
    expect(discoveryLinkLabel(candidate())).toBeUndefined();
  });

  it("uses the selected interface language", () => {
    expect(
      discoveryLinkLabel(candidate("visible"), fabricTranslatorFor("ko")),
    ).toBe("근처에서 보임");
  });
});
