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

import { Autosave, type SaveState } from "./autosave.js";
import {
  loadWorkspace,
  readWorkspace,
  registerBlocks,
  toolboxDefinition,
} from "./blockly-workspace.js";
import { exportFilename, saveTextAsFile } from "./download.js";
import type { Locale, Translate } from "./i18n.js";
import type {
  CommandOutcome,
  DeviceView,
  Identity,
  RuntimeClient,
  SessionView,
} from "./runtime-client.js";
import { useDeadman } from "./useDeadman.js";

const DRIVE_STEPS = [
  {
    key: "drive.forward",
    args: { speed: 0.3, heading: 0, durationSeconds: 1 },
  },
  { key: "drive.back", args: { speed: -0.3, heading: 0, durationSeconds: 1 } },
  { key: "drive.left", args: { speed: 0.3, heading: -90, durationSeconds: 1 } },
  { key: "drive.right", args: { speed: 0.3, heading: 90, durationSeconds: 1 } },
] as const;

const TERMINAL = ["stopped", "completed", "failed", "emergency_stopped"];

interface ProgramViewProps {
  client: RuntimeClient;
  identity: Identity;
  session: SessionView | null;
  setSession: (session: SessionView | null) => void;
  devices: DeviceView[];
  locale: Locale;
  t: Translate;
  run: (work: () => Promise<void>) => Promise<void>;
  busy: boolean;
  refresh: () => Promise<void>;
}

