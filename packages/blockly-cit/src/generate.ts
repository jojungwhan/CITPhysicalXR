/**
 * Blocks to readable Python (FR-011), with a source map back to block ids
 * (FR-012).
 *
 * The requirements that shape every choice here:
 *
 * - **Deterministic.** The same blocks produce byte-identical Python, every
 *   time, on every machine. Nothing iterates a Set or a Map keyed by insertion
 *   order, and nothing embeds a timestamp or a random id.
 * - **Stable between equivalent layouts.** Where the block order carries no
 *   meaning -- the device aliases at the top, the imports -- output is sorted,
 *   so dragging a block sideways does not churn the generated file.
 * - **Readable, and teachable.** The output is code a student could have
 *   written: real imports, real `async def`, no generated globals, no
 *   `_b17_tmp` names.
 *
 * The source map is emitted alongside rather than as comments, so the code a
 * student reads is not littered with machine bookkeeping.
 */

import { blockSpec, type BlockSpec } from "./catalog.js";

export interface GeneratorBlock {
  id: string;
  type: string;
  fields?: Record<string, unknown>;
  children?: GeneratorBlock[];
  disabled?: boolean;
  comment?: string;
}

export interface GeneratorBinding {
  alias: string;
  deviceId: string;
}

export interface SourceMapEntry {
  /** 1-based line in the generated Python. */
  line: number;
  blockId: string;
  blockType: string;
  /** The device the line acts on, when it acts on one. */
  deviceAlias?: string;
}

export interface GeneratorWarning {
  blockId: string;
  blockType: string;
  message: string;
  recovery: string;
}

export interface GenerateResult {
  python: string;
  sourceMap: SourceMapEntry[];
  warnings: GeneratorWarning[];
  /** SDK names the program actually used, so imports stay honest. */
  usedImports: string[];
}

const INDENT = "    ";

/** Blocks that produce their own module-level declaration. */
const TOP_LEVEL_BLOCKS: ReadonlySet<string> = new Set([
  "cit_on_start",
  "cit_every",
  "cit_on_gesture",
]);

class Emitter {
  readonly lines: string[] = [];
  readonly sourceMap: SourceMapEntry[] = [];
  readonly warnings: GeneratorWarning[] = [];
  readonly used = new Set<string>();

  emit(text: string, depth: number, origin?: SourceOrigin): void {
    this.lines.push(text === "" ? "" : `${INDENT.repeat(depth)}${text}`);
    if (origin !== undefined) {
      const entry: SourceMapEntry = {
        line: this.lines.length,
        blockId: origin.blockId,
        blockType: origin.blockType,
      };
      if (origin.deviceAlias !== undefined) {
        entry.deviceAlias = origin.deviceAlias;
      }
      this.sourceMap.push(entry);
    }
  }

  warn(warning: GeneratorWarning): void {
    this.warnings.push(warning);
  }
}

interface SourceOrigin {
  blockId: string;
  blockType: string;
  deviceAlias?: string;
}

function pythonNumber(value: unknown, fallback: number): string {
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return String(fallback);
  // Keep integers integral so `repeat 4 times` does not read `range(4.0)`.
  return Number.isInteger(numeric) ? String(numeric) : String(numeric);
}

function pythonString(value: unknown): string {
  const text = value === undefined || value === null ? "" : String(value);
  const escaped = text
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\n/g, "\\n");
  return `"${escaped}"`;
}

/** A Python identifier a student would accept, derived from an alias. */
function aliasIdentifier(alias: string): string {
  const cleaned = alias
    .replace(/[^a-zA-Z0-9_]/g, "_")
    .replace(/^([0-9])/, "_$1");
  return cleaned === "" ? "device_1" : cleaned;
}

function field(block: GeneratorBlock, name: string): unknown {
  return block.fields?.[name];
}

function defaultOf(spec: BlockSpec | undefined, name: string): number {
  const found = spec?.fields.find((entry) => entry.name === name);
  return typeof found?.default === "number" ? found.default : 0;
}

/**
 * Resolve the device a block acts on. A block naming an unbound device is a
 * warning, not a crash: the student sees the problem and the rest still
 * generates.
 */
