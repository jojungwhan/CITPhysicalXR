import type { IntegrationNode } from "@citxr/protocol";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { FabricSmartPlugPanel } from "./FabricSmartPlugPanel.js";
import { FabricSpheroPanel } from "./FabricSpheroPanel.js";
import { FabricSpheroSetup } from "./FabricSpheroSetup.js";
import { FabricDronePanel } from "./FabricDronePanel.js";
import type { FabricDiscoveryCandidate } from "./fabric-client.js";
import { fabricTranslatorFor } from "./fabric-i18n.js";
import {
  saveSmartPlugSelection,
  SMART_PLUG_SELECTION_STORAGE_KEY,
} from "./fabric-smart-plug.js";

const physicalNode = (overrides: Partial<IntegrationNode>): IntegrationNode =>
  ({
    nodeId: "device-1",
    displayName: "Classroom device",
    connectionState: "connected",
    simulated: false,
    metadata: {},
    ...overrides,
  }) as IntegrationNode;

const memoryStorage = () => {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  };
};

const flightCapability = (
  name: string,
): IntegrationNode["consumedCapabilities"][number] => ({
  name,
  version: "1.0",
  direction: "consume",
  latencyClass: "interactive",
  safetyClassification: "flight",
  dataClassification: "operational",
  constraints: {},
});

