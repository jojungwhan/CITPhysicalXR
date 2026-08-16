/**
 * The typed messages between the Studio page and the student worker (FR-013).
 *
 * The worker is the sandbox boundary, so this protocol is deliberately narrow:
 * the page can start a program, stop it, and answer an RPC. The worker can ask
 * for one of the five allowlisted runtime calls, report console output, and
 * report that it finished or failed. There is no "evaluate this" message, and
 * no way for the worker to name a host function to call.
 */

/** The five calls a student program may cause. Mirrors `citxr.bridge`. */
export const ALLOWED_RPC_METHODS = [
  "command",
  "device_info",
  "log",
  "read_sensor",
  "sleep",
] as const;

export type RpcMethod = (typeof ALLOWED_RPC_METHODS)[number];

export function isRpcMethod(value: unknown): value is RpcMethod {
  return (
    typeof value === "string" &&
    (ALLOWED_RPC_METHODS as readonly string[]).includes(value)
  );
}

export interface SourceMapEntry {
  line: number;
  blockId: string;
  blockType: string;
  deviceAlias?: string;
}

/* ------------------------------------------------------------------ page -> worker */

export interface RunMessage {
  kind: "run";
  runId: string;
  /** The student's Python. Generated or handwritten; the worker cannot tell. */
  source: string;
  /** How long the interval handlers are allowed to run, in iterations. */
  intervalIterations?: number;
}

export interface StopMessage {
  kind: "stop";
  runId: string;
}

export interface RpcResultMessage {
  kind: "rpc-result";
  callId: string;
  result?: unknown;
  error?: string;
}

export type HostMessage = RunMessage | StopMessage | RpcResultMessage;

/* ------------------------------------------------------------------ worker -> page */

export interface ReadyMessage {
  kind: "ready";
}

export interface RpcRequestMessage {
  kind: "rpc";
  callId: string;
  method: RpcMethod;
  payload: Record<string, unknown>;
}

export interface ConsoleMessage {
  kind: "console";
  runId: string;
  stream: "stdout" | "stderr";
  text: string;
}

export interface DoneMessage {
  kind: "done";
  runId: string;
}

/** FR-012. A failure names the Python line and the block that produced it. */
export interface ProgramError {
  message: string;
  errorType: string;
  line?: number;
  blockId?: string;
  blockType?: string;
  deviceAlias?: string;
  suggestion?: string;
  traceback?: string;
}

export interface FailedMessage {
  kind: "failed";
  runId: string;
  error: ProgramError;
}

export type WorkerMessage =
  | ReadyMessage
  | RpcRequestMessage
  | ConsoleMessage
  | DoneMessage
  | FailedMessage;

/**
 * FR-012. Turn a raw Python failure into something a student can act on.
 *
 * The mapping is deliberately conservative: when the traceback does not name a
 * line inside the student's own module, no block is blamed. A wrong arrow
 * pointing at an innocent block is worse than no arrow.
 */
export function explainError(
  error: {
    message: string;
    errorType: string;
    line?: number;
    traceback?: string;
  },
  sourceMap: readonly SourceMapEntry[],
): ProgramError {
  const explained: ProgramError = {
    message: error.message,
    errorType: error.errorType,
  };
  if (error.line !== undefined) explained.line = error.line;
  if (error.traceback !== undefined) explained.traceback = error.traceback;

  if (error.line !== undefined) {
    let best: SourceMapEntry | undefined;
    for (const entry of sourceMap) {
      if (
        entry.line <= error.line &&
        (best === undefined || entry.line > best.line)
      ) {
        best = entry;
      }
    }
    if (best !== undefined) {
      explained.blockId = best.blockId;
      explained.blockType = best.blockType;
      if (best.deviceAlias !== undefined) {
        explained.deviceAlias = best.deviceAlias;
      }
    }
  }

  explained.suggestion = suggestionFor(error.errorType, error.message);
  return explained;
}

function suggestionFor(errorType: string, message: string): string {
  switch (errorType) {
    case "CommandRejected":
      return "The runtime refused this action. Read the reason it gave, then fix the block or ask an instructor.";
    case "CancelledError":
      return "The program was stopped. Nothing is wrong with your code.";
    case "TransportError":
      return "The Studio lost its connection to the runtime. Check that the runtime is still running.";
    case "NameError":
      return "Something is used before it is created. Check the spelling, or bind the device to this project.";
    case "TypeError":
      return message.includes("await")
        ? "A device action needs `await` in front of it."
        : "A value has the wrong type here. Check the numbers and text going into this step.";
    case "ZeroDivisionError":
      return "Something divides by zero. Check the maths in this step.";
    case "ValueError":
      return "A value is outside the range this action accepts.";
    default:
      return "Read the message above, then check the highlighted block.";
  }
}
