import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type {
  FabricAndroidControllerSnapshot,
  FabricCameraImportSnapshot,
  FabricLanAccessSnapshot,
  FabricUnlockAutomationSnapshot,
} from "./fabric-client.js";
import { fabricTranslatorFor } from "./fabric-i18n.js";
import { FabricQuickControls } from "./FabricQuickControls.js";

const camera: FabricCameraImportSnapshot = {
  schemaVersion: "1.0",
  cameraId: "sony-zve10-android",
  displayName: "Sony ZV-E10",
  state: "ready",
  destination: "C:\\Users\\jc\\Pictures\\Sony Camera Imports",
  phoneConnected: true,
  phoneModel: "SM-N971N",
  appInstalled: true,
  bluetoothEnabled: true,
  cameraWifiConnected: false,
  setupRequired: false,
  filesOnPhone: 24,
  bytesOnPhone: 2_260_951_681,
  automaticEnabled: true,
  automaticIntervalSeconds: 900,
  operations: { startImport: true, openDestination: true },
};

const djiCamera: FabricCameraImportSnapshot = {
  ...camera,
  cameraId: "dji-osmo-nano-android",
  displayName: "DJI Osmo Nano",
  destination: "C:\\Users\\jc\\Pictures\\DJI Osmo Nano Imports",
};

const androidController: FabricAndroidControllerSnapshot = {
  schemaVersion: "1.0",
  state: "ready",
  phoneConnected: true,
  phoneModel: "SM-N971N",
  usbReverseReady: true,
  operations: { openController: true },
  message: "USB bridge ready",
};

const lanAccess: FabricLanAccessSnapshot = {
  schemaVersion: "1.0",
  enabled: true,
  lanOrigin: "http://172.30.1.4:8766",
  devices: [
    {
      displayName: "Spare Android",
      macAddress: "02:11:22:33:44:55",
      addedAt: "2026-09-10T03:00:00Z",
    },
  ],
  operations: { manage: true, enrollUsbAndroid: true },
};

const unlockAutomation: FabricUnlockAutomationSnapshot = {
  schemaVersion: "1.0",
  enabled: true,
  selectedNodeIds: ["plug-1", "plug-2", "plug-3"],
  cooldownSeconds: 15,
  companion: {
    deviceId: "android-0123456789abcdef",
    displayName: "SM-N971N (Wi-Fi)",
    pairedAt: "2026-09-10T03:00:00Z",
    lastSeenAt: "2026-09-10T03:15:00Z",
  },
  lastResult: {
    outcome: "succeeded",
    occurredAt: "2026-09-10T03:15:00Z",
    requestedCount: 3,
    acceptedCount: 3,
    message: "accepted",
  },
  operations: { manage: true, installAndPair: true },
};

const renderControls = (
  settingsOpen: boolean,
  cameras: readonly FabricCameraImportSnapshot[] = [camera, djiCamera],
  androidMode = false,
) =>
  renderToStaticMarkup(
    <FabricQuickControls
      selectedPlugCount={3}
      canTurnOnSelected
      canTurnOffSelected
      busy={false}
      settingsOpen={settingsOpen}
      cameras={cameras}
      canManageCamera
      onTurnOnSelected={vi.fn()}
      onTurnOffSelected={vi.fn()}
      onSettingsOpenChange={vi.fn()}
      onOpenCameraDestination={vi.fn().mockResolvedValue(true)}
      androidController={androidController}
      canOpenAndroidController
      lanAccess={lanAccess}
      canManageLanAccess={!androidMode}
      unlockAutomation={unlockAutomation}
      canInstallPwa
      onOpenAndroidController={vi.fn()}
      onAddLanAccessDevice={vi.fn().mockResolvedValue(true)}
      onRemoveLanAccessDevice={vi.fn().mockResolvedValue(true)}
      onEnrollUsbAndroidLanAccess={vi.fn().mockResolvedValue(true)}
      onCopyLanAccessLink={vi.fn().mockResolvedValue(true)}
      onConfigureUnlockAutomation={vi.fn().mockResolvedValue(true)}
      onInstallAndPairUnlockCompanion={vi.fn().mockResolvedValue(true)}
      onRemoveUnlockCompanion={vi.fn().mockResolvedValue(true)}
      onInstallPwa={vi.fn()}
      androidMode={androidMode}
      t={fabricTranslatorFor("ko")}
    />,
  );

