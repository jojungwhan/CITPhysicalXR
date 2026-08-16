import { describe, expect, it } from "vitest";

import {
  buildToolbox,
  isBlockSupported,
  NEVER_IN_STUDENT_TOOLBOX,
  type ToolboxDevice,
} from "./catalog.js";
import {
  blockForLine,
  generatePython,
  type GeneratorBinding,
  type GeneratorBlock,
} from "./generate.js";

const BINDINGS: GeneratorBinding[] = [
  { alias: "s1", deviceId: "fake-s1-main" },
  { alias: "lego", deviceId: "fake-lego-main" },
];

const S1_CAPS = ["drive.velocity", "drive.stop", "gimbal.pitch_yaw"];
const LEGO_CAPS = ["motor.run", "sensor.distance", "drive.stop"];

describe("toolbox (FR-010)", () => {
  it("hides device blocks until a device offers the capability", () => {
    const empty = buildToolbox([]);
    const types = empty.flatMap((entry) =>
      entry.blocks.map((block) => block.type),
    );
    expect(types).toContain("cit_repeat");
    expect(types).not.toContain("cit_drive_velocity");
    expect(types).not.toContain("cit_motor_run");
  });

  it("shows a block as soon as its capability appears", () => {
    const withLego = buildToolbox([
      { deviceId: "fake-lego-main", capabilities: LEGO_CAPS },
    ]);
    const types = withLego.flatMap((entry) =>
      entry.blocks.map((block) => block.type),
    );
    expect(types).toContain("cit_motor_run");
    expect(types).toContain("cit_read_distance");
    expect(types).not.toContain("cit_gimbal");
  });

  it("never offers a blaster block, whatever the device advertises (AC-25)", () => {
    const armed = buildToolbox([
      {
        deviceId: "fake-s1-main",
        capabilities: [...S1_CAPS, "weapon.blaster"],
      },
    ]);
    const types = armed.flatMap((entry) =>
      entry.blocks.map((block) => block.type),
    );
    expect(types.some((type) => type.includes("blaster"))).toBe(false);
    expect(NEVER_IN_STUDENT_TOOLBOX.has("weapon.blaster")).toBe(true);
  });

  it("rejects a stored block whose device is gone (AC-14)", () => {
    expect(isBlockSupported("cit_motor_run", [])).toBe(false);
    expect(
      isBlockSupported("cit_motor_run", [
        { deviceId: "fake-lego-main", capabilities: LEGO_CAPS },
      ]),
    ).toBe(true);
    expect(isBlockSupported("cit_repeat", [])).toBe(true);
    expect(isBlockSupported("not_a_block", [])).toBe(false);
  });

  it("drops empty categories rather than showing bare headings", () => {
    const toolbox = buildToolbox([]);
    expect(toolbox.every((entry) => entry.blocks.length > 0)).toBe(true);
  });
});

