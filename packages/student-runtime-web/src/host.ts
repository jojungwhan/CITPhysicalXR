/**
 * The page's half of the student runtime.
 *
 * It owns the worker, forwards the worker's five allowlisted calls to the local
 * runtime, and refuses anything else. This is the second gate: even if the
 * worker were compromised, the only thing on the other side of `postMessage` is
 * this switch, and every branch ends at an ordinary runtime endpoint that the
 * safety supervisor still evaluates.
 */

import {
  explainError,
  isRpcMethod,
  type ProgramError,
  type SourceMapEntry,
  type WorkerMessage,
} from "./protocol.js";

export interface RuntimeCaller {
  /** Sends one allowlisted call to the local runtime and returns its answer. */
  call(method: string, payload: Record<string, unknown>): Promise<unknown>;
}

export interface StudentRunHandlers {
  onConsole?: (stream: "stdout" | "stderr", text: string) => void;
  onDone?: () => void;
  onFailed?: (error: ProgramError) => void;
}

export interface StudentWorkerLike {
  postMessage(message: unknown): void;
  addEventListener(
    type: "message",
    listener: (event: { data: unknown }) => void,
  ): void;
  terminate(): void;
}

export class RpcNotPermittedError extends Error {
  constructor(method: string) {
    super(
      `The student runtime asked for '${method}', which is not one of the five permitted calls.`,
    );
    this.name = "RpcNotPermittedError";
  }
}

/**
 * Bridges one worker to one runtime. A host serves a single session; making a
 * second run means making a second host, so state cannot leak between students.
 */
export class StudentRuntimeHost {
  private readonly worker: StudentWorkerLike;
  private readonly runtime: RuntimeCaller;
  private sourceMap: readonly SourceMapEntry[] = [];
  private handlers: StudentRunHandlers = {};
  private runId = "";

  constructor(worker: StudentWorkerLike, runtime: RuntimeCaller) {
    this.worker = worker;
    this.runtime = runtime;
    this.worker.addEventListener("message", (event) => {
      void this.receive(event.data as WorkerMessage);
    });
  }

  run(options: {
    runId: string;
    source: string;
    sourceMap?: readonly SourceMapEntry[];
    intervalIterations?: number;
    handlers?: StudentRunHandlers;
  }): void {
    this.runId = options.runId;
    this.sourceMap = options.sourceMap ?? [];
    this.handlers = options.handlers ?? {};
    const message: Record<string, unknown> = {
      kind: "run",
      runId: options.runId,
      source: options.source,
    };
    if (options.intervalIterations !== undefined) {
      message["intervalIterations"] = options.intervalIterations;
    }
    this.worker.postMessage(message);
  }

  /** FR-015. Asks the program to stop at its next checkpoint. */
  stop(): void {
    this.worker.postMessage({ kind: "stop", runId: this.runId });
  }

  /** Used when a program will not stop, or the page is going away. */
  terminate(): void {
    this.worker.terminate();
  }

  private async receive(message: WorkerMessage): Promise<void> {
    switch (message.kind) {
      case "console":
        this.handlers.onConsole?.(message.stream, message.text);
        return;
      case "done":
        this.handlers.onDone?.();
        return;
      case "failed":
        this.handlers.onFailed?.(explainError(message.error, this.sourceMap));
        return;
      case "rpc":
        await this.forward(message.callId, message.method, message.payload);
        return;
      case "ready":
        return;
      default:
        return;
    }
  }

  private async forward(
    callId: string,
    method: string,
    payload: Record<string, unknown>,
  ): Promise<void> {
    if (!isRpcMethod(method)) {
      this.worker.postMessage({
        kind: "rpc-result",
        callId,
        error: new RpcNotPermittedError(method).message,
      });
      return;
    }
    try {
      const result = await this.runtime.call(method, payload);
      this.worker.postMessage({ kind: "rpc-result", callId, result });
    } catch (error) {
      this.worker.postMessage({
        kind: "rpc-result",
        callId,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }
}

export {
  explainError,
  type ProgramError,
  type SourceMapEntry,
} from "./protocol.js";
export { ALLOWED_RPC_METHODS, isRpcMethod } from "./protocol.js";
export { WORKER_PYTHON } from "./worker-source.js";
