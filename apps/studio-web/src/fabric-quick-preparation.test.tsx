import type { IntegrationNode } from "@citxr/protocol";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { FabricBrainDemoPanel } from "./FabricBrainDemoPanel.js";
import { FabricFleetSequencePanel } from "./FabricFleetSequencePanel.js";
import { fabricTranslatorFor } from "./fabric-i18n.js";

describe("one-step classroom preparation", () => {
  const t = fabricTranslatorFor("ko");

  it("lets the preparation action start and arm a ready physical session", () => {
    const html = renderToStaticMarkup(
      <FabricBrainDemoPanel
        controllerName="MindWave guided Tello"
        simulated={false}
        sessionState="ready"
        sessionArmed={false}
        safetyConfirmed={true}
        busy={false}
        canSubmit={true}
        canManageSession={true}
        onSafetyConfirmedChange={vi.fn()}
        onArm={vi.fn()}
        onStop={vi.fn()}
        locale="ko"
        t={t}
      />,
    );

    const prepare = html.match(
      /<button[^>]*class="fabric-demo-arm"[^>]*>/,
    )?.[0];
    expect(prepare).toBeDefined();
    expect(prepare).not.toContain("disabled");
  });

  it("keeps preparation disabled for a terminal lesson session", () => {
    const html = renderToStaticMarkup(
      <FabricBrainDemoPanel
        controllerName="MindWave guided Tello"
        simulated={false}
        sessionState="stopped"
        sessionArmed={false}
        safetyConfirmed={true}
        busy={false}
        canSubmit={true}
        canManageSession={true}
        onSafetyConfirmedChange={vi.fn()}
        onArm={vi.fn()}
        onStop={vi.fn()}
        locale="ko"
        t={t}
      />,
    );

    const prepare = html.match(
      /<button[^>]*class="fabric-demo-arm"[^>]*>/,
    )?.[0];
    expect(prepare).toContain("disabled");
  });

  it("selects one connected Tello and every connected trigger by default", () => {
    const input = {
      nodeId: "r1-a",
      pluginId: "cit.even-r1",
      displayName: "Even R1",
    } as IntegrationNode;
    const html = renderToStaticMarkup(
      <FabricFleetSequencePanel
        controllerName="Bounded Tello launch"
        simulated={false}
        status={{
          available: true,
          active: false,
          armed: false,
          phase: "idle",
          progress: 0,
          message: "Ready",
          selectedDroneIds: [],
          launchedDroneIds: [],
          landRequestedDroneIds: [],
          availableDrones: [
            {
              id: "primary",
              label: "TELLO-58C5B7",
              connection: "connected",
              flight: "landed",
              batteryPercent: 80,
            },
          ],
          simulated: false,
          observedAt: "2026-08-25T02:00:00Z",
        }}
        inputNodes={[input]}
        sessionState="ready"
        sessionArmed={false}
        safetyConfirmed={true}
        busy={false}
        canSubmit={true}
        canManageSession={true}
        onSafetyConfirmedChange={vi.fn()}
        onArm={vi.fn()}
        onLaunch={vi.fn()}
        onStart={vi.fn()}
        onStop={vi.fn()}
        locale="ko"
        t={t}
      />,
    );

    expect(html).toContain("TELLO-58C5B7");
    expect(html).toContain('type="checkbox" checked=""');
    const prepare = html.match(
      /<button[^>]*class="fabric-demo-arm"[^>]*>/,
    )?.[0];
    expect(prepare).toBeDefined();
    expect(prepare).not.toContain("disabled");
    expect(html).toContain("한 대씩 이륙");
    expect(html).toContain("한 대씩 착륙");
    expect(html).toContain("<details");
  });
});
