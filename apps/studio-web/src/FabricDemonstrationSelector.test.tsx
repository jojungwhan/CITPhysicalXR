import type { IntegrationNode } from "@citxr/protocol";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { fabricTranslatorFor } from "./fabric-i18n.js";
import { FabricDemonstrationSelector } from "./FabricDemonstrationSelector.js";

describe("Fabric demonstration selector", () => {
  it("offers every connected device directly without lesson copy", () => {
    const html = renderToStaticMarkup(
      <FabricDemonstrationSelector
        nodes={[
          node("matter-13-ep1", "창가 램프", "tapo-p110"),
          node("tello-1", "DJI Tello", "tello"),
        ]}
        selectedNodeIds={new Set(["matter-13-ep1", "tello-1"])}
        nodeName={(candidate) =>
          candidate.nodeId === "matter-13-ep1"
            ? "교실 플러그 1"
            : candidate.displayName
        }
        onSelectAll={vi.fn()}
        onClear={vi.fn()}
        onToggle={vi.fn()}
        t={fabricTranslatorFor("ko")}
      />,
    );

    expect(html).toContain("장치 직접 선택");
    expect(html).toContain("연결된 장치 모두 선택");
    expect(html).toContain("2개 중 2개 선택");
    expect(html).toContain('aria-label="교실 플러그 1 데모 선택"');
    expect(html).toContain('aria-label="DJI Tello 데모 선택"');
    expect(html.match(/type="checkbox"/g)).toHaveLength(2);
    expect(html).not.toContain("수업 선택");
  });
});

const node = (nodeId: string, displayName: string, model: string) =>
  ({
    nodeId,
    displayName,
    pluginId: `cit.${model}`,
    connectionState: "connected",
    metadata: { model },
  }) as unknown as IntegrationNode;
