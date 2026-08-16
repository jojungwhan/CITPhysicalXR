/**
 * The student worker entry point.
 *
 * Vite bundles this as a real Web Worker. It loads Pyodide, installs the citxr
 * package into the virtual filesystem, and then does nothing but run the
 * student's program and relay the five allowlisted calls back to the page.
 *
 * Nothing in this file reads the network, the DOM, or storage. Pyodide's own
 * filesystem is a virtual one that exists only inside this worker.
 */

import { loadPyodide, type PyodideInterface } from "pyodide";

import { WORKER_PYTHON } from "@citxr/student-runtime-web";

import { CITXR_SOURCES } from "./citxr-sources.js";

interface PendingCall {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
}

const pending = new Map<string, PendingCall>();
let pyodide: PyodideInterface | undefined;
let callCounter = 0;
let currentRunId = "";

const post = (message: unknown): void => {
  (self as unknown as { postMessage(value: unknown): void }).postMessage(
    message,
  );
};

/** Ask the page for one allowlisted runtime call and await its answer. */
async function send(method: string, payload: unknown): Promise<unknown> {
  callCounter += 1;
  const callId = `c${callCounter}`;
  const plain =
    payload !== null && typeof payload === "object" && "toJs" in payload
      ? (payload as { toJs(options: unknown): unknown }).toJs({
          dict_converter: Object.fromEntries,
        })
      : payload;

  return new Promise<unknown>((resolve, reject) => {
    pending.set(callId, { resolve, reject });
    post({ kind: "rpc", callId, method, payload: plain });
  });
}

function emit(stream: string, text: string): void {
  post({ kind: "console", runId: currentRunId, stream, text });
}

async function ensurePyodide(): Promise<PyodideInterface> {
  if (pyodide !== undefined) return pyodide;
  // Vendored beside the bundle by the vite config, never a CDN: the Studio has
  // to work on a school network with no outbound access (FR-085).
  const indexURL = new URL("../pyodide/", import.meta.url).href;
  const instance = await loadPyodide({ indexURL });

  // Write the citxr package into the worker's virtual filesystem. The student
  // imports it exactly as they would a normal package; there is no host module
  // reachable from inside.
  instance.FS.mkdir("/lib/citxr");
  for (const [name, source] of Object.entries(CITXR_SOURCES)) {
    instance.FS.writeFile(`/lib/citxr/${name}`, source, { encoding: "utf8" });
  }
  await instance.runPythonAsync(`
import sys
sys.path.insert(0, "/lib")
`);
  await instance.runPythonAsync(WORKER_PYTHON);
  pyodide = instance;
  return instance;
}

async function run(
  runId: string,
  source: string,
  intervalIterations: number,
): Promise<void> {
  currentRunId = runId;
  try {
    const instance = await ensurePyodide();
    const runner = instance.globals.get("run_student_program") as (
      source: string,
      send: unknown,
      emit: unknown,
      iterations: number,
    ) => Promise<unknown>;

    const raw = await runner(source, send, emit, intervalIterations);
    const outcome = (
      raw !== null && typeof raw === "object" && "toJs" in raw
        ? (raw as { toJs(options: unknown): unknown }).toJs({
            dict_converter: Object.fromEntries,
          })
        : raw
    ) as {
      ok: boolean;
      errorType?: string;
      message?: string;
      line?: number | null;
      traceback?: string;
    };

    if (outcome.ok) {
      post({ kind: "done", runId });
      return;
    }
    const error: Record<string, unknown> = {
      message: outcome.message ?? "The program stopped with an error.",
      errorType: outcome.errorType ?? "Error",
    };
    if (typeof outcome.line === "number") error["line"] = outcome.line;
    if (outcome.traceback !== undefined) error["traceback"] = outcome.traceback;
    post({ kind: "failed", runId, error });
  } catch (caught) {
    post({
      kind: "failed",
      runId,
      error: {
        message: caught instanceof Error ? caught.message : String(caught),
        errorType: "RuntimeError",
      },
    });
  }
}

self.addEventListener("message", (event: MessageEvent) => {
  const message = event.data as {
    kind: string;
    runId?: string;
    source?: string;
    intervalIterations?: number;
    callId?: string;
    result?: unknown;
    error?: string;
  };

  switch (message.kind) {
    case "run":
      void run(
        message.runId ?? "",
        message.source ?? "",
        message.intervalIterations ?? 3,
      );
      return;
    case "stop":
      void pyodide?.runPythonAsync("cancel_student_program()");
      return;
    case "rpc-result": {
      const waiting = pending.get(message.callId ?? "");
      if (waiting === undefined) return;
      pending.delete(message.callId ?? "");
      if (message.error !== undefined) {
        waiting.reject(new Error(message.error));
      } else {
        waiting.resolve(message.result);
      }
      return;
    }
    default:
      return;
  }
});

post({ kind: "ready" });
