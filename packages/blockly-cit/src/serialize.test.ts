import { describe, expect, it } from "vitest";

import { BLOCK_CATALOG } from "./catalog.js";
import { toWorkspaceBlocks } from "./serialize.js";

describe("stored blocks back into Blockly's load format (FR-001)", () => {
  it("keeps the property the translation depends on", () => {
    // A stored child says what it is, not which socket it came from, so the
    // routing below is only exact while a block has at most one value input
    // and at most one statement input. If a catalog entry ever grows a second
    // of either, this fails here rather than by silently reassembling a
    // student's program wrongly.
    for (const spec of BLOCK_CATALOG) {
      const values = spec.fields.filter((field) => field.kind === "value");
      const statements = spec.fields.filter(
        (field) => field.kind === "statement",
      );
      expect(values.length, `${spec.type} value inputs`).toBeLessThanOrEqual(1);
      expect(
        statements.length,
        `${spec.type} statement inputs`,
      ).toBeLessThanOrEqual(1);
    }
  });

  it("puts a block's fields and id back", () => {
    const [block] = toWorkspaceBlocks([
      { id: "b1", type: "cit_wait", fields: { seconds: 2 } },
    ]);

    expect(block).toEqual({
      type: "cit_wait",
      id: "b1",
      fields: { seconds: 2 },
    });
  });

  it("chains stored statements into the statement input", () => {
    const [start] = toWorkspaceBlocks([
      {
        id: "root",
        type: "cit_on_start",
        children: [
          { id: "a", type: "cit_log", fields: { message: "one" } },
          { id: "b", type: "cit_log", fields: { message: "two" } },
        ],
      },
    ]);

    const body = start?.inputs?.["body"]?.block;
    expect(body?.id).toBe("a");
    expect(body?.next?.block?.id).toBe("b");
  });

  it("routes a reporter to the value input and statements to the body", () => {
    const [conditional] = toWorkspaceBlocks([
      {
        id: "if1",
        type: "cit_if",
        children: [
          { id: "cond", type: "cit_read_distance", fields: { device: "s1" } },
          { id: "then", type: "cit_log", fields: { message: "yes" } },
        ],
      },
    ]);

    expect(conditional?.inputs?.["condition"]?.block?.id).toBe("cond");
    expect(conditional?.inputs?.["body"]?.block?.id).toBe("then");
  });

  it("carries a disabled block and its comment", () => {
    const [block] = toWorkspaceBlocks([
      { id: "b1", type: "cit_log", disabled: true, comment: "not yet" },
    ]);

    expect(block?.enabled).toBe(false);
    expect(block?.icons).toEqual({ comment: { text: "not yet" } });
  });

  it("drops a field the catalog no longer declares", () => {
    // A project written by an older catalog has to open. Handing Blockly a
    // field the block does not have is how that turns into a blank editor.
    const [block] = toWorkspaceBlocks([
      { id: "b1", type: "cit_wait", fields: { seconds: 1, retired: true } },
    ]);

    expect(block?.fields).toEqual({ seconds: 1 });
  });

  it("loads a block type the catalog does not know at all", () => {
    const [block] = toWorkspaceBlocks([
      { id: "b1", type: "cit_from_the_future" },
    ]);

    expect(block).toEqual({ type: "cit_from_the_future", id: "b1" });
  });
});