describe("generated Python (FR-011, AC-8)", () => {
  it("matches the reviewed golden output", () => {
    const blocks: GeneratorBlock[] = [
      {
        id: "b1",
        type: "cit_on_start",
        children: [
          {
            id: "b2",
            type: "cit_log",
            fields: { message: "starting" },
          },
          {
            id: "b3",
            type: "cit_repeat",
            fields: { times: 3 },
            children: [
              {
                id: "b4",
                type: "cit_drive_velocity",
                fields: { device: "s1", speed: 0.2, durationSeconds: 1 },
              },
              { id: "b5", type: "cit_wait", fields: { seconds: 0.5 } },
            ],
          },
          {
            id: "b6",
            type: "cit_parallel",
            children: [
              {
                id: "b7",
                type: "cit_stop",
                fields: { device: "s1" },
              },
              {
                id: "b8",
                type: "cit_motor_run",
                fields: {
                  device: "lego",
                  port: "A",
                  speed: 0.3,
                  durationSeconds: 1,
                },
              },
            ],
          },
        ],
      },
    ];

    const result = generatePython(blocks, BINDINGS);

    expect(result.python).toBe(
      `from citxr import device, log, parallel, sleep


lego = device("fake-lego-main")
s1 = device("fake-s1-main")


async def main():
    await log("starting")
    for _ in range(3):
        await s1.drive.velocity(speed=0.2, durationSeconds=1)
        await sleep(0.5)
    await parallel(
        s1.stop(),
        lego.motor.run(port="A", speed=0.3, durationSeconds=1),
    )
`,
    );
    expect(result.warnings).toEqual([]);
  });

  it("is byte-identical across repeated runs", () => {
    const blocks: GeneratorBlock[] = [
      {
        id: "b1",
        type: "cit_on_start",
        children: [{ id: "b2", type: "cit_wait", fields: { seconds: 1 } }],
      },
    ];
    const first = generatePython(blocks, BINDINGS).python;
    for (let run = 0; run < 5; run += 1) {
      expect(generatePython(blocks, BINDINGS).python).toBe(first);
    }
  });

  it("is stable when bindings arrive in a different order", () => {
    const blocks: GeneratorBlock[] = [
      { id: "b1", type: "cit_on_start", children: [] },
    ];
    const forwards = generatePython(blocks, BINDINGS).python;
    const backwards = generatePython(blocks, [...BINDINGS].reverse()).python;
    expect(backwards).toBe(forwards);
  });

  it("imports only what the program used", () => {
    const quiet = generatePython(
      [{ id: "b1", type: "cit_on_start", children: [] }],
      BINDINGS,
    );
    expect(quiet.usedImports).toEqual(["device"]);
    expect(quiet.python).toContain("from citxr import device\n");
    expect(quiet.python).not.toContain("parallel");
  });

  it("emits pass for an empty body rather than invalid Python", () => {
    const result = generatePython(
      [{ id: "b1", type: "cit_on_start", children: [] }],
      BINDINGS,
    );
    expect(result.python).toContain("async def main():\n    pass");
  });

  it("skips disabled blocks", () => {
    const result = generatePython(
      [
        {
          id: "b1",
          type: "cit_on_start",
          children: [
            { id: "b2", type: "cit_log", fields: { message: "kept" } },
            {
              id: "b3",
              type: "cit_log",
              fields: { message: "dropped" },
              disabled: true,
            },
          ],
        },
      ],
      BINDINGS,
    );
    expect(result.python).toContain("kept");
    expect(result.python).not.toContain("dropped");
  });

  it("renders a block comment as a Python comment", () => {
    const result = generatePython(
      [
        {
          id: "b1",
          type: "cit_on_start",
          comment: "drive a square",
          children: [],
        },
      ],
      BINDINGS,
    );
    expect(result.python).toContain("# drive a square");
  });

  it("escapes text so a quote cannot break out of the string", () => {
    const result = generatePython(
      [
        {
          id: "b1",
          type: "cit_on_start",
          children: [
            {
              id: "b2",
              type: "cit_log",
              fields: { message: 'he said "go"\nthen stopped' },
            },
          ],
        },
      ],
      BINDINGS,
    );
    expect(result.python).toContain(
      'await log("he said \\"go\\"\\nthen stopped")',
    );
  });

  it("generates the every-decorator shape from the PRD", () => {
    const result = generatePython(
      [
        {
          id: "b1",
          type: "cit_every",
          fields: { seconds: 0.5 },
          children: [
            {
              id: "b2",
              type: "cit_drive_velocity",
              fields: { device: "s1", speed: 0.2, durationSeconds: 0.5 },
            },
          ],
        },
      ],
      BINDINGS,
    );
    expect(result.python).toContain("@every(0.5)");
    expect(result.python).toContain("async def every_0_5s():");
    expect(result.usedImports).toContain("every");
  });
});