function resolveAlias(
  block: GeneratorBlock,
  bindings: readonly GeneratorBinding[],
  emitter: Emitter,
): string | undefined {
  const requested = field(block, "device");
  if (typeof requested !== "string" || requested === "") {
    if (bindings.length === 1 && bindings[0] !== undefined) {
      return bindings[0].alias;
    }
    emitter.warn({
      blockId: block.id,
      blockType: block.type,
      message: "This block does not say which device it should act on.",
      recovery: "Pick a device in the block's device field.",
    });
    return undefined;
  }
  const known = bindings.some(
    (binding) => binding.alias === requested || binding.deviceId === requested,
  );
  if (!known) {
    emitter.warn({
      blockId: block.id,
      blockType: block.type,
      message: `This block uses '${requested}', which is not bound in this project.`,
      recovery: "Bind that device to the project, or choose one that is bound.",
    });
    return undefined;
  }
  const byDeviceId = bindings.find((binding) => binding.deviceId === requested);
  return byDeviceId?.alias ?? requested;
}

function emitBody(
  children: readonly GeneratorBlock[] | undefined,
  depth: number,
  context: Context,
): void {
  const statements = (children ?? []).filter(
    (child) => child.disabled !== true,
  );
  const before = context.emitter.lines.length;
  for (const child of statements) {
    emitStatement(child, depth, context);
  }
  // Counting lines, not blocks: a block that only produced a warning emits
  // nothing, and an empty `async def` body is an IndentationError at run time.
  if (context.emitter.lines.length === before) {
    context.emitter.emit("pass", depth);
  }
}

interface Context {
  emitter: Emitter;
  bindings: readonly GeneratorBinding[];
}

/** Expression blocks: produce a value, emit no line of their own. */
function emitExpression(block: GeneratorBlock, context: Context): string {
  const alias = resolveAlias(block, context.bindings, context.emitter);
  const target = alias === undefined ? "device" : aliasIdentifier(alias);
  switch (block.type) {
    case "cit_read_distance":
      return `(await ${target}.sensor("sensor.distance")).value`;
    case "cit_read_color":
      return `(await ${target}.sensor("sensor.color")).value`;
    default:
      context.emitter.warn({
        blockId: block.id,
        blockType: block.type,
        message: `'${block.type}' cannot be used as a value here.`,
        recovery: "Remove the block, or use it as its own step.",
      });
      return "None";
  }
}

