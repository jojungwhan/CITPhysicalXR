/**
 * The block catalog (FR-009) and the capability rules that show or hide a block
 * (FR-010).
 *
 * A block declares which device capability it needs. The toolbox is then a pure
 * function of the connected devices: no capability, no block. That is how
 * AC-14 ("unsupported blocks hidden") and AC-25 ("no default S1 blaster") hold
 * without anyone remembering to hide something.
 *
 * Labels carry Korean and English (UI 11.5). The identifier is what the project
 * file stores and never changes with the display language.
 */

export type BlockCategory =
  | "events"
  | "control"
  | "logic"
  | "loops"
  | "variables"
  | "functions"
  | "math"
  | "text"
  | "lists"
  | "time"
  | "parallel"
  | "devices"
  | "sensors"
  | "quest"
  | "leap"
  | "robomaster"
  | "lego";

export const BLOCK_CATEGORIES: readonly BlockCategory[] = [
  "events",
  "control",
  "logic",
  "loops",
  "variables",
  "functions",
  "math",
  "text",
  "lists",
  "time",
  "parallel",
  "devices",
  "sensors",
  "quest",
  "leap",
  "robomaster",
  "lego",
] as const;

export interface LocalizedLabel {
  en: string;
  ko: string;
}

export interface BlockFieldSpec {
  name: string;
  kind: "number" | "text" | "device" | "choice" | "statement" | "value";
  label: LocalizedLabel;
  choices?: readonly string[];
  min?: number;
  max?: number;
  default?: string | number;
}

export interface BlockSpec {
  type: string;
  category: BlockCategory;
  label: LocalizedLabel;
  /** The capability a bound device must advertise for this block to appear. */
  requiresCapability?: string;
  /** True when the block emits a statement; false when it emits an expression. */
  statement: boolean;
  fields: readonly BlockFieldSpec[];
}

const label = (en: string, ko: string): LocalizedLabel => ({ en, ko });

/**
 * Blocks that never touch a device. Always available, so a student can write a
 * program before anything is connected.
 */
const CORE_BLOCKS: readonly BlockSpec[] = [
  {
    type: "cit_on_start",
    category: "events",
    label: label("when program starts", "프로그램을 시작하면"),
    statement: true,
    fields: [{ name: "body", kind: "statement", label: label("do", "실행") }],
  },
  {
    type: "cit_every",
    category: "events",
    label: label("every N seconds", "N초마다"),
    statement: true,
    fields: [
      {
        name: "seconds",
        kind: "number",
        label: label("seconds", "초"),
        min: 0.1,
        max: 3600,
        default: 1,
      },
      { name: "body", kind: "statement", label: label("do", "실행") },
    ],
  },
  {
    type: "cit_repeat",
    category: "loops",
    label: label("repeat N times", "N번 반복"),
    statement: true,
    fields: [
      {
        name: "times",
        kind: "number",
        label: label("times", "횟수"),
        min: 1,
        max: 1000,
        default: 4,
      },
      { name: "body", kind: "statement", label: label("do", "실행") },
    ],
  },
  {
    type: "cit_wait",
    category: "time",
    label: label("wait N seconds", "N초 기다리기"),
    statement: true,
    fields: [
      {
        name: "seconds",
        kind: "number",
        label: label("seconds", "초"),
        min: 0,
        max: 600,
        default: 1,
      },
    ],
  },
  {
    type: "cit_log",
    category: "text",
    label: label("print message", "메시지 출력"),
    statement: true,
    fields: [
      {
        name: "message",
        kind: "text",
        label: label("message", "메시지"),
        default: "hello",
      },
    ],
  },
  {
    type: "cit_parallel",
    category: "parallel",
    label: label("do all at the same time", "동시에 실행"),
    statement: true,
    fields: [
      { name: "body", kind: "statement", label: label("actions", "동작") },
    ],
  },
  {
    type: "cit_if",
    category: "logic",
    label: label("if", "만약"),
    statement: true,
    fields: [
      { name: "condition", kind: "value", label: label("condition", "조건") },
      { name: "body", kind: "statement", label: label("then", "그러면") },
    ],
  },
];

