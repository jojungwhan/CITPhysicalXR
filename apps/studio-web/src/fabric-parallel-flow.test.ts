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
    } as CoursePack;

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
});