function emitStatement(
  block: GeneratorBlock,
  depth: number,
  context: Context,
): void {
  const { emitter } = context;
  const spec = blockSpec(block.type);

  if (spec === undefined) {
    emitter.warn({
      blockId: block.id,
      blockType: block.type,
      message: `'${block.type}' is not a block this version knows.`,
      recovery:
        "Delete it, or open the project in the Studio version that made it.",
    });
    return;
  }

  if (block.comment !== undefined && block.comment !== "") {
    for (const line of block.comment.split("\n")) {
      emitter.emit(`# ${line}`, depth);
    }
  }

  const alias = spec.fields.some((entry) => entry.kind === "device")
    ? resolveAlias(block, context.bindings, emitter)
    : undefined;
  const target = alias === undefined ? undefined : aliasIdentifier(alias);
  const origin: SourceOrigin =
    alias === undefined
      ? { blockId: block.id, blockType: block.type }
      : { blockId: block.id, blockType: block.type, deviceAlias: alias };

  switch (block.type) {
    case "cit_on_start": {
      emitter.emit("async def main():", depth, origin);
      emitBody(block.children, depth + 1, context);
      break;
    }
    case "cit_every": {
      const seconds = pythonNumber(
        field(block, "seconds"),
        defaultOf(spec, "seconds"),
      );
      emitter.used.add("every");
      emitter.emit(`@every(${seconds})`, depth, origin);
      emitter.emit(`async def every_${seconds.replace(".", "_")}s():`, depth);
      emitBody(block.children, depth + 1, context);
      break;
    }
    case "cit_on_gesture": {
      const gesture = pythonString(field(block, "gesture") ?? "open_palm");
      emitter.used.add("when");
      const source = target ?? "leap";
      emitter.emit(`@when(${source}.gesture(${gesture}))`, depth, origin);
      emitter.emit("async def on_gesture():", depth);
      emitBody(block.children, depth + 1, context);
      break;
    }
    case "cit_repeat": {
      const times = pythonNumber(
        field(block, "times"),
        defaultOf(spec, "times"),
      );
      emitter.emit(`for _ in range(${times}):`, depth, origin);
      emitBody(block.children, depth + 1, context);
      break;
    }
    case "cit_if": {
      const condition = block.children?.[0];
      const rendered =
        condition === undefined ? "True" : emitExpression(condition, context);
      emitter.emit(`if ${rendered}:`, depth, origin);
      emitBody(block.children?.slice(1), depth + 1, context);
      break;
    }
    case "cit_parallel": {
      emitter.used.add("parallel");
      const actions = (block.children ?? []).filter(
        (child) => child.disabled !== true,
      );
      if (actions.length === 0) {
        emitter.emit("pass", depth, origin);
        break;
      }
      emitter.emit("await parallel(", depth, origin);
      for (const action of actions) {
        emitter.emit(`${parallelCall(action, context)},`, depth + 1, {
          blockId: action.id,
          blockType: action.type,
        });
      }
      emitter.emit(")", depth);
      break;
    }
    case "cit_wait": {
      const seconds = pythonNumber(
        field(block, "seconds"),
        defaultOf(spec, "seconds"),
      );
      emitter.used.add("sleep");
      emitter.emit(`await sleep(${seconds})`, depth, origin);
      break;
    }
    case "cit_log": {
      emitter.used.add("log");
      emitter.emit(
        `await log(${pythonString(field(block, "message"))})`,
        depth,
        origin,
      );
      break;
    }
    default: {
      const call = deviceCall(block, target, spec, context);
      if (call !== undefined) {
        emitter.emit(`await ${call}`, depth, origin);
      }
    }
  }
}

/** The bare awaitable a `parallel(...)` argument needs, with no `await`. */
function parallelCall(block: GeneratorBlock, context: Context): string {
  const spec = blockSpec(block.type);
  const alias = resolveAlias(block, context.bindings, context.emitter);
  const target = alias === undefined ? undefined : aliasIdentifier(alias);
  if (spec === undefined) return "None";
  if (block.type === "cit_wait") {
    context.emitter.used.add("sleep");
    return `sleep(${pythonNumber(field(block, "seconds"), defaultOf(spec, "seconds"))})`;
  }
  if (block.type === "cit_log") {
    context.emitter.used.add("log");
    return `log(${pythonString(field(block, "message"))})`;
  }
  return deviceCall(block, target, spec, context) ?? "None";
}

function deviceCall(
  block: GeneratorBlock,
  target: string | undefined,
  spec: BlockSpec,
  context: Context,
): string | undefined {
  if (target === undefined) return undefined;
  switch (block.type) {
    case "cit_drive_velocity": {
      const speed = pythonNumber(
        field(block, "speed"),
        defaultOf(spec, "speed"),
      );
      const duration = pythonNumber(
        field(block, "durationSeconds"),
        defaultOf(spec, "durationSeconds"),
      );
      return `${target}.drive.velocity(speed=${speed}, durationSeconds=${duration})`;
    }
    case "cit_stop":
      return `${target}.stop()`;
    case "cit_motor_speed": {
      const speed = pythonNumber(
        field(block, "speed"),
        defaultOf(spec, "speed"),
      );
      return `${target}.motor.speed(speed=${speed})`;
    }
    case "cit_gimbal": {
      const pitch = pythonNumber(
        field(block, "pitch"),
        defaultOf(spec, "pitch"),
      );
      const yaw = pythonNumber(field(block, "yaw"), defaultOf(spec, "yaw"));
      return `${target}.gimbal.pitch_yaw(pitch=${pitch}, yaw=${yaw})`;
    }
    case "cit_hud_show":
      return `${target}.xr.hud(text=${pythonString(field(block, "text"))})`;
    default:
      context.emitter.warn({
        blockId: block.id,
        blockType: block.type,
        message: `'${block.type}' has no Python form yet.`,
        recovery: "Remove the block; a later milestone adds it.",
      });
      return undefined;
  }
}