/** Device blocks. Each one names the capability that must be present. */
const DEVICE_BLOCKS: readonly BlockSpec[] = [
  {
    type: "cit_drive_velocity",
    category: "devices",
    label: label("drive", "주행"),
    requiresCapability: "drive.velocity",
    statement: true,
    fields: [
      { name: "device", kind: "device", label: label("device", "장치") },
      {
        name: "speed",
        kind: "number",
        label: label("speed", "속도"),
        min: -1,
        max: 1,
        default: 0.2,
      },
      {
        name: "durationSeconds",
        kind: "number",
        label: label("for seconds", "지속 시간(초)"),
        min: 0.1,
        max: 10,
        default: 1,
      },
    ],
  },
  {
    type: "cit_stop",
    category: "devices",
    label: label("stop", "정지"),
    requiresCapability: "drive.stop",
    statement: true,
    fields: [
      { name: "device", kind: "device", label: label("device", "장치") },
    ],
  },
  {
    type: "cit_motor_run",
    category: "lego",
    label: label("run motor", "모터 돌리기"),
    requiresCapability: "motor.run",
    statement: true,
    fields: [
      { name: "device", kind: "device", label: label("device", "장치") },
      {
        name: "port",
        kind: "choice",
        label: label("port", "포트"),
        choices: ["A", "B", "C", "D", "E", "F"],
        default: "A",
      },
      // Speed is a fraction of full power on every device, LEGO included. A
      // hub wants degrees per second and the S1 wants metres per second, and
      // the adapter is where that conversion belongs -- one number a student
      // can carry from one robot to the next, and one number the safety
      // supervisor can bound without knowing which robot it is.
      {
        name: "speed",
        kind: "number",
        label: label("speed", "속도"),
        min: -1,
        max: 1,
        default: 0.3,
      },
      {
        name: "durationSeconds",
        kind: "number",
        label: label("for seconds", "지속 시간(초)"),
        min: 0.1,
        max: 10,
        default: 1,
      },
    ],
  },
  {
    type: "cit_motor_angle",
    category: "lego",
    label: label("turn motor by angle", "모터를 각도만큼 돌리기"),
    requiresCapability: "motor.run_angle",
    statement: true,
    fields: [
      { name: "device", kind: "device", label: label("device", "장치") },
      {
        name: "port",
        kind: "choice",
        label: label("port", "포트"),
        choices: ["A", "B", "C", "D", "E", "F"],
        default: "A",
      },
      {
        name: "angle",
        kind: "number",
        label: label("angle", "각도"),
        min: -3600,
        max: 3600,
        default: 90,
      },
      {
        name: "speed",
        kind: "number",
        label: label("speed", "속도"),
        min: -1,
        max: 1,
        default: 0.3,
      },
    ],
  },
  {
    type: "cit_drive_straight",
    category: "lego",
    label: label("drive straight", "직진하기"),
    requiresCapability: "drive.straight",
    statement: true,
    fields: [
      { name: "device", kind: "device", label: label("device", "장치") },
      {
        name: "distanceMillimetres",
        kind: "number",
        label: label("millimetres", "밀리미터"),
        min: -2000,
        max: 2000,
        default: 200,
      },
      {
        name: "speed",
        kind: "number",
        label: label("speed", "속도"),
        min: -1,
        max: 1,
        default: 0.3,
      },
    ],
  },
  {
    type: "cit_drive_turn",
    category: "lego",
    label: label("turn on the spot", "제자리에서 돌기"),
    requiresCapability: "drive.turn",
    statement: true,
    fields: [
      { name: "device", kind: "device", label: label("device", "장치") },
      {
        name: "angle",
        kind: "number",
        label: label("angle", "각도"),
        min: -720,
        max: 720,
        default: 90,
      },
      {
        name: "speed",
        kind: "number",
        label: label("speed", "속도"),
        min: -1,
        max: 1,
        default: 0.3,
      },
    ],
  },
  {
    type: "cit_hub_display",
    category: "lego",
    label: label("show on hub", "허브에 표시"),
    requiresCapability: "hub.display",
    statement: true,
    fields: [
      { name: "device", kind: "device", label: label("device", "장치") },
      {
        name: "text",
        kind: "text",
        label: label("text", "내용"),
        default: "hi",
      },
    ],
  },
  {
    type: "cit_gimbal",
    category: "robomaster",
    label: label("move gimbal", "짐벌 이동"),
    requiresCapability: "gimbal.pitch_yaw",
    statement: true,
    fields: [
      { name: "device", kind: "device", label: label("device", "장치") },
      {
        name: "pitch",
        kind: "number",
        label: label("pitch", "상하"),
        min: -55,
        max: 55,
        default: 0,
      },
      {
        name: "yaw",
        kind: "number",
        label: label("yaw", "좌우"),
        min: -180,
        max: 180,
        default: 0,
      },
    ],
  },
  {
    type: "cit_read_distance",
    category: "sensors",
    label: label("distance sensor", "거리 센서"),
    requiresCapability: "sensor.distance",
    statement: false,
    fields: [
      { name: "device", kind: "device", label: label("device", "장치") },
    ],
  },
  {
    type: "cit_read_color",
    category: "sensors",
    label: label("colour sensor", "색상 센서"),
    requiresCapability: "sensor.color",
    statement: false,
    fields: [
      { name: "device", kind: "device", label: label("device", "장치") },
    ],
  },
  {
    type: "cit_read_force",
    category: "sensors",
    label: label("force sensor", "힘 센서"),
    requiresCapability: "sensor.force",
    statement: false,
    fields: [
      { name: "device", kind: "device", label: label("device", "장치") },
    ],
  },
  {
    type: "cit_hud_show",
    category: "quest",
    label: label("show on headset", "헤드셋에 표시"),
    requiresCapability: "xr.hud",
    statement: true,
    fields: [
      { name: "device", kind: "device", label: label("device", "장치") },
      {
        name: "text",
        kind: "text",
        label: label("text", "내용"),
        default: "hello",
      },
    ],
  },
  {
    type: "cit_on_gesture",
    category: "leap",
    label: label("when hand gesture", "손동작이 감지되면"),
    requiresCapability: "input.gesture",
    statement: true,
    fields: [
      { name: "device", kind: "device", label: label("device", "장치") },
      {
        name: "gesture",
        kind: "choice",
        label: label("gesture", "동작"),
        choices: ["open_palm", "fist", "pinch"],
        default: "open_palm",
      },
      { name: "body", kind: "statement", label: label("do", "실행") },
    ],
  },
];

