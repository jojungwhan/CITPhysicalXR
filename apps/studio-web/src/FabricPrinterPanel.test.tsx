import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { FabricPrinterSnapshot } from "./fabric-client.js";
import { fabricTranslatorFor } from "./fabric-i18n.js";
import { FabricPrinterPanel } from "./FabricPrinterPanel.js";

const lockedPrinter = (): FabricPrinterSnapshot => ({
  schemaVersion: "1.0",
  printerId: "creality-k1-max-172-30-1-55",
  displayName: "3D Printer",
  model: "Creality K1 Max (generation not yet verified)",
  address: "172.30.1.55",
  transport: "Not verified",
  state: "current_print_locked",
  operations: {
    stageSource: true,
    verifyIdle: false,
    slice: false,
    upload: false,
    start: false,
    lockReasonCode: "current_print",
    lockReason:
      "The current print is protected. Verify standby after it finishes.",
  },
  profiles: [
    {
      profileId: "k1-max-0.4-pla-standard",
      displayName: "K1 Max · 0.20 mm · Generic PLA · 0.4 mm",
      printerModel: "K1 Max",
      nozzleDiameterMm: 0.4,
      filament: "Generic PLA",
      process: "0.20 mm Standard",
      available: true,
    },
  ],
  sources: [],
  gcodeArtifacts: [],
});

describe("Fabric 3D printer panel", () => {
  it("renders a current-print lock without any enabled remote action", () => {
    const html = renderToStaticMarkup(
      <FabricPrinterPanel
        printer={lockedPrinter()}
        busy={false}
        canManage
        onVerifyIdle={vi.fn().mockResolvedValue(false)}
        onStage={vi.fn().mockResolvedValue(true)}
        onSlice={vi.fn().mockResolvedValue(false)}
        onDownload={vi.fn().mockResolvedValue(false)}
        onUpload={vi.fn().mockResolvedValue(false)}
        onPrepareStart={vi.fn().mockResolvedValue(undefined)}
        onStart={vi.fn().mockResolvedValue(false)}
        t={fabricTranslatorFor("ko")}
      />,
    );

    expect(html).toContain("3D 프린터");
    expect(html).toContain("172.30.1.55");
    expect(html).toContain("현재 출력 보호 중");
    expect(html).toContain("잠김 · 현재 출력 중");
    expect(html).toContain("확인되지 않음");
    expect(html).toContain(
      "현재 출력이 끝난 뒤 대기 상태를 확인할 때까지 보호합니다.",
    );
    expect(html).not.toContain("The current print is protected");
    expect(html).toContain("프린터로 전송하지 않음");
    expect(html).toContain("출력 시작은 전체 선택");
    expect(html).not.toContain("모두 선택");

    const verify = html.match(
      /<button class="fabric-printer-verify"[^>]*>/,
    )?.[0];
    const prepare = html.match(/<button type="button"[^>]*>G-code 준비/)?.[0];
    expect(verify).toContain("disabled");
    expect(prepare).toContain("disabled");
    expect(html).not.toContain(">업로드만</button>");
    expect(html).not.toContain(">출력 시작</button>");
  });

  it("keeps upload and print start as separate buttons", () => {
    const printer = lockedPrinter();
    printer.state = "standby";
    printer.operations = {
      stageSource: true,
      verifyIdle: false,
      slice: true,
      upload: true,
      start: true,
    };
    printer.gcodeArtifacts = [
      {
        artifactId: "a".repeat(32),
        fileName: "demo.gcode",
        sizeBytes: 4096,
        sha256: "b".repeat(64),
        createdAt: "2026-09-08T12:00:00Z",
        sourceArtifactId: "c".repeat(32),
        profileId: "k1-max-0.4-pla-standard",
      },
      {
        artifactId: "d".repeat(32),
        fileName: "uploaded.gcode",
        sizeBytes: 4096,
        sha256: "e".repeat(64),
        createdAt: "2026-09-08T12:00:00Z",
        sourceArtifactId: "f".repeat(32),
        profileId: "k1-max-0.4-pla-standard",
        remoteFileName: "cit-uploaded.gcode",
        uploadedAt: "2026-09-08T12:01:00Z",
      },
    ];

    const html = renderToStaticMarkup(
      <FabricPrinterPanel
        printer={printer}
        busy={false}
        canManage
        onVerifyIdle={vi.fn().mockResolvedValue(false)}
        onStage={vi.fn().mockResolvedValue(true)}
        onSlice={vi.fn().mockResolvedValue(true)}
        onDownload={vi.fn().mockResolvedValue(true)}
        onUpload={vi.fn().mockResolvedValue(true)}
        onPrepareStart={vi.fn().mockResolvedValue(undefined)}
        onStart={vi.fn().mockResolvedValue(true)}
        t={fabricTranslatorFor("en")}
      />,
    );

    expect(html).toContain(">Upload only</button>");
    expect(html).toContain(">Start print</button>");
    expect(html).not.toContain("Confirm and start this print");
  });
});