describe("warnings instead of crashes", () => {
  it("warns about an unbound device and still generates the rest", () => {
    const result = generatePython(
      [
        {
          id: "b1",
          type: "cit_on_start",
          children: [
            {
              id: "b2",
              type: "cit_drive_velocity",
              fields: { device: "quest", speed: 0.2, durationSeconds: 1 },
            },
            { id: "b3", type: "cit_log", fields: { message: "still here" } },
          ],
        },
      ],
      BINDINGS,
    );
    expect(result.warnings).toHaveLength(1);
    expect(result.warnings[0]?.blockId).toBe("b2");
    expect(result.warnings[0]?.recovery).toMatch(/Bind that device/);
    expect(result.python).toContain("still here");
  });

  it("warns about an unknown block type", () => {
    const result = generatePython(
      [{ id: "b1", type: "cit_from_the_future", fields: {} }],
      BINDINGS,
    );
    expect(result.warnings[0]?.message).toMatch(
      /not a block this version knows/,
    );
  });

  it("uses the only bound device when a block does not name one", () => {
    const result = generatePython(
      [
        {
          id: "b1",
          type: "cit_on_start",
          children: [{ id: "b2", type: "cit_stop", fields: {} }],
        },
      ],
      [{ alias: "s1", deviceId: "fake-s1-main" }],
    );
    expect(result.warnings).toEqual([]);
    expect(result.python).toContain("await s1.stop()");
  });

  it("warns rather than guessing when several devices are bound", () => {
    const result = generatePython(
      [
        {
          id: "b1",
          type: "cit_on_start",
          children: [{ id: "b2", type: "cit_stop", fields: {} }],
        },
      ],
      BINDINGS,
    );
    expect(result.warnings[0]?.message).toMatch(/does not say which device/);
  });
});

describe("source map (FR-012)", () => {
  it("maps each generated line back to the block that produced it", () => {
    const result = generatePython(
      [
        {
          id: "b1",
          type: "cit_on_start",
          children: [
            {
              id: "b2",
              type: "cit_drive_velocity",
              fields: { device: "s1", speed: 0.2, durationSeconds: 1 },
            },
          ],
        },
      ],
      BINDINGS,
    );

    const driveLine = result.python
      .split("\n")
      .findIndex((line) => line.includes("drive.velocity"));
    const mapped = blockForLine(result.sourceMap, driveLine + 1);

    expect(mapped?.blockId).toBe("b2");
    expect(mapped?.blockType).toBe("cit_drive_velocity");
    expect(mapped?.deviceAlias).toBe("s1");
  });

  it("attributes a line inside a block body to that block", () => {
    const result = generatePython(
      [
        {
          id: "b1",
          type: "cit_on_start",
          children: [{ id: "b2", type: "cit_wait", fields: { seconds: 1 } }],
        },
      ],
      BINDINGS,
    );
    expect(blockForLine(result.sourceMap, 1)).toBeUndefined();
    const last = result.sourceMap[result.sourceMap.length - 1];
    expect(blockForLine(result.sourceMap, 9999)?.blockId).toBe(last?.blockId);
  });
});

