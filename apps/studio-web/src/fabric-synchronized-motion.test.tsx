import type { IntegrationNode } from "@citxr/protocol";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { fabricTranslatorFor } from "./fabric-i18n.js";
import {
  synchronizedInputKinds,
  synchronizedMotionCommands,
} from "./fabric-synchronized-motion.js";
import { FabricSynchronizedMotionPanel } from "./FabricSynchronizedMotionPanel.js";

const node = (
  nodeId: string,
  model: string,
  capabilities: string[] = [],
): IntegrationNode =>
  ({
    nodeId,
    pluginId: model === "tello" ? "cit.tello" : "cit.test",
    displayName: nodeId,
    connectionState: "connected",
    healthState: "healthy",
    metadata: { model },
    consumedCapabilities: capabilities.map((name) => ({ name })),
  }) as unknown as IntegrationNode;

describe("synchronized motor control", () => {
  it("fans one semantic direction out to ground robots and only opted-in Tellos", () => {
    const groundRobots = [
      { role: "ground_output_1", node: node("bolt", "sphero-bolt") },
      { role: "ground_output_2", node: node("ollie", "sphero-ollie") },
    ];
    const drones = [
      {
        role: "safety_drone_1",
        node: node("tello", "tello", [
          "mobility.flight.takeoff",
          "mobility.flight.move",
          "mobility.flight.rotate",
          "mobility.flight.land",
          "mobility.flight.emergency_stop",
        ]),
      },
    ];

    expect(
      synchronizedMotionCommands({
        direction: "backward",
        groundRobots,
        drones,
        includeTello: false,
        flightConfirmed: true,
      }),
    ).toHaveLength(2);
    expect(
      synchronizedMotionCommands({
        direction: "backward",
        groundRobots,
        drones,
        includeTello: true,
        flightConfirmed: true,
      }),
    ).toEqual([
      expect.objectContaining({
        role: "ground_output_1",
        action: "mobility.ground.nudge",
        parameters: { direction: "backward" },
      }),
      expect.objectContaining({
        role: "ground_output_2",
        action: "mobility.ground.nudge",
        parameters: { direction: "backward" },
      }),
      expect.objectContaining({
        role: "safety_drone_1",
        action: "mobility.flight.move",
        parameters: expect.objectContaining({
          direction: "back",
          distanceCentimeters: 20,
        }),
      }),
    ]);
  });

  it("never maps group stop to a Tello motor-stop or landing command", () => {
    const commands = synchronizedMotionCommands({
      direction: "stop",
      groundRobots: [
        { role: "ground_output_1", node: node("bolt", "sphero-bolt") },
      ],
      drones: [
        {
          role: "safety_drone_1",
          node: node("tello", "tello", [
            "mobility.flight.takeoff",
            "mobility.flight.move",
            "mobility.flight.rotate",
            "mobility.flight.land",
            "mobility.flight.emergency_stop",
          ]),
        },
      ],
      includeTello: true,
      flightConfirmed: true,
    });

    expect(commands).toEqual([
      expect.objectContaining({
        action: "mobility.ground.stop",
        kind: "ground",
      }),
    ]);
  });

  it("recognizes the four approved semantic input families", () => {
    expect(
      synchronizedInputKinds([
        node("g2", "even-realities-g2"),
        node("ring", "even-realities-r1"),
        node("meta", "meta-rayban"),
        node("brain", "mindwave-mobile2"),
      ]),
    ).toEqual(new Set(["g2", "r1", "meta", "mindwave"]));
  });

  it("keeps Tello excluded until both flight confirmation and opt-in exist", () => {
    const html = renderToStaticMarkup(
      <FabricSynchronizedMotionPanel
        enabled={true}
        includeTello={false}
        groundCount={2}
        telloCount={1}
        availableInputs={new Set(["g2", "r1", "mindwave"])}
        busy={false}
        canManage={true}
        flightConfirmed={false}
        onEnabledChange={vi.fn()}
        onIncludeTelloChange={vi.fn()}
        onAssignInputs={vi.fn()}
        onMove={vi.fn()}
        t={fabricTranslatorFor("ko")}
      />,
    );

    expect(html).toContain("BOLT·Ollie 2대");
    expect(html).toContain("Tello 포함 (1대)");
    expect(html).toContain("비행 안전 확인 후 Tello 제어에서 먼저 이륙하세요");
    expect(html).toContain("G2 음성");
    expect(html).toContain("R1 링");
    expect(html).toContain("MindWave 깜박임");
  });

  it("keeps the synchronized-control option visible before devices connect", () => {
    const html = renderToStaticMarkup(
      <FabricSynchronizedMotionPanel
        enabled={false}
        includeTello={false}
        groundCount={0}
        telloCount={0}
        availableInputs={new Set()}
        busy={false}
        canManage={true}
        flightConfirmed={false}
        onEnabledChange={vi.fn()}
        onIncludeTelloChange={vi.fn()}
        onAssignInputs={vi.fn()}
        onMove={vi.fn()}
        t={fabricTranslatorFor("ko")}
      />,
    );

    expect(html).toContain("동기 이동");
    expect(html).toContain("BOLT·Ollie 0대");
    expect(html).toMatch(/type="checkbox"[^>]*disabled/);
  });
});