export function ProgramView({
  client,
  identity,
  session,
  setSession,
  devices,
  locale,
  t,
  run,
  busy,
  refresh,
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
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const [sourceMap, setSourceMap] = useState<SourceMapEntry[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [console, setConsole] = useState<string[]>([]);
  const [failure, setFailure] = useState<ProgramError | null>(null);
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<CommandOutcome | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  // What a change is, for the purpose of saving one. Not `updatedAt`: opening a
  // project restamps it, and a project that saves itself because it was opened
  // rotates its own backup for nothing.
  const contentOf = (candidate: CitProject): string =>
    exportProject({ ...candidate, updatedAt: "" });
  // The document as the runtime last stored it. `null` means this project has
  // never been on disk, and nothing is autosaved until it has been: a project
  // the Studio invented at page load has an id every other tab invented too,
  // and autosaving it would have two students writing one file.
  const savedTextRef = useRef<string | null>(null);
  // FR-062. Simulation unless an instructor deliberately chooses otherwise, and
  // a student has no control that changes it.
  const [mode, setMode] = useState<"simulation" | "physical">("simulation");
  const [policyId, setPolicyId] = useState("simulation-only");
  const isInstructor = identity.role === "instructor";

  const selected =
    devices.find((device) => device.deviceId === selectedDeviceId) ?? null;
  const deadman = useDeadman(client, selected?.deviceId ?? null);

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

  // FR-001. Open whatever the Projects view asked for.
  useEffect(() => {
    const wanted = window.localStorage.getItem("citxr.openProject");
    if (wanted === null) return;
    window.localStorage.removeItem("citxr.openProject");
    void run(async () => {
      const stored = (await client.project(wanted)) as unknown as CitProject;
      const workspace = workspaceRef.current;
      // The blocks first: the change listener regenerates from the workspace,
      // so a project set in state while the editor still holds the previous
      // program is a project about to be overwritten by it.
      if (workspace !== null) loadWorkspace(workspace, stored.blocksState);
      setProject(stored);
      savedTextRef.current = contentOf(stored);
      setSaveState("saved");
      setNotice(null);
    });
  }, [client, run]);

  // FR-001. Edits reach the disk without anybody pressing anything.
  //
  // Created once and kept in a ref: an autosave rebuilt on every render would
  // lose the edit it was holding, which is the failure it exists to prevent.
  const autosaveRef = useRef<Autosave<CitProject> | null>(null);
  if (autosaveRef.current === null) {
    autosaveRef.current = new Autosave<CitProject>({
      onState: setSaveState,
      save: async (document) => {
        const text = contentOf(document);
        await client.saveProject(
          document.projectId,
          document as unknown as Record<string, unknown>,
        );
        savedTextRef.current = text;
      },
    });
  }

  useEffect(() => {
    const autosave = autosaveRef.current;
    return () => {
      // Leaving the Program view is not a decision to discard the last edit.
      autosave?.flushNow();
      autosave?.stop();
    };
  }, []);

  useEffect(() => {
    if (savedTextRef.current === null) return;
    const text = contentOf(project);
    if (text === savedTextRef.current) return;
    autosaveRef.current?.change(project);
  }, [project]);

  const save = () =>
    run(async () => {
      const text = contentOf(project);
      await client.saveProject(
        project.projectId,
        project as unknown as Record<string, unknown>,
      );
      savedTextRef.current = text;
      setSaveState("saved");
      setNotice(t("projects.saved"));
    });

  const ensureRunner = useCallback((): StudentRuntimeHost => {
    if (runnerRef.current !== null) return runnerRef.current;
    const worker = new Worker(new URL("./student-worker.js", import.meta.url), {
      type: "module",
    });
    const host = new StudentRuntimeHost(worker, {
      call: async (method, payload) => {
        if (session === null) throw new Error(t("program.needsSession"));
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
          aliases: Object.fromEntries(
            bindings.map((binding) => [binding.alias, binding.deviceId]),
          ),
        });
      },
    });
    runnerRef.current = host;
    return host;
  }, [bindings, client, session, t]);

  // ------------------------------------------------------------------ session

  const startSession = () =>
    run(async () => {
      // End the previous session first. A session holds its devices until it
      // finishes, so without this the second lesson finds every robot taken.
      if (session !== null && !TERMINAL.includes(session.state)) {
        await client.endSession(session.sessionId);
      }
      setSession(
        await client.createSession({
          projectId: project.projectId,
          executionMode: mode,
          safetyPolicyId: policyId,
        }),
      );
      setOutcome(null);
      await refresh();
    });

  const bindSelected = () =>
    run(async () => {
      if (session === null || selected === null) return;
      setSession(
        await client.bindDevices(session.sessionId, [selected.deviceId]),
      );
      await refresh();
    });

  const validate = () =>
    run(async () => {
      if (session === null) return;
      setSession(await client.validate(session.sessionId));
    });

  // FR-066 step 4. The instructor's own action, and the only one that grants
  // physical movement. The runtime refuses it for anyone else regardless of
  // whether this button is rendered.
  const armSelected = () =>
    run(async () => {
      if (session === null || selected === null) return;
      await client.arm({
        sessionId: session.sessionId,
        deviceId: selected.deviceId,
      });
      await refresh();
    });

  // -------------------------------------------------------------------- drive

  const canDrive =
    session !== null &&
    selected !== null &&
    bound.some((device) => device.deviceId === selected.deviceId) &&
    session.state === "ready" &&
    selected.state === "connected";

  const drive = (args: Record<string, unknown>) =>
    run(async () => {
      if (session === null || selected === null) return;
      setOutcome(
        await client.send({
          sessionId: session.sessionId,
          deviceId: selected.deviceId,
          capability: "drive.velocity",
          action: "set",
          arguments: args,
          inputConfidence: 1,
        }),
      );
      await refresh();
    });

  // ------------------------------------------------------------------ program

  const runProgram = () => {
    if (session === null) {
      setNotice(t("program.needsSession"));
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

  const stopProgram = () => {
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
      setNotice(t("program.converted"));
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

  // FR-002. The project leaves as the same versioned document the runtime
  // stores, so a student can take their work home on a memory stick.
  const download = () => {
    const name = saveTextAsFile(
      exportProject(project),
      exportFilename("project", project.name, new Date(), "json"),
      "application/json",
    );
    setNotice(t("download.saved", { name }));
  };

  const pythonMode = project.authoringMode === "python";

  return (
    <>
      <section aria-labelledby="session-heading">
        <h2 id="session-heading">{t("session.heading")}</h2>
        <div className="row">
          <button type="button" onClick={startSession} disabled={busy}>
            {t("session.new")}
          </button>
          <button
            type="button"
            onClick={bindSelected}
            disabled={busy || session === null || selected === null}
          >
            {t("session.bind")}
          </button>
          <button
            type="button"
            onClick={validate}
            disabled={busy || session === null || bound.length === 0}
          >
            {t("session.validate")}
          </button>
          {isInstructor && (
            <button
              type="button"
              onClick={armSelected}
              disabled={
                busy ||
                session === null ||
                selected === null ||
                session.state !== "ready"
              }
            >
              {t("devices.arm")}
            </button>
          )}
        </div>

        {isInstructor ? (
          <div className="row">
            <label>
              <span>{t("session.mode")}</span>
              <select
                value={mode}
                onChange={(event) => {
                  const chosen = event.target.value as
                    "simulation" | "physical";
                  setMode(chosen);
                  setPolicyId(
                    chosen === "physical"
                      ? "classroom-physical"
                      : "simulation-only",
                  );
                }}
              >
                <option value="simulation">{t("session.simulation")}</option>
                <option value="physical">{t("session.physical")}</option>
              </select>
            </label>
            <label>
              <span>{t("session.safetyProfile")}</span>
              <input
                value={policyId}
                onChange={(event) => setPolicyId(event.target.value)}
                maxLength={128}
              />
            </label>
          </div>
        ) : (
          <p className="muted">{t("session.instructorOnly")}</p>
        )}
        {session === null ? (
          <p className="muted">{t("session.none")}</p>
        ) : (
          <p className="muted">
            <code>{session.sessionId}</code> · {t("session.state")}{" "}
            <strong>{session.state}</strong> · {session.executionMode} ·{" "}
            {t("session.bound")}:{" "}
            {bound.length > 0
              ? bound.map((device) => device.deviceId).join(", ")
              : t("session.nothingBound")}
          </p>
        )}
      </section>

      <section aria-labelledby="pick-heading">
        <h2 id="pick-heading">{t("devices.heading")}</h2>
        <div className="cards">
          {devices.map((device) => (
            <button
              key={device.deviceId}
              type="button"
              className={`card ${device.deviceId === selectedDeviceId ? "selected" : ""}`}
              onClick={() => setSelectedDeviceId(device.deviceId)}
              aria-pressed={device.deviceId === selectedDeviceId}
            >
              <span className="card-title">{device.displayName}</span>
              <span
                className={`pill ${device.state === "connected" ? "ok" : "warn"}`}
              >
                {device.state}
              </span>
              <span className="muted">{device.model}</span>
              <span className="muted">
                {device.physical
                  ? t("devices.physical")
                  : t("devices.simulated")}
                {device.armed ? ` · ${t("devices.armed")}` : ""}
              </span>
            </button>
          ))}
          {devices.length === 0 && <p className="muted">{t("devices.none")}</p>}
        </div>
      </section>

      <section aria-labelledby="drive-heading">
        <h2 id="drive-heading">{t("drive.heading")}</h2>
        {!canDrive && <p className="muted">{t("drive.blocked")}</p>}

        <div className="row">
          <button
            type="button"
            className={deadman.held ? "deadman held" : "deadman"}
            onPointerDown={deadman.hold}
            onPointerUp={deadman.release}
            onPointerLeave={deadman.release}
            onPointerCancel={deadman.release}
            onBlur={deadman.release}
            disabled={selected === null}
          >
            {deadman.held ? t("drive.deadmanHeld") : t("drive.holdDeadman")}
          </button>
        </div>
        <p className="muted">{t("drive.deadmanExplain")}</p>

        <div className="row">
          {DRIVE_STEPS.map((step) => (
            <button
              key={step.key}
              type="button"
              onClick={() => drive(step.args)}
              disabled={busy || !canDrive}
            >
              {t(step.key)}
            </button>
          ))}
          <button
            type="button"
            onClick={() => drive({ speed: 9.9, durationSeconds: 30 })}
            disabled={busy || !canDrive}
          >
            {t("drive.overspeed")}
          </button>
        </div>

        {outcome !== null && (
          <div className={`notice ${outcome.accepted ? "ok" : "bad"}`}>
            {outcome.accepted ? (
              <>
                {t("drive.accepted")} · {outcome.status}
                {outcome.clampedFields && outcome.clampedFields.length > 0 && (
                  <>
                    {" "}
                    · {t("drive.clamped")}: {outcome.clampedFields.join(", ")}
                  </>
                )}
              </>
            ) : (
              <>
                {t("drive.refused")} · {outcome.code} — {outcome.message}
                {outcome.recovery && (
                  <div className="muted">{outcome.recovery}</div>
                )}
              </>
            )}
          </div>
        )}
      </section>

      <section aria-labelledby="program-heading">
        <div className="bar">
          <h2 id="program-heading">{t("program.heading")}</h2>
          <div className="row">
            <button
              type="button"
              onClick={runProgram}
              disabled={running || session === null}
            >
              {t("program.run")}
            </button>
            <button type="button" onClick={stopProgram} disabled={!running}>
              {t("program.stop")}
            </button>
            <button type="button" onClick={convert} disabled={pythonMode}>
              {t("program.convert")}
            </button>
            <button type="button" onClick={save} disabled={busy}>
              {t("projects.save")}
            </button>
            <button type="button" onClick={download}>
              {t("program.export")}
            </button>
            {/* Read on every render that changes `saveState`, and the two are
                always set together. UI 11.6: a student can tell whether their
                work is on the runtime without opening another page. */}
            <span className="muted save-state" role="status">
              {savedTextRef.current === null
                ? t("projects.notStored")
                : saveState === "saving"
                  ? t("projects.saving")
                  : saveState === "unsaved"
                    ? t("projects.unsaved")
                    : saveState === "failed"
                      ? t("projects.autosaveFailed")
                      : t("projects.saved")}
            </span>
          </div>
        </div>

        {notice !== null && <div className="notice">{notice}</div>}
        {session === null && (
          <p className="muted">{t("program.needsSession")}</p>
        )}

        <div
          ref={hostRef}
          className={`blockly ${pythonMode ? "snapshot" : ""}`}
          aria-label={t("program.blockEditor")}
        />
        {pythonMode && <p className="muted">{t("program.blocksSnapshot")}</p>}
      </section>

      <section aria-labelledby="python-heading">
        <h2 id="python-heading">
          {pythonMode ? t("program.python") : t("program.generatedPython")}
        </h2>
        {pythonMode ? (
          <textarea
            className="code-edit"
            value={project.pythonSource}
            onChange={(event) => editPython(event.target.value)}
            spellCheck={false}
            aria-label={t("program.python")}
          />
        ) : (
          <pre className="code">
            {project.generatedPython || t("program.emptyProgram")}
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
        <h2 id="console-heading">{t("program.console")}</h2>
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
          <p className="muted">{t("program.consoleEmpty")}</p>
        ) : (
          <pre className="code">{console.join("")}</pre>
        )}
        <p className="muted">
          {identity.displayName} · {identity.role}
        </p>
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
