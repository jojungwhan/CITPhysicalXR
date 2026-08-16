import * as Blockly from "blockly/core";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  generatePython,
  type GeneratorBinding,
  type SourceMapEntry,
} from "@citxr/blockly-cit";
import {
  convertToPythonMode,
  createProject,
  executableSource,
  exportProject,
  ProjectRuleError,
  setBlocksState,
  setPythonSource,
  type CitProject,
} from "@citxr/project-format";
import {
  StudentRuntimeHost,
  type ProgramError,
} from "@citxr/student-runtime-web";

import {
  readWorkspace,
  registerBlocks,
  toolboxDefinition,
  type Locale,
} from "./blockly-workspace.js";
import type {
  DeviceView,
  RuntimeClient,
  SessionView,
} from "./runtime-client.js";

interface ProgramViewProps {
  client: RuntimeClient;
  session: SessionView | null;
  devices: DeviceView[];
  locale: Locale;
}

export function ProgramView({
  client,
  session,
  devices,
  locale,
}: ProgramViewProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const workspaceRef = useRef<Blockly.WorkspaceSvg | null>(null);
  const runnerRef = useRef<StudentRuntimeHost | null>(null);
  const regenerateRef = useRef<((workspace: Blockly.Workspace) => void) | null>(
    null,
  );

  const [project, setProject] = useState<CitProject>(() =>
    createProject({
      projectId: "00000000-0000-4000-8000-000000000000",
      name: "My program",
      now: new Date().toISOString(),
    }),
  );
  const [sourceMap, setSourceMap] = useState<SourceMapEntry[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [console, setConsole] = useState<string[]>([]);
  const [failure, setFailure] = useState<ProgramError | null>(null);
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const bound = useMemo(
    () =>
      devices.filter(
        (device) => device.assignedSessionId === session?.sessionId,
      ),
    [devices, session],
  );

  const bindings = useMemo<GeneratorBinding[]>(
    () =>
      bound.map((device, index) => ({
        alias: aliasFor(device, index),
        deviceId: device.deviceId,
      })),
    [bound],
  );

  const regenerate = useCallback(
    (workspace: Blockly.Workspace) => {
      const state = readWorkspace(workspace);
      const result = generatePython(state.blocks, bindings);
      setSourceMap(result.sourceMap);
      setWarnings(
        result.warnings.map(
          (warning) => `${warning.message} ${warning.recovery}`,
        ),
      );
      setProject((current) =>
        current.authoringMode === "blocks"
          ? setBlocksState(
              current,
              state,
              result.python,
              new Date().toISOString(),
            )
          : current,
      );
    },
    [bindings],
  );

  // Create the workspace once. Recreating it on every device change would throw
  // away the student's blocks, so the toolbox is updated in place instead.
  useEffect(() => {
    if (hostRef.current === null || workspaceRef.current !== null) return;
    registerBlocks(locale);
    const workspace = Blockly.inject(hostRef.current, {
      toolbox: toolboxDefinition([], locale),
      trashcan: true,
      zoom: { controls: true, wheel: true, startScale: 0.9 },
      move: { scrollbars: true, drag: true, wheel: true },
    });

    // A first program that does something, so Run has an effect before the
    // student has dragged anything.
    Blockly.serialization.blocks.append(
      {
        type: "cit_on_start",
        id: "starter_root",
        inputs: {
          body: {
            block: {
              type: "cit_log",
              id: "starter_log",
              fields: { message: "hello from my program" },
            },
          },
        },
      },
      workspace,
    );
    // Through a ref: this listener is registered once, and `regenerate` closes
    // over `bindings`. Calling the captured copy would regenerate with the
    // bindings that existed at mount -- none -- and silently drop every device
    // line the moment a student edited a block.
    workspace.addChangeListener((event: Blockly.Events.Abstract) => {
      if (event.isUiEvent) return;
      regenerateRef.current?.(workspace);
    });
    workspaceRef.current = workspace;
    regenerate(workspace);

    return () => {
      workspace.dispose();
      workspaceRef.current = null;
    };
    // Deliberately empty: the workspace is created once, and later changes
    // reach it through the toolbox effect and the change listener. Recreating
    // it would throw away the student's blocks.
  }, []);

  useEffect(() => {
    regenerateRef.current = regenerate;
  }, [regenerate]);

  // FR-010. Devices appear and disappear; the toolbox follows them.
  useEffect(() => {
    const workspace = workspaceRef.current;
    if (workspace === null) return;
    workspace.updateToolbox(
      toolboxDefinition(
        bound.map((device) => ({
          deviceId: device.deviceId,
          capabilities: device.capabilities,
        })),
        locale,
      ),
    );
    regenerate(workspace);
  }, [bound, locale, regenerate]);

  const ensureRunner = useCallback((): StudentRuntimeHost => {
    if (runnerRef.current !== null) return runnerRef.current;
    const worker = new Worker(new URL("./student-worker.js", import.meta.url), {
      type: "module",
    });
    const host = new StudentRuntimeHost(worker, {
      call: async (method, payload) => {
        if (session === null)
          throw new Error("Start a session before running.");
        if (method === "log") {
          // `log()` is the student's own output. It is also recorded by the
          // runtime, but it has to appear in their console or the block looks
          // like it did nothing.
          setConsole((current) =>
            [...current, `${String(payload["message"] ?? "")}\n`].slice(-200),
          );
        }
        return client.studentRpc({
          sessionId: session.sessionId,
          method,
          payload,
          source:
            project.authoringMode === "blocks"
              ? "student_blocks"
              : "student_python",
          aliases: Object.fromEntries(
            bindings.map((binding) => [binding.alias, binding.deviceId]),
          ),
        });
      },
    });
    runnerRef.current = host;
    return host;
  }, [bindings, client, project.authoringMode, session]);

  const run = () => {
    if (session === null) {
      setNotice("Start a session and bind a device first.");
      return;
    }
    setConsole([]);
    setFailure(null);
    setRunning(true);
    ensureRunner().run({
      runId: `run-${Date.now()}`,
      source: executableSource(project),
      sourceMap,
      intervalIterations: 3,
      handlers: {
        onConsole: (_stream, text) =>
          setConsole((current) => [...current, text].slice(-200)),
        onDone: () => setRunning(false),
        onFailed: (error) => {
          setFailure(error);
          setRunning(false);
          highlight(error.blockId);
        },
      },
    });
  };

  const stop = () => {
    runnerRef.current?.stop();
    setRunning(false);
  };

  const highlight = (blockId: string | undefined) => {
    const workspace = workspaceRef.current;
    if (workspace === null) return;
    workspace.highlightBlock(blockId ?? null);
  };

  const convert = () => {
    try {
      setProject((current) =>
        convertToPythonMode(current, new Date().toISOString()),
      );
      setNotice(
        "This project is Python now. The blocks are kept as a snapshot, but the change is one way.",
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    }
  };

  const editPython = (text: string) => {
    try {
      setProject((current) =>
        setPythonSource(current, text, new Date().toISOString()),
      );
      setNotice(null);
    } catch (error) {
      setNotice(
        error instanceof ProjectRuleError
          ? `${error.message} ${error.recovery}`
          : String(error),
      );
    }
  };

  const download = () => {
    const text = exportProject(project);
    setConsole((current) => [
      ...current,
      `Exported ${text.length} bytes of project JSON.`,
    ]);
  };

  const pythonMode = project.authoringMode === "python";

  return (
    <>
      <section aria-labelledby="program-heading">
        <div className="bar">
          <h2 id="program-heading">Program</h2>
          <div className="row">
            <button
              type="button"
              onClick={run}
              disabled={running || session === null}
            >
              Run
            </button>
            <button type="button" onClick={stop} disabled={!running}>
              Stop program
            </button>
            <button type="button" onClick={convert} disabled={pythonMode}>
              Convert to Python
            </button>
            <button type="button" onClick={download}>
              Export
            </button>
          </div>
        </div>

        {notice !== null && <div className="notice">{notice}</div>}
        {session === null && (
          <p className="muted">
            A program needs a session and at least one bound device before it
            can run.
          </p>
        )}

        <div
          ref={hostRef}
          className={`blockly ${pythonMode ? "snapshot" : ""}`}
          aria-label="Block editor"
        />
        {pythonMode && (
          <p className="muted">
            The blocks above are a retained snapshot. The Python below is what
            runs.
          </p>
        )}
      </section>

      <section aria-labelledby="python-heading">
        <h2 id="python-heading">
          {pythonMode ? "Python" : "Generated Python"}
        </h2>
        {pythonMode ? (
          <textarea
            className="code-edit"
            value={project.pythonSource}
            onChange={(event) => editPython(event.target.value)}
            spellCheck={false}
            aria-label="Python source"
          />
        ) : (
          <pre className="code">
            {project.generatedPython || "# add a block to begin"}
          </pre>
        )}
        {warnings.length > 0 && (
          <ul className="warnings">
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="console-heading">
        <h2 id="console-heading">Console</h2>
        {failure !== null && (
          <div className="notice bad" role="alert">
            <strong>
              {failure.errorType}: {failure.message}
            </strong>
            <div className="muted">
              {failure.line !== undefined && <>Line {failure.line}. </>}
              {failure.blockType !== undefined && (
                <>Block: {failure.blockType}. </>
              )}
              {failure.deviceAlias !== undefined && (
                <>Device: {failure.deviceAlias}. </>
              )}
              {failure.suggestion}
            </div>
          </div>
        )}
        {console.length === 0 ? (
          <p className="muted">Nothing printed yet.</p>
        ) : (
          <pre className="code">{console.join("")}</pre>
        )}
      </section>
    </>
  );
}

/** A short Python name for a device, stable for a given bound order. */
function aliasFor(device: DeviceView, index: number): string {
  const fromModel = device.model.replace(/[^a-z0-9]+/gi, "_").toLowerCase();
  const trimmed = fromModel.replace(/^_+|_+$/g, "");
  return trimmed === "" ? `device_${index + 1}` : trimmed;
}