describe("Fabric direct device controls", () => {
  const t = fabricTranslatorFor("ko");

  it("shows one immediately enabled smart-plug toggle before setup", () => {
    const offHtml = renderToStaticMarkup(
      <FabricSmartPlugPanel
        plugs={[
          {
            role: "classroom_plug",
            node: physicalNode({
              nodeId: "plug-1",
              displayName: "P110M",
              metadata: { vendorBrand: "TP-Link", model: "Tapo P110M" },
            }),
            state: {
              on: false,
              observedAt: "2026-08-24T12:00:00Z",
              source: "command",
            },
          },
        ]}
        sessionState=""
        sessionMode={undefined}
        sessionArmed={false}
        busy={false}
        canSubmit={true}
        canManageSession={true}
        requiredRolesReady={true}
        onPower={vi.fn()}
        onGroupPower={vi.fn()}
        t={t}
      />,
    );

    expect(offHtml).not.toContain("켜기 제어 활성화");
    expect(offHtml.match(/class="fabric-power-toggle/g)).toHaveLength(1);
    const turnOnToggle = offHtml.match(
      /<button class="fabric-power-toggle fabric-power-on"[^>]*>/,
    )?.[0];
    expect(turnOnToggle).toBeDefined();
    // The label already states the action, so aria-pressed would double-encode
    // it. The accessible name names the target and what pressing will do.
    expect(turnOnToggle).not.toContain("aria-pressed");
    expect(turnOnToggle).toContain('aria-label="교실 플러그 1: 켜기"');
    expect(turnOnToggle).not.toContain("disabled");
    expect(offHtml).toContain("교실 플러그 1");
    expect(offHtml).toContain("꺼짐");
    expect(offHtml).toContain("켜기");
    // Current state and the action live in separate elements, never in one
    // control that has to mean both at once.
    expect(offHtml).toContain(
      '<span class="fabric-plug-state is-off">꺼짐</span>',
    );
    expect(offHtml).not.toContain("plug-1");
    expect(offHtml).not.toContain("P110M");
    expect(offHtml).not.toContain("TP-Link");
    expect(offHtml).not.toContain("command");
    expect(offHtml).not.toContain("승인된 교실 부하 켜기");
    expect(offHtml).not.toContain("장치 찾기 후 하나의 전원 버튼");
    // No heading: the enclosing discovery card already names the integration.
    expect(offHtml).not.toContain("<h2");
    expect(offHtml).not.toContain("eyebrow");

    const onHtml = renderToStaticMarkup(
      <FabricSmartPlugPanel
        plugs={[
          {
            role: "classroom_plug",
            node: physicalNode({ nodeId: "plug-1", displayName: "P110M" }),
            state: { on: true, observedAt: "2026-08-24T12:00:00Z" },
          },
        ]}
        sessionState="active"
        sessionMode="physical"
        sessionArmed
        busy={false}
        canSubmit
        canManageSession
        requiredRolesReady
        onPower={vi.fn()}
        onGroupPower={vi.fn()}
        t={t}
      />,
    );

    expect(onHtml.match(/class="fabric-power-toggle/g)).toHaveLength(1);
    const turnOffToggle = onHtml.match(
      /<button class="fabric-power-toggle fabric-power-off"[^>]*>/,
    )?.[0];
    expect(turnOffToggle).toBeDefined();
    expect(turnOffToggle).toContain('aria-label="교실 플러그 1: 끄기"');
    expect(turnOffToggle).not.toContain("disabled");
    expect(onHtml).toContain("끄기");
    expect(onHtml).toContain(
      '<span class="fabric-plug-state is-on">켜짐</span>',
    );
  });

  it("renders an Android-first remote with explicit all and per-plug power actions", () => {
    const html = renderToStaticMarkup(
      <FabricSmartPlugPanel
        plugs={[
          {
            role: "classroom_plug",
            node: physicalNode({ nodeId: "plug-1", displayName: "P110M" }),
            state: { on: false, observedAt: "2026-09-09T12:00:00Z" },
          },
          {
            role: "classroom_plug_2",
            node: physicalNode({ nodeId: "plug-2", displayName: "P110M" }),
            state: { on: true, observedAt: "2026-09-09T12:00:00Z" },
          },
        ]}
        remoteMode
        showFullControlCenter={false}
        onShowFullControlCenterChange={vi.fn()}
        sessionState="active"
        sessionMode="physical"
        sessionArmed
        busy={false}
        canSubmit
        canManageSession
        requiredRolesReady
        onPower={vi.fn()}
        onGroupPower={vi.fn()}
        t={t}
      />,
    );

    expect(html).toContain(
      'class="fabric-smart-plug-panel fabric-android-plug-remote"',
    );
    expect(html).toContain("스마트 플러그 원격 제어");
    expect(html).toContain("2개 중 2개 연결됨");
    expect(html).toContain(">모든 플러그 켜기</button>");
    expect(html).toContain(">모든 플러그 끄기</button>");
    expect(html.match(/class="fabric-plug-remote-on"/g)).toHaveLength(2);
    expect(html.match(/class="fabric-plug-remote-off"/g)).toHaveLength(2);
    expect(html).toContain('aria-label="교실 플러그 1: 켜기"');
    expect(html).toContain('aria-label="교실 플러그 1: 끄기"');
    expect(html).toContain("전체 제어 센터 보기");
  });

  it("marks unobserved smart-plug state without overflowing the row", () => {
    const html = renderToStaticMarkup(
      <FabricSmartPlugPanel
        plugs={[
          {
            role: "classroom_plug",
            node: physicalNode({ nodeId: "plug-1", displayName: "P110M" }),
            state: undefined,
          },
        ]}
        sessionState="active"
        sessionMode="physical"
        sessionArmed
        busy={false}
        canSubmit
        canManageSession
        requiredRolesReady
        onPower={vi.fn()}
        onGroupPower={vi.fn()}
        t={t}
      />,
    );

    // A word like "알 수 없음" cannot fit the state column; a null-reading mark
    // can, and the full sentence stays available as the tooltip.
    expect(html).not.toContain(">알 수 없음<");
    expect(html).toContain("--");
    expect(html).toContain(
      '<span class="fabric-plug-state is-unknown" title="이 수업에서 아직 상태를 확인하지 못했습니다">',
    );
    // Unknown state still offers the safe direction.
    expect(html).toContain("끄기");
  });

  it("renders every connected classroom plug as an independently named control", () => {
    const html = renderToStaticMarkup(
      <FabricSmartPlugPanel
        plugs={Array.from({ length: 4 }, (_, index) => ({
          role: index === 0 ? "classroom_plug" : `classroom_plug_${index + 1}`,
          node: physicalNode({
            nodeId: `plug-${index + 1}`,
            displayName: "Smart Wi-Fi Plug",
          }),
          state: { on: false, observedAt: "2026-09-01T12:00:00Z" },
        }))}
        sessionState="active"
        sessionMode="physical"
        sessionArmed
        busy={false}
        canSubmit
        canManageSession
        requiredRolesReady
        onPower={vi.fn()}
        onGroupPower={vi.fn()}
        t={t}
      />,
    );

    expect(html.match(/class="fabric-power-toggle/g)).toHaveLength(4);
    expect(html.match(/type="checkbox"/g)).toHaveLength(5);
    expect(html).toContain("모두 선택");
    expect(html).toContain("0개 선택됨");
    const groupOn = html.match(
      /<button class="fabric-plug-group-on"[^>]*>/,
    )?.[0];
    const groupOff = html.match(
      /<button class="fabric-plug-group-off"[^>]*>/,
    )?.[0];
    expect(groupOn).toContain("disabled");
    expect(groupOff).toContain("disabled");
    expect(html).toContain("선택 켜기");
    expect(html).toContain("선택 끄기");
    for (const number of [1, 2, 3, 4]) {
      expect(html).toContain(`교실 플러그 ${number}`);
      expect(html).toContain(`aria-label="교실 플러그 ${number} 선택"`);
      expect(html).toContain(`aria-label="교실 플러그 ${number}: 켜기"`);
    }
  });

  it("restores checked plugs by node identity after a reload", () => {
    const storage = memoryStorage();
    saveSmartPlugSelection(["plug-2"], storage);
    vi.stubGlobal("window", { localStorage: storage });

    try {
      const html = renderToStaticMarkup(
        <FabricSmartPlugPanel
          plugs={[1, 2].map((number) => ({
            role: number === 1 ? "classroom_plug" : `classroom_plug_${number}`,
            node: physicalNode({
              nodeId: `plug-${number}`,
              displayName: "Smart Wi-Fi Plug",
            }),
            state: { on: false, observedAt: "2026-09-06T12:00:00Z" },
          }))}
          sessionState="active"
          sessionMode="physical"
          sessionArmed
          busy={false}
          canSubmit
          canManageSession
          requiredRolesReady
          onPower={vi.fn()}
          onGroupPower={vi.fn()}
          t={t}
        />,
      );

      const firstPlugCheckbox = html.match(
        /<input[^>]*aria-label="교실 플러그 1 선택"[^>]*>/,
      )?.[0];
      const secondPlugCheckbox = html.match(
        /<input[^>]*aria-label="교실 플러그 2 선택"[^>]*>/,
      )?.[0];
      expect(firstPlugCheckbox).not.toContain("checked");
      expect(secondPlugCheckbox).toContain("checked");
    } finally {
      vi.unstubAllGlobals();
      storage.removeItem(SMART_PLUG_SELECTION_STORAGE_KEY);
    }
  });

  it("shows a persisted custom plug name with an accessible rename control", () => {
    const html = renderToStaticMarkup(
      <FabricSmartPlugPanel
        plugs={[
          {
            role: "classroom_plug",
            node: physicalNode({
              nodeId: "matter-13-ep1",
              displayName: "Smart Wi-Fi Plug",
              metadata: { matterNodeId: "19", endpointId: 1 },
            }),
            state: { on: false, observedAt: "2026-09-06T01:00:00Z" },
          },
        ]}
        setupCodes={[
          {
            setupCode: "12345678901",
            matterNodeIds: ["19"],
            name: "창가 램프",
          },
        ]}
        sessionState="ready"
        sessionMode="physical"
        sessionArmed={false}
        busy={false}
        canSubmit
        canManageSession
        canRename
        requiredRolesReady
        onPower={vi.fn()}
        onGroupPower={vi.fn()}
        onRename={vi.fn().mockResolvedValue(true)}
        t={t}
      />,
    );

    expect(html).toContain('<span class="fabric-plug-name">창가 램프</span>');
    expect(html).toContain('aria-label="창가 램프 이름 변경"');
    expect(html).toContain(">이름 변경</button>");
    expect(html).toContain('aria-label="창가 램프: 켜기"');
    expect(html).not.toContain(">교실 플러그 1</span>");
  });

  it("shows the controller Matter node ID for each connected plug", () => {
    const html = renderToStaticMarkup(
      <FabricSmartPlugPanel
        plugs={[
          {
            role: "classroom_plug",
            node: physicalNode({
              nodeId: "matter-13-ep1",
              displayName: "Smart Wi-Fi Plug",
              metadata: { matterNodeId: "19", endpointId: 1 },
            }),
            state: { on: false, observedAt: "2026-09-03T02:00:00Z" },
          },
          {
            role: "classroom_plug_2",
            node: physicalNode({
              nodeId: "matter-16-ep1",
              displayName: "Smart Wi-Fi Plug",
              metadata: { matterNodeId: "22", endpointId: 1 },
            }),
            state: { on: false, observedAt: "2026-09-03T02:00:00Z" },
          },
        ]}
        setupCodes={[
          { setupCode: "12345678901", matterNodeIds: ["19"] },
          { setupCode: "10987654321", matterNodeIds: ["22"] },
        ]}
        sessionState="active"
        sessionMode="physical"
        sessionArmed
        busy={false}
        canSubmit
        canManageSession
        requiredRolesReady
        onPower={vi.fn()}
        onGroupPower={vi.fn()}
        t={t}
      />,
    );

    expect(html).toContain(
      '<small class="fabric-plug-matter-id">Matter 노드 ID 19</small>',
    );
    expect(html).toContain(
      '<small class="fabric-plug-matter-id">Matter 노드 ID 22</small>',
    );
    expect(html).toContain(
      '<small class="fabric-plug-setup-code">Matter 설정 코드 1234 567 8901</small>',
    );
    expect(html).toContain(
      '<small class="fabric-plug-setup-code">Matter 설정 코드 1098 765 4321</small>',
    );
  });

  it("keeps commissioned offline plugs visible with unavailable controls", () => {
    const html = renderToStaticMarkup(
      <FabricSmartPlugPanel
        plugs={Array.from({ length: 4 }, (_, index) => ({
          role: index === 0 ? "classroom_plug" : `classroom_plug_${index + 1}`,
          node: physicalNode({
            nodeId: `plug-${index + 1}`,
            displayName: "Smart Wi-Fi Plug",
            connectionState: index < 2 ? "connected" : "disconnected",
          }),
          state:
            index < 2
              ? { on: false, observedAt: "2026-09-01T12:00:00Z" }
              : undefined,
        }))}
        sessionState="ready"
        sessionMode="physical"
        sessionArmed={false}
        busy={false}
        canSubmit
        canManageSession
        requiredRolesReady
        onPower={vi.fn()}
        onGroupPower={vi.fn()}
        t={t}
      />,
    );

    expect(html.match(/class="fabric-power-toggle/g)).toHaveLength(4);
    expect(html.match(/>연결 끊김</g)).toHaveLength(2);
    for (const number of [3, 4]) {
      const selection = html.match(
        new RegExp(`<input[^>]*aria-label="교실 플러그 ${number} 선택"[^>]*>`),
      )?.[0];
      expect(selection).toBeDefined();
      expect(selection).toContain("disabled");
      const unavailable = html.match(
        new RegExp(
          `<button[^>]*aria-label="교실 플러그 ${number}: 제어 불가"[^>]*>`,
        ),
      )?.[0];
      expect(unavailable).toBeDefined();
      expect(unavailable).toContain("disabled");
      expect(unavailable).toContain(
        'title="플러그 연결이 끊겼습니다. 전원과 교실 Wi-Fi를 확인한 뒤 장치 찾기를 다시 실행하세요."',
      );
    }
  });

  it("shows Sphero movement controls without a separate enable step", () => {
    const html = renderToStaticMarkup(
      <FabricSpheroPanel
        robots={[
          {
            role: "robot_sensor_1",
            node: physicalNode({
              nodeId: "sphero-1",
              displayName: "SB-1234",
            }),
          },
        ]}
        sessionState=""
        sessionArmed={false}
        busy={false}
        canSubmit={true}
        canManageSession={true}
        onCommand={vi.fn()}
        t={t}
      />,
    );

    expect(html).not.toContain("이동 제어 활성화");
    const forwardButton = html.match(
      /<button[^>]*aria-label="앞으로"[^>]*>/,
    )?.[0];
    expect(forwardButton).toBeDefined();
    expect(forwardButton).not.toContain("disabled");
  });

  it("keeps the exact Sphero ID without a selection checkbox", () => {
    const candidate = {
      candidateId: "sphero-aabbccddeeff",
      displayName: "SB-B7BE",
      model: "sphero-bolt",
      status: "found",
      signalPercent: 88,
    } as FabricDiscoveryCandidate;
    const html = renderToStaticMarkup(
      <FabricSpheroSetup
        candidates={[candidate]}
        busy={false}
        canConnect={true}
        onConnect={vi.fn()}
        t={t}
      />,
    );

    expect(html).toContain("SB-B7BE");
    expect(html).not.toContain('type="checkbox"');
    expect(html).not.toContain("보이는 Sphero BOLT 로봇");
  });

  it("shows bounded single-Tello controls with one explicit safety confirmation", () => {
    const html = renderToStaticMarkup(
      <FabricDronePanel
        drones={[
          {
            role: "safety_drone_1",
            node: physicalNode({
              nodeId: "tello-primary",
              pluginId: "cit.tello",
              displayName: "TELLO-58C5B7",
              consumedCapabilities: [
                flightCapability("mobility.flight.takeoff"),
                flightCapability("mobility.flight.move"),
                flightCapability("mobility.flight.rotate"),
                flightCapability("mobility.flight.land"),
                flightCapability("mobility.flight.emergency_stop"),
              ],
            }),
          },
        ]}
        sessionState="ready"
        sessionArmed={false}
        busy={false}
        canSubmit={true}
        canManageSession={true}
        safetyConfirmed={false}
        onSafetyConfirmedChange={vi.fn()}
        onCommand={vi.fn()}
        t={t}
      />,
    );

    expect(html.match(/type="checkbox"/g)).toHaveLength(1);
    expect(html).not.toContain('type="checkbox" checked');
    expect(html).toContain(
      "강사가 현장에 있고, 비행 구역·비상 대응·각 드론 연결 경로를 확인했습니다.",
    );
    expect(html).not.toContain("강사 현장 확인");
    expect(html).not.toContain("비행 구역 확인");
    expect(html).not.toContain("비상 대응 확인");
    expect(html).toContain("이륙");
    expect(html).toContain("앞으로 20cm");
    expect(html).toContain("시계 방향 30°");
    expect(html).toContain("착륙");
    expect(html).toContain("모터 비상 정지");
    expect(html).toContain("<details");
  });
});
