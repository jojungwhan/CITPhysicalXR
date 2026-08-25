import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { FabricDiscoveryActions } from "./FabricDiscoveryActions.js";
import { fabricTranslatorFor } from "./fabric-i18n.js";

describe("FabricDiscoveryActions", () => {
  const t = fabricTranslatorFor("ko");

  it("keeps a per-card scan action when initial discovery found nothing", () => {
    const html = renderToStaticMarkup(
      <FabricDiscoveryActions
        actionLabel={undefined}
        busy={false}
        canConnect={true}
        connected={false}
        groundedConfirmed={false}
        hasConnectAction={false}
        hasSetupCommand={false}
        requiresGroundedConfirmation={false}
        onConnect={vi.fn()}
        onCopySetup={vi.fn()}
        onScan={vi.fn()}
        t={t}
      />,
    );

    expect(html).toContain('class="fabric-scan-device"');
    expect(html).toContain("이 장치 다시 검색");
    expect(html).not.toContain('class="fabric-connect-device"');
  });

  it("shows scan and validated connect actions together when available", () => {
    const html = renderToStaticMarkup(
      <FabricDiscoveryActions
        actionLabel="G2 연결"
        busy={false}
        canConnect={true}
        connected={false}
        groundedConfirmed={false}
        hasConnectAction={true}
        hasSetupCommand={false}
        requiresGroundedConfirmation={false}
        onConnect={vi.fn()}
        onCopySetup={vi.fn()}
        onScan={vi.fn()}
        t={t}
      />,
    );

    expect(html).toContain('class="fabric-scan-device"');
    expect(html).toContain('class="fabric-connect-device"');
    expect(html).toContain("G2 연결");
  });

  it("can keep a repeatable fleet connection beside an existing connection", () => {
    const html = renderToStaticMarkup(
      <FabricDiscoveryActions
        actionLabel="연결 가능한 모든 드론 연결"
        busy={false}
        canConnect={true}
        connected={true}
        showConnectWhenConnected
        groundedConfirmed
        hasConnectAction
        hasSetupCommand={false}
        requiresGroundedConfirmation
        onConnect={vi.fn()}
        onCopySetup={vi.fn()}
        onScan={vi.fn()}
        t={t}
      />,
    );

    expect(html).toContain("연결 가능한 모든 드론 연결");
    expect(html).toContain('class="fabric-connect-device"');
  });

  it("shows connection feedback beside the device action that produced it", () => {
    const html = renderToStaticMarkup(
      <FabricDiscoveryActions
        actionLabel="연결 가능한 모든 드론 연결"
        busy={false}
        canConnect={true}
        connected={false}
        feedback={{
          tone: "error",
          message: "드론용 Wi-Fi 어댑터를 확인하세요.",
        }}
        groundedConfirmed
        hasConnectAction
        hasSetupCommand={false}
        requiresGroundedConfirmation
        onConnect={vi.fn()}
        onCopySetup={vi.fn()}
        onScan={vi.fn()}
        t={t}
      />,
    );

    expect(html).toContain('class="fabric-discovery-action-feedback is-error"');
    expect(html).toContain('role="alert"');
    expect(html).toContain("드론용 Wi-Fi 어댑터를 확인하세요.");
  });
});
