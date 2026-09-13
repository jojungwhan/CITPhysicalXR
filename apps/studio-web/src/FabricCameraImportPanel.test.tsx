import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { FabricCameraImportSnapshot } from "./fabric-client.js";
import { fabricTranslatorFor } from "./fabric-i18n.js";
import { FabricCameraImportPanel } from "./FabricCameraImportPanel.js";

const readyCamera = (): FabricCameraImportSnapshot => ({
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
  phoneBattery: {
    levelPercent: 70,
    charging: true,
    condition: "ok",
  },
  cameraBattery: { condition: "unknown" },
  operations: { startImport: true, openDestination: true },
});

describe("Fabric Sony camera import panel", () => {
  it("offers one automatic import action with safety details collapsed", () => {
    const html = renderToStaticMarkup(
      <FabricCameraImportPanel
        camera={readyCamera()}
        busy={false}
        canManage
        onStart={vi.fn().mockResolvedValue(true)}
        onOpenDestination={vi.fn().mockResolvedValue(true)}
        t={fabricTranslatorFor("ko")}
      />,
    );

    expect(html).toContain("Sony ZV-E10 자동 가져오기");
    expect(html).toContain("SM-N971N");
    expect(html).toContain("24개 · 2.11 GB");
    expect(html).toContain("15분마다");
    expect(html).toContain("휴대전화 배터리");
    expect(html).toContain("70% · 충전 중");
    expect(html).toContain("카메라 배터리");
    expect(html).toContain("확인 불가");
    expect(html).toContain("30% 미만이면 경고");
    expect(html).toContain(">지금 새 원본 가져오기</button>");
    expect(html).not.toContain("검증 완료 저장 위치");
    expect(html).not.toContain("C:\\Users\\jc\\Pictures\\Sony Camera Imports");
    expect(html).toContain(">폴더 열기</button>");
    expect(html).toContain("<details");
    expect(html).toContain("카메라나 휴대전화 파일을 삭제하지 않고");
  });

  it("shows a low-battery defer instead of starting a sync", () => {
    const camera = readyCamera();
    camera.state = "deferred";
    camera.phoneBattery = {
      levelPercent: 19,
      charging: false,
      condition: "blocked",
    };
    camera.operations.startImport = false;

    const html = renderToStaticMarkup(
      <FabricCameraImportPanel
        camera={camera}
        busy={false}
        canManage
        onStart={vi.fn().mockResolvedValue(true)}
        onOpenDestination={vi.fn().mockResolvedValue(true)}
        t={fabricTranslatorFor("ko")}
      />,
    );

    expect(html).toContain("배터리 부족 · 동기화 대기");
    expect(html).toContain("19% · 동기화 대기");
    expect(html).toContain(
      "충전을 시작하거나 배터리가 20% 이상이 되면 다음 자동 주기에 다시 확인합니다.",
    );
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>/);
  });

  it("shows the DJI-specific one-time setup and automation limits", () => {
    const camera = readyCamera();
    camera.cameraId = "dji-osmo-nano-android";
    camera.displayName = "DJI Osmo Nano";
    camera.state = "setup_required";
    camera.setupRequired = true;
    camera.errorCode = "DJI_NANO_PAIRING_REQUIRED";

    const html = renderToStaticMarkup(
      <FabricCameraImportPanel
        camera={camera}
        busy={false}
        canManage
        onStart={vi.fn().mockResolvedValue(true)}
        onOpenDestination={vi.fn().mockResolvedValue(true)}
        t={fabricTranslatorFor("en")}
      />,
    );

    expect(html).toContain("DJI Osmo Nano automatic import");
    expect(html).toContain("Finish DJI Mimo setup once");
    expect(html).toContain("not promise remote wake from every power state");
    expect(html).not.toContain("Imaging Edge Mobile pairing");
  });

  it("shows the one-time pairing state and disables while importing", () => {
    const camera = readyCamera();
    camera.state = "setup_required";
    camera.setupRequired = true;
    const setupHtml = renderToStaticMarkup(
      <FabricCameraImportPanel
        camera={camera}
        busy={false}
        canManage
        onStart={vi.fn().mockResolvedValue(true)}
        onOpenDestination={vi.fn().mockResolvedValue(true)}
        t={fabricTranslatorFor("en")}
      />,
    );

    expect(setupHtml).toContain("One-time camera pairing required");
    expect(setupHtml).toContain("Recurring imports are touch-free");

    camera.state = "verifying";
    camera.setupRequired = false;
    camera.progress = {
      stage: "verifying",
      message: "Verified DSC00001.JPG",
      completedItems: 3,
      totalItems: 24,
      bytesOnPhone: 2_260_951_681,
    };
    const activeHtml = renderToStaticMarkup(
      <FabricCameraImportPanel
        camera={camera}
        busy={false}
        canManage
        onStart={vi.fn().mockResolvedValue(true)}
        onOpenDestination={vi.fn().mockResolvedValue(true)}
        t={fabricTranslatorFor("ko")}
      />,
    );

    expect(activeHtml).toContain("24개 중 3개");
    expect(activeHtml).not.toContain("Verified DSC00001.JPG");
    expect(activeHtml).toMatch(/<button[^>]*disabled=""[^>]*>/);
  });

  it("identifies a locked companion instead of showing camera-pairing advice", () => {
    const camera = readyCamera();
    camera.state = "setup_required";
    camera.setupRequired = true;
    camera.errorCode = "SONY_PHONE_UNLOCK_REQUIRED";

    const html = renderToStaticMarkup(
      <FabricCameraImportPanel
        camera={camera}
        busy={false}
        canManage
        onStart={vi.fn().mockResolvedValue(true)}
        onOpenDestination={vi.fn().mockResolvedValue(true)}
        t={fabricTranslatorFor("ko")}
      />,
    );

    expect(html).toContain("전용 휴대전화 잠금 해제 필요");
    expect(html).toContain("패턴 잠금을 한 번 해제");
    expect(html).not.toContain("카메라 페어링 필요");
  });
});
