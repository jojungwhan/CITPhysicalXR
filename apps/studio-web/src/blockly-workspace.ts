/**
 * Registers the CIT block catalog with Blockly and reads a workspace back out
 * as the plain `BlocksState` the project file stores.
 *
 * Blockly's own serialization is deliberately not what we persist. The project
 * format has to survive a Blockly upgrade, so the stored shape is ours and this
 * module is the only translator.
 */

import * as Blockly from "blockly/core";
import * as EnMessages from "blockly/msg/en";
import * as KoMessages from "blockly/msg/ko";
import {
  BLOCK_CATALOG,
  buildToolbox,
  type BlockSpec,
  type ToolboxDevice,
} from "@citxr/blockly-cit";
import type { BlockNode, BlocksState } from "@citxr/project-format";

export type Locale = "en" | "ko";

const STATEMENT_COLOUR: Record<string, number> = {
  events: 40,
  control: 210,
  logic: 210,
  loops: 120,
  variables: 330,
  functions: 290,
  math: 230,
  text: 160,
  lists: 260,
  time: 60,
  parallel: 20,
  devices: 0,
  sensors: 180,
  quest: 270,
  leap: 300,
  robomaster: 350,
  lego: 90,
};

let registered = false;

/** Define every catalog block on the shared Blockly registry, once. */
export function registerBlocks(locale: Locale): void {
  // UI 11.5. Blockly's own strings live in a separate catalog; without it the
  // library throws while building a block's ARIA label, so this is required
  // before inject(), not a nicety.
  Blockly.setLocale(
    (locale === "ko" ? KoMessages : EnMessages) as unknown as Record<
      string,
      string
    >,
  );

  if (registered) return;
  registered = true;

  for (const spec of BLOCK_CATALOG) {
    Blockly.Blocks[spec.type] = {
      init(this: Blockly.Block): void {
        applySpec(this, spec, locale);
      },
    };
  }
}

function applySpec(
  block: Blockly.Block,
  spec: BlockSpec,
  locale: Locale,
): void {
  block.appendDummyInput().appendField(spec.label[locale]);

  for (const field of spec.fields) {
    switch (field.kind) {
      case "number":
        block
          .appendDummyInput()
          .appendField(field.label[locale])
          .appendField(
            new Blockly.FieldNumber(
              typeof field.default === "number" ? field.default : 0,
              field.min,
              field.max,
            ),
            field.name,
          );
        break;
      case "text":
        block
          .appendDummyInput()
          .appendField(field.label[locale])
          .appendField(
            new Blockly.FieldTextInput(String(field.default ?? "")),
            field.name,
          );
        break;
      case "device":
        block
          .appendDummyInput()
          .appendField(field.label[locale])
          .appendField(
            new Blockly.FieldTextInput(String(field.default ?? "")),
            field.name,
          );
        break;
      case "choice":
        block
          .appendDummyInput()
          .appendField(field.label[locale])
          .appendField(
            new Blockly.FieldDropdown(
              (field.choices ?? ["-"]).map(
                (choice) => [choice, choice] as [string, string],
              ),
            ),
            field.name,
          );
        break;
      case "statement":
        block.appendStatementInput(field.name).appendField(field.label[locale]);
        break;
      case "value":
        block.appendValueInput(field.name).appendField(field.label[locale]);
        break;
    }
  }

  if (spec.statement) {
    block.setPreviousStatement(true, null);
    block.setNextStatement(true, null);
  } else {
    block.setOutput(true, null);
  }
  block.setColour(STATEMENT_COLOUR[spec.category] ?? 200);
  block.setTooltip(spec.label[locale]);
}

/** FR-010. The toolbox XML follows the connected devices, nothing else. */
export function toolboxDefinition(
  devices: readonly ToolboxDevice[],
  locale: Locale,
): Blockly.utils.toolbox.ToolboxDefinition {
  const categories = buildToolbox(devices).map((entry) => ({
    kind: "category",
    name: categoryLabel(entry.category, locale),
    contents: entry.blocks.map((block) => ({
      kind: "block",
      type: block.type,
    })),
  }));
  return { kind: "categoryToolbox", contents: categories };
}

const CATEGORY_LABELS: Record<string, { en: string; ko: string }> = {
  events: { en: "Events", ko: "이벤트" },
  control: { en: "Control", ko: "제어" },
  logic: { en: "Logic", ko: "논리" },
  loops: { en: "Loops", ko: "반복" },
  variables: { en: "Variables", ko: "변수" },
  functions: { en: "Functions", ko: "함수" },
  math: { en: "Math", ko: "수학" },
  text: { en: "Text", ko: "텍스트" },
  lists: { en: "Lists", ko: "리스트" },
  time: { en: "Time", ko: "시간" },
  parallel: { en: "Parallel", ko: "동시 실행" },
  devices: { en: "Devices", ko: "장치" },
  sensors: { en: "Sensors", ko: "센서" },
  quest: { en: "Quest", ko: "퀘스트" },
  leap: { en: "Leap Motion", ko: "립 모션" },
  robomaster: { en: "RoboMaster", ko: "로보마스터" },
  lego: { en: "LEGO", ko: "레고" },
};

function categoryLabel(category: string, locale: Locale): string {
  return CATEGORY_LABELS[category]?.[locale] ?? category;
}

/** Read the workspace into the shape the project file stores. */
export function readWorkspace(workspace: Blockly.Workspace): BlocksState {
  const roots = workspace
    .getTopBlocks(true)
    .filter((block) => block.type in Blockly.Blocks);
  return { blocks: roots.map(toNode) };
}

function toNode(block: Blockly.Block): BlockNode {
  const node: BlockNode = { id: block.id, type: block.type };

  const fields: Record<string, unknown> = {};
  for (const input of block.inputList) {
    for (const field of input.fieldRow) {
      const name = field.name;
      if (name === undefined || name === "") continue;
      const value = field.getValue();
      fields[name] = value === null ? undefined : value;
    }
  }
  if (Object.keys(fields).length > 0) node.fields = fields;

  const children: BlockNode[] = [];
  for (const input of block.inputList) {
    const target = input.connection?.targetBlock();
    if (target === null || target === undefined) continue;
    for (
      let current: Blockly.Block | null = target;
      current;
      current = current.getNextBlock()
    ) {
      children.push(toNode(current));
    }
  }
  if (children.length > 0) node.children = children;

  if (!block.isEnabled()) node.disabled = true;
  const comment = block.getCommentText();
  if (comment !== null && comment !== "") node.comment = comment;

  return node;
}
