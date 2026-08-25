import { describe, expect, it } from "vitest";

import { FabricApiError } from "./fabric-client.js";
import { describeFabricError } from "./FabricConsole.js";
import { fabricTranslatorFor } from "./fabric-i18n.js";

describe("Fabric classroom errors", () => {
  it("explains when a previously discovered Tello is no longer visible", () => {
    const error = new FabricApiError(409, {
      code: "BRAIN2DEVICES_CONNECTION_REJECTED",
      message:
        "Automatic fleet setup found no powered TELLO-* or RMTT-* access point.",
    });

    expect(describeFabricError(error, fabricTranslatorFor("ko"))).toBe(
      "Tello Wi-Fi가 현재 보이지 않습니다. 드론 전원을 켜고 TELLO-*가 표시되면 장치를 다시 검색한 뒤 연결하세요.",
    );
  });

  it("keeps an active Tello session distinct from a Fabric failure", () => {
    const error = new FabricApiError(409, {
      code: "BRAIN2DEVICES_CONNECTION_REJECTED",
      message:
        "Local Wi-Fi routes cannot change while an affected aircraft session may be active: [TELLO-DC5E0F] currently uses Wi-Fi 2 (connected, unknown). Land and disconnect any connected or busy affected sessions first.",
    });

    expect(describeFabricError(error, fabricTranslatorFor("ko"))).toBe(
      "드론 연결은 유지됩니다. 사용 중인 기체 세션 때문에 Wi-Fi 경로만 변경하지 않았습니다.",
    );
  });
});
