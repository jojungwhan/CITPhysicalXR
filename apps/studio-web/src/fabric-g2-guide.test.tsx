import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { FabricG2Guide } from "./FabricG2Guide.js";
import { fabricTranslatorFor } from "./fabric-i18n.js";

describe("FabricG2Guide", () => {
  it("explains glasses input, device control, output, and Telegram paths", () => {
    const html = renderToStaticMarkup(
      <FabricG2Guide t={fabricTranslatorFor("ko")}>
        <button type="button">이 장치 다시 검색</button>
      </FabricG2Guide>,
    );

    expect(html).toContain('<details class="fabric-g2-guide">');
    expect(html).toContain("<summary>");
    expect(html).not.toContain("<details open");
    expect(html).toContain("음성·버튼 입력");
    expect(html).toContain("Codex 또는 Claude");
    expect(html).toContain("CIT 로봇 앞으로");
    expect(html).toContain("RoboMaster, Sphero, LEGO 또는 Dash");
    expect(html).toContain("이동과 이륙은 한 번 더 눌러 확인");
    expect(html).toContain("Telegram은 안경이 아니라");
    expect(html).toContain("일반 문구를 직접 보내는 작성창");
    expect(html).toContain("fabric-g2-guide-actions");
    expect(html).toContain("이 장치 다시 검색");
    expect(html.indexOf("이 장치 다시 검색")).toBeLessThan(
      html.indexOf("</details>"),
    );
  });
});