describe("loose blocks (a student drops one on the canvas)", () => {
  it("wraps a bare statement in main() rather than emitting a top-level await", () => {
    const result = generatePython(
      [
        {
          id: "b1",
          type: "cit_drive_velocity",
          fields: { device: "s1", speed: 0.25, durationSeconds: 1 },
        },
      ],
      BINDINGS,
    );

    expect(result.python).toContain("async def main():");
    expect(result.python).toContain(
      "    await s1.drive.velocity(speed=0.25, durationSeconds=1)",
    );
    // An `await` at column zero would be a SyntaxError the moment it ran.
    expect(
      result.python.split("\n").some((line) => line.startsWith("await ")),
    ).toBe(false);
  });

  it("runs loose blocks inside main() rather than a function nobody calls", () => {
    const result = generatePython(
      [
        {
          id: "b1",
          type: "cit_on_start",
          children: [
            { id: "b2", type: "cit_log", fields: { message: "first" } },
          ],
        },
        { id: "b3", type: "cit_stop", fields: { device: "s1" } },
      ],
      BINDINGS,
    );

    expect(result.python).toContain(
      'async def main():\n    await log("first")\n    await s1.stop()',
    );
    // A second def would be dead code: the host only awaits main().
    expect(result.python.match(/async def /g)).toHaveLength(1);
  });

  it("still emits event declarations at module level", () => {
    const result = generatePython(
      [
        {
          id: "b1",
          type: "cit_every",
          fields: { seconds: 1 },
          children: [
            { id: "b2", type: "cit_log", fields: { message: "tick" } },
          ],
        },
      ],
      BINDINGS,
    );
    expect(result.python).toContain("@every(1)");
    expect(result.python).not.toContain("async def main():");
  });
});

describe("LEGO blocks (FR-051, M4)", () => {
  const LEGO_HUB: ToolboxDevice = {
    deviceId: "lego-spike-01",
    capabilities: [
      "motor.run",
      "motor.run_angle",
      "drive.straight",
      "drive.turn",
      "hub.display",
      "sensor.force",
    ],
  };

  it("shows a LEGO block only when its exact capability is present", () => {
    const types = buildToolbox([LEGO_HUB]).flatMap((entry) =>
      entry.blocks.map((block) => block.type),
    );
    expect(types).toContain("cit_motor_run");
    expect(types).toContain("cit_drive_straight");
    expect(types).toContain("cit_hub_display");
    expect(types).toContain("cit_read_force");
    // The hub has one distance-free build: no distance sensor, no block.
    expect(types).not.toContain("cit_read_distance");
  });

  it("generates the same student API a hand-written program would use", () => {
    const result = generatePython(
      [
        {
          id: "b1",
          type: "cit_on_start",
          children: [
            {
              id: "b2",
              type: "cit_motor_run",
              fields: {
                device: "lego",
                port: "B",
                speed: 0.4,
                durationSeconds: 1.5,
              },
            },
            {
              id: "b3",
              type: "cit_motor_angle",
              fields: { device: "lego", port: "A", angle: 180, speed: 0.2 },
            },
            {
              id: "b4",
              type: "cit_drive_straight",
              fields: { device: "lego", distanceMillimetres: 250, speed: 0.3 },
            },
            {
              id: "b5",
              type: "cit_drive_turn",
              fields: { device: "lego", angle: -90, speed: 0.3 },
            },
            {
              id: "b6",
              type: "cit_hub_display",
              fields: { device: "lego", text: "go" },
            },
          ],
        },
      ],
      BINDINGS,
    );

    expect(result.warnings).toEqual([]);
    expect(result.python).toContain(
      'await lego.motor.run(port="B", speed=0.4, durationSeconds=1.5)',
    );
    expect(result.python).toContain(
      'await lego.motor.run_angle(port="A", angle=180, speed=0.2)',
    );
    expect(result.python).toContain(
      "await lego.drive.straight(distanceMillimetres=250, speed=0.3)",
    );
    expect(result.python).toContain(
      "await lego.drive.turn(angle=-90, speed=0.3)",
    );
    expect(result.python).toContain('await lego.hub.display(text="go")');
  });

  it("reads a force sensor as a value, not a step", () => {
    const result = generatePython(
      [
        {
          id: "b1",
          type: "cit_on_start",
          children: [
            {
              id: "b2",
              type: "cit_if",
              children: [
                {
                  id: "b3",
                  type: "cit_read_force",
                  fields: { device: "lego" },
                },
                { id: "b4", type: "cit_stop", fields: { device: "lego" } },
              ],
            },
          ],
        },
      ],
      BINDINGS,
    );

    expect(result.python).toContain(
      'if (await lego.sensor("sensor.force")).value:',
    );
  });
});