export const BLOCK_CATALOG: readonly BlockSpec[] = [
  ...CORE_BLOCKS,
  ...DEVICE_BLOCKS,
];

const BY_TYPE = new Map(BLOCK_CATALOG.map((block) => [block.type, block]));

export function blockSpec(type: string): BlockSpec | undefined {
  return BY_TYPE.get(type);
}

/**
 * AC-25 and FR-068. Some capabilities never reach a student toolbox, whatever a
 * device advertises. This is a denial list, so a new device cannot introduce a
 * blaster block by declaring one.
 */
export const NEVER_IN_STUDENT_TOOLBOX: ReadonlySet<string> = new Set([
  "weapon.blaster",
  "weapon.fire",
]);

export interface ToolboxDevice {
  deviceId: string;
  alias?: string;
  capabilities: readonly string[];
}

export interface ToolboxCategory {
  category: BlockCategory;
  blocks: readonly BlockSpec[];
}

/**
 * FR-010. The toolbox is derived, never stored: connect a LEGO hub and motor
 * blocks appear; unplug it and they leave.
 */
export function buildToolbox(
  devices: readonly ToolboxDevice[],
): ToolboxCategory[] {
  const available = new Set<string>();
  for (const device of devices) {
    for (const capability of device.capabilities) {
      if (!NEVER_IN_STUDENT_TOOLBOX.has(capability)) {
        available.add(capability);
      }
    }
  }

  const visible = BLOCK_CATALOG.filter(
    (block) =>
      block.requiresCapability === undefined ||
      available.has(block.requiresCapability),
  );

  return BLOCK_CATEGORIES.map((category) => ({
    category,
    blocks: visible.filter((block) => block.category === category),
  })).filter((entry) => entry.blocks.length > 0);
}

/** FR-010 / AC-14. Used to reject a stored block whose device went away. */
export function isBlockSupported(
  type: string,
  devices: readonly ToolboxDevice[],
): boolean {
  const spec = blockSpec(type);
  if (spec === undefined) return false;
  if (spec.requiresCapability === undefined) return true;
  if (NEVER_IN_STUDENT_TOOLBOX.has(spec.requiresCapability)) return false;
  return devices.some((device) =>
    device.capabilities.includes(spec.requiresCapability as string),
  );
}
