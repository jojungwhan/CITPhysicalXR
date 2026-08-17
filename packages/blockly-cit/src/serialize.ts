/**
 * The project's blocks, back into something Blockly can load (FR-001, FR-003).
 *
 * The project file stores our own block shape, not Blockly's, so the format
 * survives a Blockly upgrade. That translation was one-way until now: a project
 * could be written to disk and never read back into an editor, so "Open" loaded
 * a document the student could not see -- and the workspace they *could* see
 * then overwrote it on the next save.
 *
 * This is the other direction. It is here rather than in the Studio because it
 * needs the catalog to know which input a child belongs to, and because the
 * Studio's Blockly module cannot be imported by a test: Blockly's Node entry
 * point needs `jsdom`, which Milestone 3 dropped rather than widen the licence
 * allowlist. Nothing in this file imports Blockly.
 */

import { blockSpec } from "./catalog.js";
import type { GeneratorBlock } from "./generate.js";

/** The subset of Blockly's block state this translation produces. */
export interface SerializedBlock {
  type: string;
  id?: string;
  enabled?: boolean;
  fields?: Record<string, unknown>;
  icons?: Record<string, unknown>;
  inputs?: Record<string, { block?: SerializedBlock }>;
  next?: { block?: SerializedBlock };
}

/**
 * Turn stored blocks into Blockly's load format, one entry per top-level block.
 *
 * A block in the catalog has at most one value input and at most one statement
 * input, so a stored child can be routed by what it is: a reporter block goes to
 * the value input, and statement blocks chain into the statement input in the
 * order they were stored. That is why this translation is exact rather than a
 * guess, and a test asserts the catalog keeps that property.
 */
export function toWorkspaceBlocks(
  blocks: readonly GeneratorBlock[],
): SerializedBlock[] {
  return blocks.map((block) => toSerialized(block));
}

function toSerialized(node: GeneratorBlock): SerializedBlock {
  const spec = blockSpec(node.type);
  const serialized: SerializedBlock = { type: node.type, id: node.id };

  if (node.fields !== undefined && Object.keys(node.fields).length > 0) {
    // Only fields the catalog still declares: a project written by an older
    // catalog must open, without carrying a field the block no longer has.
    const declared = new Set(
      (spec?.fields ?? [])
        .filter((field) => field.kind !== "statement" && field.kind !== "value")
        .map((field) => field.name),
    );
    const fields: Record<string, unknown> = {};
    for (const [name, value] of Object.entries(node.fields)) {
      if (declared.has(name)) fields[name] = value;
    }
    if (Object.keys(fields).length > 0) serialized.fields = fields;
  }

  if (node.disabled === true) serialized.enabled = false;
  if (node.comment !== undefined && node.comment !== "") {
    serialized.icons = { comment: { text: node.comment } };
  }

  const valueInput = spec?.fields.find((field) => field.kind === "value")?.name;
  const statementInput = spec?.fields.find(
    (field) => field.kind === "statement",
  )?.name;

  const inputs: Record<string, { block?: SerializedBlock }> = {};
  const statements: GeneratorBlock[] = [];
  for (const child of node.children ?? []) {
    const childSpec = blockSpec(child.type);
    const isValue = childSpec !== undefined && !childSpec.statement;
    if (isValue && valueInput !== undefined) {
      inputs[valueInput] = { block: toSerialized(child) };
      continue;
    }
    statements.push(child);
  }

  if (statementInput !== undefined && statements.length > 0) {
    inputs[statementInput] = { block: chain(statements) };
  }
  if (Object.keys(inputs).length > 0) serialized.inputs = inputs;

  return serialized;
}

/** Statements stored side by side are connected one after another. */
function chain(nodes: readonly GeneratorBlock[]): SerializedBlock {
  const [head, ...rest] = nodes;
  const serialized = toSerialized(head as GeneratorBlock);
  if (rest.length > 0) serialized.next = { block: chain(rest) };
  return serialized;
}