/**
 * Generate the module.
 *
 * `device` is always imported: a program with no device blocks still declares
 * its bindings, and that is the shape a student learns.
 */
export function generatePython(
  blocks: readonly GeneratorBlock[],
  bindings: readonly GeneratorBinding[],
): GenerateResult {
  const emitter = new Emitter();
  const body = new Emitter();
  const bodyContext: Context = { emitter: body, bindings };

  // A student drops a block on the canvas and expects it to run. `await` at
  // module level is not valid Python, and a second function nobody calls would
  // silently do nothing, so loose statements join main() -- the one place the
  // host actually invokes.
  const enabled = blocks.filter((block) => block.disabled !== true);
  const events = enabled.filter(
    (block) =>
      TOP_LEVEL_BLOCKS.has(block.type) && block.type !== "cit_on_start",
  );
  const starts = enabled.filter((block) => block.type === "cit_on_start");
  const loose = enabled.filter((block) => !TOP_LEVEL_BLOCKS.has(block.type));

  for (const block of events) {
    emitBody([block], 0, bodyContext);
    body.emit("", 0);
  }

  const mainSteps = [
    ...starts.flatMap((block) => block.children ?? []),
    ...loose,
  ];
  if (starts.length > 0 || loose.length > 0) {
    const anchor = starts[0] ?? loose[0];
    // The start block's own comment describes the program, so it belongs above
    // main() rather than being lost when its children are flattened into it.
    for (const start of starts) {
      if (start.comment === undefined || start.comment === "") continue;
      for (const line of start.comment.split("\n")) {
        body.emit(`# ${line}`, 0);
      }
    }
    body.emit("async def main():", 0, {
      blockId: anchor?.id ?? "main",
      blockType: anchor?.type ?? "cit_on_start",
    });
    emitBody(mainSteps, 1, bodyContext);
    body.emit("", 0);
  }

  // Imports are decided after the body, so the list matches what was used, and
  // they are ordered by the catalogue rather than by first appearance -- two
  // equivalent layouts must not produce different import lines.
  const IMPORT_ORDER = ["device", "every", "log", "parallel", "sleep", "when"];
  const used = new Set<string>(body.used);
  used.add("device");
  const imports = IMPORT_ORDER.filter((name) => used.has(name));

  emitter.emit(`from citxr import ${imports.join(", ")}`, 0);
  emitter.emit("", 0);
  emitter.emit("", 0);

  const sorted = [...bindings].sort((a, b) => a.alias.localeCompare(b.alias));
  for (const binding of sorted) {
    emitter.emit(
      `${aliasIdentifier(binding.alias)} = device(${pythonString(binding.deviceId)})`,
      0,
    );
  }
  if (sorted.length > 0) {
    emitter.emit("", 0);
    emitter.emit("", 0);
  }

  const offset = emitter.lines.length;
  for (const line of body.lines) {
    emitter.lines.push(line);
  }
  for (const entry of body.sourceMap) {
    emitter.sourceMap.push({ ...entry, line: entry.line + offset });
  }
  for (const warning of body.warnings) {
    emitter.warnings.push(warning);
  }

  // One trailing newline, no trailing blank lines: byte-stable output.
  while (
    emitter.lines.length > 0 &&
    emitter.lines[emitter.lines.length - 1] === ""
  ) {
    emitter.lines.pop();
  }

  return {
    python: `${emitter.lines.join("\n")}\n`,
    sourceMap: emitter.sourceMap,
    warnings: emitter.warnings,
    usedImports: imports,
  };
}

/** FR-012. Map a runtime traceback line back to the block that made it. */
export function blockForLine(
  sourceMap: readonly SourceMapEntry[],
  line: number,
): SourceMapEntry | undefined {
  let best: SourceMapEntry | undefined;
  for (const entry of sourceMap) {
    if (entry.line <= line && (best === undefined || entry.line > best.line)) {
      best = entry;
    }
  }
  return best;
}
