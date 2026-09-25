import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { FabricGatewayPlugPanel } from "./FabricGatewayPlugs.js";
import { FabricClient, type FabricPlugGateway } from "./fabric-client.js";
import { fabricTranslatorFor } from "./fabric-i18n.js";

const gateway: FabricPlugGateway = {
  siteId: "academy",
  displayName: "CIT Coding 학원",
  connected: true,
  canControl: true,
  generatedAt: "2026-09-23T04:00:00Z",
  message: null,
  plugs: Array.from({ length: 4 }, (_, i) => ({
    nodeId: `plug-${i}`,
    displayName: "Smart Wi-Fi Plug",
    available: true,
    on: false,
  })),
};

describe("Gateway plug controls", () => {
  it("shows all four gateway plugs and individual and group actions in Korean", () => {
    const html = renderToStaticMarkup(
      <FabricGatewayPlugPanel
        gateway={gateway}
        busy={false}
        canSubmit
        onPower={vi.fn()}
        t={fabricTranslatorFor("ko")}
      />,
    );
    expect(html).toContain("CIT Coding 학원");
    expect(html).toContain("플러그 4개 중 4개 연결됨");
    expect(html.match(/fabric-gateway-plug-row/g)).toHaveLength(4);
    expect(html.match(/<button /g)).toHaveLength(10);
    expect(html).not.toContain("disabled");
  });

  it("disables all controls and hides stale ON states when the gateway disconnects", () => {
    const html = renderToStaticMarkup(
      <FabricGatewayPlugPanel
        gateway={{
          ...gateway,
          connected: false,
          plugs: gateway.plugs.map((plug) => ({ ...plug, on: true })),
        }}
        busy={false}
        canSubmit
        onPower={vi.fn()}
        t={fabricTranslatorFor("en")}
      />,
    );
    expect(html).toContain("Gateway offline");
    expect(html).not.toContain("is-on");
    expect(html.match(/disabled=""/g)).toHaveLength(10);
  });

  it("keeps power disabled for a read-only or physically disabled runtime", () => {
    const html = renderToStaticMarkup(
      <FabricGatewayPlugPanel
        gateway={{ ...gateway, canControl: false }}
        busy={false}
        canSubmit
        onPower={vi.fn()}
        t={fabricTranslatorFor("en")}
      />,
    );
    expect(html.match(/disabled=""/g)).toHaveLength(10);
  });

  it("sends the exact chosen gateway and plug selection through the local authenticated API", async () => {
    const fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ accepted: true }), { status: 200 }),
    );
    const client = new FabricClient("", fetch);
    client.setCredential("x".repeat(40));
    await client.setGatewayPlugPower("academy", ["plug-2"], false);
    const [url, options] = fetch.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("/api/v1/fabric/plug-gateways/academy/power");
    expect(options.method).toBe("POST");
    expect(JSON.parse(String(options.body))).toEqual({
      selectedNodeIds: ["plug-2"],
      on: false,
    });
    expect(JSON.stringify(options)).not.toContain("secret");
  });
});
