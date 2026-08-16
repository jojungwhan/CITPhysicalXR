import { describe, expect, it } from "vitest";

import {
  bindDevice,
  convertToPythonMode,
  createProject,
  duplicateProject,
  executableSource,
  exportProject,
  ProjectRuleError,
  resetToTemplate,
  setBlocksState,
  setExecutionMode,
  setPythonSource,
  unbindDevice,
} from "./project.js";
import {
  assertCitProject,
  importProject,
  migrateProject,
  ProjectValidationError,
} from "./validate.js";
import { PROJECT_SCHEMA_VERSION, type BlocksState } from "./types.js";

const NOW = "2026-01-01T00:00:00.000Z";
const LATER = "2026-01-02T00:00:00.000Z";
const ID = "11111111-1111-4111-8111-111111111111";

const newProject = () =>
  createProject({ projectId: ID, name: "Demo", now: NOW });

const BLOCKS: BlocksState = {
  blocks: [{ id: "b1", type: "cit_on_start", children: [] }],
};

describe("lifecycle (FR-001)", () => {
  it("creates a simulation-first project bound to nothing", () => {
    const project = newProject();
    expect(project.schemaVersion).toBe(PROJECT_SCHEMA_VERSION);
    expect(project.authoringMode).toBe("blocks");
    expect(project.executionMode).toBe("simulation");
    expect(project.deviceBindings).toEqual([]);
    expect(assertCitProject(project)).toBe(project);
  });

  it("round-trips through export and import", () => {
    const project = setBlocksState(newProject(), BLOCKS, "# code\n", LATER);
    expect(importProject(exportProject(project))).toEqual(project);
  });

  it("exports nested fields rather than filtering them away", () => {
    const project = setBlocksState(newProject(), BLOCKS, "# code\n", LATER);
    const text = exportProject(project);
    expect(text).toContain('"type": "cit_on_start"');
    expect(JSON.parse(text).blocksState.blocks[0].id).toBe("b1");
  });

  it("exports with stable key order so saves diff cleanly", () => {
    const project = newProject();
    expect(exportProject(project)).toBe(exportProject({ ...project }));
  });

  it("duplicates into a genuinely new project", () => {
    const copy = duplicateProject(newProject(), {
      projectId: "22222222-2222-4222-8222-222222222222",
      name: "Demo copy",
      now: LATER,
    });
    expect(copy.projectId).not.toBe(ID);
    expect(copy.createdAt).toBe(LATER);
    expect(assertCitProject(copy)).toBe(copy);
  });

  it("resets to a template without losing identity", () => {
    const edited = setBlocksState(newProject(), BLOCKS, "# mine\n", LATER);
    const reset = resetToTemplate(
      edited,
      { blocksState: { blocks: [] }, generatedPython: "" },
      LATER,
    );
    expect(reset.projectId).toBe(ID);
    expect(reset.blocksState.blocks).toEqual([]);
    expect(reset.generatedPython).toBe("");
  });

  it("records an updated timestamp on every change", () => {
    const project = setBlocksState(newProject(), BLOCKS, "", LATER);
    expect(project.updatedAt).toBe(LATER);
    expect(project.createdAt).toBe(NOW);
  });
});

