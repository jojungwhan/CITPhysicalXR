import type { CoursePack } from "@citxr/protocol";
import { describe, expect, it } from "vitest";

import { parallelFlowGroups } from "./fabric-parallel-flow.js";

describe("parallel Fabric flow presentation", () => {
  it("groups enabled outputs while leaving ordinary flows separate", () => {
    const coursePack = {
      flows: [
        {
          flowId: "robot",
          enabled: true,
          parallelGroup: "cue",
          trigger: { event: "interaction.intent.start" },
          target: { role: "ground_output" },
          command: { action: "mobility.ground.set_velocity" },
        },
        {
          flowId: "display",
          enabled: true,
          parallelGroup: "cue",
          trigger: { event: "interaction.intent.start" },
          target: { role: "message_output" },
          command: { action: "display.text.render" },
        },
        {
          flowId: "disabled",
          enabled: false,
          parallelGroup: "cue",
          trigger: { event: "interaction.intent.start" },
          target: { role: "unused_output" },
          command: { action: "display.text.render" },
        },
        {
          flowId: "ordinary",
          enabled: true,
          trigger: { event: "interaction.intent.start" },
          target: { role: "single_output" },
          command: { action: "display.text.render" },
        },
      ],
    } as unknown as CoursePack;

    expect(parallelFlowGroups(coursePack)).toEqual([
      {
        groupId: "cue",
        trigger: "interaction.intent.start",
        outputs: [
          {
            flowId: "robot",
            role: "ground_output",
            action: "mobility.ground.set_velocity",
          },
          {
            flowId: "display",
            role: "message_output",
            action: "display.text.render",
          },
        ],
      },
    ]);
  });

  it("shows one output when several gestures target the same role and action", () => {
    const coursePack = {
      flows: [
        {
          flowId: "ring-forward",
          enabled: true,
          parallelGroup: "ring-control",
          trigger: {
            event: "interaction.gesture.smart_ring",
            payloadEquals: { gesture: "scroll_up" },
          },
          target: { role: "ground_output_1" },
          command: { action: "mobility.ground.set_velocity" },
        },
        {
          flowId: "ring-stop",
          enabled: true,
          parallelGroup: "ring-control",
          trigger: {
            event: "interaction.gesture.smart_ring",
            payloadEquals: { gesture: "tap" },
          },
          target: { role: "ground_output_1" },
          command: { action: "mobility.ground.set_velocity" },
        },
      ],
    } as unknown as CoursePack;

    expect(parallelFlowGroups(coursePack)[0]?.outputs).toEqual([
      {
        flowId: "ring-forward",
        role: "ground_output_1",
        action: "mobility.ground.set_velocity",
      },
    ]);
  });

  it("expands bounded group and payload-selected roles from the course recipe", () => {
    const coursePack = {
      flows: [
        {
          flowId: "all-lights",
          enabled: true,
          parallelGroup: "wearable-control",
          trigger: { event: "interaction.intent.device_control" },
          target: {
            roles: ["ground_output_1", "ground_output_2"],
            requiredCapability: "robot.light.set",
          },
          command: { action: "robot.light.set" },
        },
        {
          flowId: "exact-plug",
          enabled: true,
          parallelGroup: "wearable-control",
          trigger: { event: "interaction.intent.device_control" },
          target: {
            roleFromPayload: "targetRole",
            allowedRoles: ["power_output_1", "power_output_2"],
            requiredCapability: "power.switch.set",
          },
          command: { action: "power.switch.set" },
        },
      ],
    } as unknown as CoursePack;

    expect(parallelFlowGroups(coursePack)[0]?.outputs).toEqual([
      {
        flowId: "all-lights",
        role: "ground_output_1",
        action: "robot.light.set",
      },
      {
        flowId: "all-lights",
        role: "ground_output_2",
        action: "robot.light.set",
      },
      {
        flowId: "exact-plug",
        role: "power_output_1",
        action: "power.switch.set",
      },
      {
        flowId: "exact-plug",
        role: "power_output_2",
        action: "power.switch.set",
      },
    ]);
  });
});
