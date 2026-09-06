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

  it.each([
    [
      "MATTER_BLUETOOTH_UNAVAILABLE",
      "이 컴퓨터에서 Bluetooth LE 어댑터를 사용할 수 없습니다. 어댑터를 연결하거나 Bluetooth를 켠 뒤 다시 시도하세요.",
    ],
    [
      "MATTER_BLUETOOTH_ADAPTER_MISSING",
      "연결된 Bluetooth LE 어댑터가 없습니다. 어댑터를 연결한 뒤 ‘장치 찾기’를 다시 누르세요.",
    ],
    [
      "MATTER_BLUETOOTH_RADIO_OFF",
      "Bluetooth 어댑터는 있지만 Windows Bluetooth가 꺼져 있습니다. Bluetooth를 켠 뒤 다시 시도하세요.",
    ],
    [
      "MATTER_DEVICE_NOT_FOUND",
      "설정 모드인 Matter 플러그를 찾지 못했습니다. 플러그를 공장 초기화하고 컴퓨터 가까이에서 다시 시도하세요.",
    ],
    [
      "MATTER_WIFI_JOIN_FAILED",
      "플러그에는 연결했지만 저장된 Wi-Fi에 가입하지 못했습니다. 2.4GHz SSID와 비밀번호를 확인하세요.",
    ],
    [
      "MATTER_SETUP_CODE_REJECTED",
      "플러그가 응답했지만 인쇄된 Matter 설정 코드를 승인하지 않았습니다. 해당 플러그의 원래 코드를 확인하세요.",
    ],
    [
      "MATTER_ATTESTATION_FAILED",
      "플러그가 응답했지만 Matter 장치 신원을 확인하지 못했습니다. 정품 인증 장치와 최신 펌웨어인지 확인하세요.",
    ],
  ])("explains the Matter failure stage %s", (code, expected) => {
    const error = new FabricApiError(409, {
      code,
      message: "A redacted Matter diagnostic.",
    });

    expect(describeFabricError(error, fabricTranslatorFor("ko"))).toBe(
      expected,
    );
  });
});
