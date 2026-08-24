import { describe, expect, it } from "vitest";

import type { FabricIntegrationDiscovery } from "./fabric-client.js";
import {
  fabricCatalog,
  fabricMessageKeys,
  fabricRoleText,
  fabricTranslatorFor,
  localizeFabricIntegration,
  translateFabric,
} from "./fabric-i18n.js";

describe("Fabric classroom i18n", () => {
  it("ships a complete non-placeholder Korean catalog", () => {
    const english = fabricCatalog("en");
    const korean = fabricCatalog("ko");
    expect(Object.keys(korean)).toEqual(Object.keys(english));

    const intentionallyShared = new Set([
      "language.ko",
      "language.en",
      "leap.eyebrow",
      "matter.placeholder",
    ]);
    for (const key of fabricMessageKeys()) {
      expect(korean[key].trim(), `ko.${key}`).not.toBe("");
      expect(korean[key], `ko.${key}`).not.toBe(key);
      if (!intentionallyShared.has(key)) {
        expect(korean[key], `ko.${key}`).not.toBe(english[key]);
      }
      expect(
        new Set(korean[key].match(/\{[a-z]+\}/gi) ?? []),
        `ko.${key}`,
      ).toEqual(new Set(english[key].match(/\{[a-z]+\}/gi) ?? []));
    }
  });

  it("interpolates tutor-facing Korean guidance", () => {
    expect(translateFabric("ko", "guide.connect.title", { count: 2 })).toBe(
      "장치 2대 더 연결",
    );
    expect(translateFabric("en", "guide.connect.title", { count: 2 })).toBe(
      "Connect 2 more device(s)",
    );
  });

  it("localizes discovery copy without changing operational identifiers", () => {
    const integration: FabricIntegrationDiscovery = {
      integrationId: "sphero-bolt",
      displayName: "Sphero BOLT",
      category: "robot",
      ioType: "bidirectional",
      icon: "sphero",
      status: "found",
      summary: "Windows found a device.",
      connectionMethod: "Bluetooth Low Energy",
      connectedNodeIds: [],
      candidates: [
        {
          candidateId: "SB-1234",
          displayName: "SB-1234",
          transport: "Bluetooth LE",
          status: "found",
          detail: "Visible nearby.",
          linkState: "visible",
        },
      ],
      setupSteps: ["Charge the robot."],
      actionId: "cit.sphero.connect",
      actionLabel: "Connect",
      requiresGroundedConfirmation: false,
      safetyNote: "Discovery does not move it.",
    };

    const localized = localizeFabricIntegration("ko", integration);
    expect(localized.connectionMethod).toContain("Bluetooth 저전력");
    expect(localized.setupSteps.join(" ")).toContain("충전");
    expect(localized.candidates[0]?.detail).toContain("근처");
    expect(localized.integrationId).toBe(integration.integrationId);
    expect(localized.actionId).toBe(integration.actionId);
    expect(localized.candidates[0]?.candidateId).toBe("SB-1234");
  });

  it("localizes static and numbered course roles", () => {
    const t = fabricTranslatorFor("ko");
    expect(fabricRoleText("student_robot", t).name).toBe("교실 로봇");
    expect(fabricRoleText("safety_drone_3", t).name).toBe("안전 드론 3");
  });
});