describe("source-of-truth rules (FR-003)", () => {
  it("keeps blocks authoritative in block mode", () => {
    const project = setBlocksState(
      newProject(),
      BLOCKS,
      "# generated\n",
      LATER,
    );
    expect(executableSource(project)).toBe("# generated\n");
  });

  it("refuses a direct Python edit in block mode, and says why", () => {
    expect(() => setPythonSource(newProject(), "print(1)", LATER)).toThrow(
      ProjectRuleError,
    );
    try {
      setPythonSource(newProject(), "print(1)", LATER);
    } catch (error) {
      expect((error as ProjectRuleError).recovery).toMatch(
        /Convert the project/,
      );
    }
  });

  it("retains the last block snapshot when converting to Python", () => {
    const blocks = setBlocksState(newProject(), BLOCKS, "# generated\n", LATER);
    const python = convertToPythonMode(blocks, LATER);

    expect(python.authoringMode).toBe("python");
    expect(python.lastBlocksSnapshot).toEqual(BLOCKS);
    expect(python.pythonSource).toBe("# generated\n");
    expect(executableSource(python)).toBe("# generated\n");
  });

  it("refuses block edits once the project is Python", () => {
    const python = convertToPythonMode(newProject(), LATER);
    expect(() => setBlocksState(python, BLOCKS, "", LATER)).toThrow(
      ProjectRuleError,
    );
  });

  it("converting twice is a no-op rather than losing the snapshot", () => {
    const once = convertToPythonMode(
      setBlocksState(newProject(), BLOCKS, "# generated\n", LATER),
      LATER,
    );
    const edited = setPythonSource(once, "print('mine')", LATER);
    const twice = convertToPythonMode(edited, LATER);
    expect(twice).toBe(edited);
    expect(twice.pythonSource).toBe("print('mine')");
  });

  it("offers no way to turn Python back into blocks", async () => {
    const module = await import("./project.js");
    const names = Object.keys(module);
    expect(
      names.some((name) => /pythonToBlocks|toBlocks|decompile/i.test(name)),
    ).toBe(false);
  });
});

describe("device bindings (FR-019)", () => {
  it("binds an alias to an exact device id", () => {
    const project = bindDevice(
      newProject(),
      { alias: "s1", deviceId: "fake-s1-main" },
      LATER,
    );
    expect(project.deviceBindings).toEqual([
      { alias: "s1", deviceId: "fake-s1-main" },
    ]);
  });

  it("refuses to point one alias at two devices", () => {
    const project = bindDevice(
      newProject(),
      { alias: "s1", deviceId: "fake-s1-main" },
      LATER,
    );
    expect(() =>
      bindDevice(project, { alias: "s1", deviceId: "fake-lego-main" }, LATER),
    ).toThrow(/already points at a different device/);
  });

  it("rebinding the same pair is idempotent", () => {
    const once = bindDevice(
      newProject(),
      { alias: "s1", deviceId: "fake-s1-main" },
      LATER,
    );
    const twice = bindDevice(
      once,
      { alias: "s1", deviceId: "fake-s1-main" },
      LATER,
    );
    expect(twice.deviceBindings).toHaveLength(1);
  });

  it("unbinds by alias", () => {
    const project = unbindDevice(
      bindDevice(
        newProject(),
        { alias: "s1", deviceId: "fake-s1-main" },
        LATER,
      ),
      "s1",
      LATER,
    );
    expect(project.deviceBindings).toEqual([]);
  });
});

describe("validation and migration (FR-002)", () => {
  it("refuses a file that is not an object", () => {
    expect(() => migrateProject([])).toThrow(ProjectValidationError);
    expect(() => importProject("not json")).toThrow(ProjectValidationError);
  });

  it("refuses a newer schema version by name rather than guessing", () => {
    expect(() =>
      migrateProject({ ...newProject(), schemaVersion: 99 }),
    ).toThrow(/newer than this build understands/);
  });

  it("refuses a version with no registered migration", () => {
    expect(() => migrateProject({ schemaVersion: 0 })).toThrow(
      /no migration is registered from schemaVersion 0/,
    );
  });

  it("rejects an unknown field rather than silently keeping it", () => {
    expect(() => assertCitProject({ ...newProject(), sneaky: true })).toThrow(
      ProjectValidationError,
    );
  });

  it("rejects a binding alias that is not a Python identifier", () => {
    expect(() =>
      assertCitProject({
        ...newProject(),
        deviceBindings: [{ alias: "My Robot", deviceId: "fake-s1-main" }],
      }),
    ).toThrow(ProjectValidationError);
  });

  it("accepts a project that carries a retained snapshot", () => {
    const python = convertToPythonMode(
      setBlocksState(newProject(), BLOCKS, "# generated\n", LATER),
      LATER,
    );
    expect(assertCitProject(python)).toBe(python);
  });
});

describe("execution mode (FR-062)", () => {
  it("is simulation until deliberately changed", () => {
    expect(newProject().executionMode).toBe("simulation");
    expect(
      setExecutionMode(newProject(), "physical", LATER).executionMode,
    ).toBe("physical");
  });
});