describe("Fabric floating quick controls", () => {
  it("keeps technical camera paths hidden behind one settings button", () => {
    const html = renderControls(false);

    expect(html).toContain('aria-label="빠른 제어"');
    expect(html).toContain("3개 선택됨");
    expect(html).toContain(">선택 켜기</button>");
    expect(html).toContain(">선택 끄기</button>");
    expect(html).toContain('aria-controls="fabric-control-settings"');
    expect(html).toContain(">설정</button>");
    expect(html).toContain(">Sony 폴더</button>");
    expect(html).toContain(">Nano 폴더</button>");
    expect(html).toContain('href="http://127.0.0.1:4174"');
    expect(html).toContain("소셜 콘텐츠</a>");
    expect(html).not.toContain(camera.destination);
    expect(html).not.toContain(djiCamera.destination);
    expect(html).not.toContain("검증 완료 저장 위치");
  });

  it("keeps both camera folder actions visible while status is loading", () => {
    const html = renderControls(false, []);

    expect(html).toContain(">Sony 폴더</button>");
    expect(html).toContain(">Nano 폴더</button>");
    expect(html.match(/fabric-quick-camera-folder/g)).toHaveLength(2);
  });

  it("keeps the Android dock compact because plug power is on the main screen", () => {
    const html = renderControls(false, [camera, djiCamera], true);

    expect(html).toContain(
      'class="fabric-quick-controls is-android-controller"',
    );
    expect(html).not.toContain("3개 선택됨");
    expect(html).not.toContain(">선택 켜기</button>");
    expect(html).not.toContain(">선택 끄기</button>");
    expect(html).toContain(">Sony 폴더</button>");
    expect(html).toContain(">Nano 폴더</button>");
    expect(html).toContain(">설정</button>");
    expect(html).not.toContain("소셜 콘텐츠</a>");
  });

  it("reveals the destination and folder action only in settings", () => {
    const html = renderControls(true);

    expect(html).toContain('role="dialog"');
    expect(html).toContain("검증 완료 저장 위치");
    expect(html).toContain(camera.destination);
    expect(html).toContain("DJI Osmo Nano");
    expect(html).toContain(djiCamera.destination);
    expect(html).toContain("15분마다");
    expect(html.match(/>폴더 열기<\/button>/g)).toHaveLength(2);
    expect(html).toContain("체크한 플러그 3개가 이 브라우저에 저장");
    expect(html).toContain("Android 제어 화면");
    expect(html).toContain("SM-N971N");
    expect(html).toContain("USB 연결 준비됨");
    expect(html).toContain(">Android에서 열기</button>");
    expect(html).toContain(">이 휴대전화에 설치</button>");
    expect(html).toContain("로컬 Wi-Fi 접근");
    expect(html).toContain("http://172.30.1.4:8766");
    expect(html).toContain("Spare Android");
    expect(html).toContain("02:11:22:33:44:55");
    expect(html).toContain(">USB 휴대전화 허용하고 열기</button>");
    expect(html).toContain(">접속 링크 복사</button>");
    expect(html).toContain(">장치 허용</button>");
    expect(html).toContain("휴대전화 잠금 해제 자동화");
    expect(html).toContain("SM-N971N (Wi-Fi)");
    expect(html).toContain("현재 체크한 플러그 저장");
    expect(html).toContain("휴대전화 페어링 해제");
    expect(html).toContain("USB를 분리하세요");
  });
});
