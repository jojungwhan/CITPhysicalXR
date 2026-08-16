/**
 * Project lifecycle and the source-of-truth rules.
 *
 * FR-003 is the whole point of this module, and it is a rule about honesty:
 *
 * - In block mode the blocks are authoritative and the Python is *output*.
 *   Editing that output is therefore not a save; it is a request to change what
 *   the project fundamentally is, and it has to be made explicitly.
 * - In Python mode the Python is authoritative, and the last block snapshot is
 *   retained so the student can see what they came from.
 * - There is no `pythonToBlocks`. The PRD forbids claiming arbitrary Python can
 *   be converted back, so this module does not offer a function that would have
 *   to lie.
 *
 * Every function returns a new project. Nothing here mutates its input, so an
 * editor can hold history without defensive copying.
 */

import {
  type AuthoringMode,
  type BlocksState,
  type CitProject,
  type DeviceBinding,
  type ExecutionMode,
  EMPTY_BLOCKS_STATE,
  PROJECT_SCHEMA_VERSION,
} from "./types.js";

export interface CreateProjectOptions {
  projectId: string;
  name: string;
  now: string;
  targetProfile?: string;
  safetyPreset?: string;
  authoringMode?: AuthoringMode;
  deviceBindings?: DeviceBinding[];
}

export class ProjectRuleError extends Error {
  readonly recovery: string;

  constructor(message: string, recovery: string) {
    super(message);
    this.name = "ProjectRuleError";
    this.recovery = recovery;
  }
}

/** FR-001 create. Simulation-first (FR-062) and bound to nothing. */
export function createProject(options: CreateProjectOptions): CitProject {
  return {
    schemaVersion: PROJECT_SCHEMA_VERSION,
    projectId: options.projectId,
    name: options.name,
    authoringMode: options.authoringMode ?? "blocks",
    blocksState: EMPTY_BLOCKS_STATE,
    generatedPython: "",
    pythonSource: "",
    lastBlocksSnapshot: null,
    targetProfile: options.targetProfile ?? "simulation-default",
    deviceBindings: options.deviceBindings ?? [],
    questScene: {},
    safetyPreset: options.safetyPreset ?? "student-low-speed",
    executionMode: "simulation",
    assets: [],
    createdAt: options.now,
    updatedAt: options.now,
  };
}

function touch(project: CitProject, now: string): CitProject {
  return { ...project, updatedAt: now };
}

/**
 * FR-003. Replacing the blocks also replaces the generated Python, because the
 * Python is output and stale output is worse than none.
 */
export function setBlocksState(
  project: CitProject,
  blocksState: BlocksState,
  generatedPython: string,
  now: string,
): CitProject {
  if (project.authoringMode !== "blocks") {
    throw new ProjectRuleError(
      "This project is in Python mode, so its blocks are a retained snapshot and cannot be edited.",
      "Create a new block project, or keep editing the Python source.",
    );
  }
  return touch({ ...project, blocksState, generatedPython }, now);
}

/**
 * FR-003. A direct edit to generated Python is refused in block mode. The
 * student must convert first, which is a decision, not a keystroke.
 */
export function setPythonSource(
  project: CitProject,
  pythonSource: string,
  now: string,
): CitProject {
  if (project.authoringMode !== "python") {
    throw new ProjectRuleError(
      "Generated Python is output in block mode, so editing it here would be overwritten by the next block change.",
      "Convert the project to Python mode first. The blocks are kept as a snapshot, but the change is one way.",
    );
  }
  return touch({ ...project, pythonSource }, now);
}

/**
 * FR-003. One way, and deliberately so: the last block state is retained for
 * reference, but nothing here claims it can be regenerated from the Python.
 */
export function convertToPythonMode(
  project: CitProject,
  now: string,
): CitProject {
  if (project.authoringMode === "python") {
    return project;
  }
  return touch(
    {
      ...project,
      authoringMode: "python",
      lastBlocksSnapshot: project.blocksState,
      pythonSource: project.pythonSource || project.generatedPython,
    },
    now,
  );
}

/** FR-001 reset. Keeps identity and bindings; discards the student's work. */
export function resetToTemplate(
  project: CitProject,
  template: Pick<CitProject, "blocksState" | "generatedPython">,
  now: string,
): CitProject {
  return touch(
    {
      ...project,
      authoringMode: "blocks",
      blocksState: template.blocksState,
      generatedPython: template.generatedPython,
      pythonSource: "",
      lastBlocksSnapshot: null,
    },
    now,
  );
}

/** FR-001 duplicate. A copy is a new project, never a second name for one. */
export function duplicateProject(
  project: CitProject,
  options: { projectId: string; name: string; now: string },
): CitProject {
  return {
    ...project,
    projectId: options.projectId,
    name: options.name,
    createdAt: options.now,
    updatedAt: options.now,
  };
}

export function bindDevice(
  project: CitProject,
  binding: DeviceBinding,
  now: string,
): CitProject {
  const clashes = project.deviceBindings.some(
    (existing) =>
      existing.alias === binding.alias &&
      existing.deviceId !== binding.deviceId,
  );
  if (clashes) {
    throw new ProjectRuleError(
      `The alias '${binding.alias}' already points at a different device.`,
      "Pick a different alias, or remove the existing binding first.",
    );
  }
  const kept = project.deviceBindings.filter(
    (existing) => existing.alias !== binding.alias,
  );
  return touch({ ...project, deviceBindings: [...kept, binding] }, now);
}

export function unbindDevice(
  project: CitProject,
  alias: string,
  now: string,
): CitProject {
  return touch(
    {
      ...project,
      deviceBindings: project.deviceBindings.filter(
        (binding) => binding.alias !== alias,
      ),
    },
    now,
  );
}

/**
 * FR-062. Physical mode is a deliberate choice on the project, and it is still
 * only a request: the runtime decides whether a physical session may start.
 */
export function setExecutionMode(
  project: CitProject,
  executionMode: ExecutionMode,
  now: string,
): CitProject {
  return touch({ ...project, executionMode }, now);
}

/** The source a runner should execute, given the current mode. */
export function executableSource(project: CitProject): string {
  return project.authoringMode === "python"
    ? project.pythonSource
    : project.generatedPython;
}

/**
 * Recursively order object keys.
 *
 * `JSON.stringify(value, keyArray)` looks like it would do this, but that form
 * is an allowlist applied at every depth, so it silently drops nested fields
 * whose names are not in the top-level key list.
 */
function sortKeysDeep(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(sortKeysDeep);
  }
  if (value === null || typeof value !== "object") {
    return value;
  }
  const source = value as Record<string, unknown>;
  const ordered: Record<string, unknown> = {};
  for (const key of Object.keys(source).sort()) {
    ordered[key] = sortKeysDeep(source[key]);
  }
  return ordered;
}

/** FR-001 export. Stable key order so a diff between saves is meaningful. */
export function exportProject(project: CitProject): string {
  return `${JSON.stringify(sortKeysDeep(project), null, 2)}\n`;
}
