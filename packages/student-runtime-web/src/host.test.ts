import { describe, expect, it, vi } from "vitest";

import {
  ALLOWED_RPC_METHODS,
  explainError,
  isRpcMethod,
  type SourceMapEntry,
  type WorkerMessage,
} from "./protocol.js";
import { StudentRuntimeHost, type StudentWorkerLike } from "./host.js";

class FakeWorker implements StudentWorkerLike {
  readonly sent: unknown[] = [];
  private listener: ((event: { data: unknown }) => void) | undefined;
  terminated = false;

  postMessage(message: unknown): void {
    this.sent.push(message);
  }

  addEventListener(
    _: "message",
    listener: (event: { data: unknown }) => void,
  ): void {
    this.listener = listener;
  }

  terminate(): void {
    this.terminated = true;
  }

  emit(message: WorkerMessage): void {
    this.listener?.({ data: message });
  }
}

const SOURCE_MAP: SourceMapEntry[] = [
  { line: 5, blockId: "b1", blockType: "cit_on_start" },
  {
    line: 7,
    blockId: "b2",
    blockType: "cit_drive_velocity",
    deviceAlias: "s1",
  },
];

function setup(call = vi.fn(async () => ({ accepted: true }))) {
  const worker = new FakeWorker();
  const host = new StudentRuntimeHost(worker, { call });
  return { worker, host, call };
}

describe("sandbox boundary (FR-013)", () => {
  it("permits exactly the five documented calls", () => {
    expect([...ALLOWED_RPC_METHODS].sort()).toEqual([
      "command",
      "device_info",
      "log",
      "read_sensor",
      "sleep",
    ]);
    for (const forbidden of ["exec", "eval", "open", "fetch", "spawn"]) {
      expect(isRpcMethod(forbidden)).toBe(false);
    }
  });

  it("refuses an unlisted method instead of forwarding it", async () => {
    const { worker, host, call } = setup();
    host.run({ runId: "r1", source: "" });
    worker.sent.length = 0;

    worker.emit({
      kind: "rpc",
      callId: "c1",
      method: "read_file" as never,
      payload: { path: "/etc/passwd" },
    });
    await vi.waitFor(() => expect(worker.sent).toHaveLength(1));

    expect(call).not.toHaveBeenCalled();
    expect(worker.sent[0]).toMatchObject({
      kind: "rpc-result",
      callId: "c1",
      error: expect.stringContaining("not one of the five permitted calls"),
    });
  });

  it("forwards a permitted call and returns the runtime's answer", async () => {
    const call = vi.fn(async () => ({ accepted: true, status: "completed" }));
    const { worker, host } = setup(call);
    host.run({ runId: "r1", source: "" });
    worker.sent.length = 0;

    worker.emit({
      kind: "rpc",
      callId: "c1",
      method: "command",
      payload: { device_id: "fake-s1-main" },
    });
    await vi.waitFor(() => expect(worker.sent).toHaveLength(1));

    expect(call).toHaveBeenCalledWith("command", { device_id: "fake-s1-main" });
    expect(worker.sent[0]).toMatchObject({
      kind: "rpc-result",
      result: { accepted: true, status: "completed" },
    });
  });

  it("reports a runtime failure to the worker rather than hanging it", async () => {
    const call = vi.fn(async () => {
      throw new Error("runtime is down");
    });
    const { worker, host } = setup(call);
    host.run({ runId: "r1", source: "" });
    worker.sent.length = 0;

    worker.emit({ kind: "rpc", callId: "c1", method: "log", payload: {} });
    await vi.waitFor(() => expect(worker.sent).toHaveLength(1));

    expect(worker.sent[0]).toMatchObject({ error: "runtime is down" });
  });
});

describe("run control (FR-015)", () => {
  it("sends the student source to the worker", () => {
    const { worker, host } = setup();
    host.run({ runId: "r1", source: "await log('hi')" });
    expect(worker.sent[0]).toEqual({
      kind: "run",
      runId: "r1",
      source: "await log('hi')",
    });
  });

  it("asks the program to stop before resorting to termination", () => {
    const { worker, host } = setup();
    host.run({ runId: "r1", source: "" });
    host.stop();
    expect(worker.sent[1]).toEqual({ kind: "stop", runId: "r1" });
    expect(worker.terminated).toBe(false);

    host.terminate();
    expect(worker.terminated).toBe(true);
  });

  it("passes console output through", () => {
    const onConsole = vi.fn();
    const { worker, host } = setup();
    host.run({ runId: "r1", source: "", handlers: { onConsole } });

    worker.emit({
      kind: "console",
      runId: "r1",
      stream: "stdout",
      text: "hello",
    });
    expect(onConsole).toHaveBeenCalledWith("stdout", "hello");
  });

  it("reports completion", () => {
    const onDone = vi.fn();
    const { worker, host } = setup();
    host.run({ runId: "r1", source: "", handlers: { onDone } });
    worker.emit({ kind: "done", runId: "r1" });
    expect(onDone).toHaveBeenCalled();
  });
});

describe("error mapping (FR-012)", () => {
  it("names the block a failing line came from", () => {
    const explained = explainError(
      { message: "boom", errorType: "TypeError", line: 8 },
      SOURCE_MAP,
    );
    expect(explained.blockId).toBe("b2");
    expect(explained.blockType).toBe("cit_drive_velocity");
    expect(explained.deviceAlias).toBe("s1");
    expect(explained.suggestion).toBeTruthy();
  });

  it("blames no block when the line precedes every mapped line", () => {
    const explained = explainError(
      { message: "boom", errorType: "NameError", line: 1 },
      SOURCE_MAP,
    );
    expect(explained.blockId).toBeUndefined();
    expect(explained.suggestion).toMatch(/spelling|bind/i);
  });

  it("blames no block when there is no line at all", () => {
    const explained = explainError(
      { message: "boom", errorType: "RuntimeError" },
      SOURCE_MAP,
    );
    expect(explained.blockId).toBeUndefined();
  });

  it("explains a refusal in terms a student can act on", () => {
    const explained = explainError(
      { message: "not armed", errorType: "CommandRejected", line: 8 },
      SOURCE_MAP,
    );
    expect(explained.suggestion).toMatch(/refused this action/);
  });

  it("says a stopped program is not a mistake", () => {
    const explained = explainError(
      { message: "stopped", errorType: "CancelledError" },
      SOURCE_MAP,
    );
    expect(explained.suggestion).toMatch(/Nothing is wrong/);
  });

  it("suggests await when a TypeError mentions it", () => {
    const explained = explainError(
      {
        message: "object NoneType can't be used in 'await' expression",
        errorType: "TypeError",
      },
      SOURCE_MAP,
    );
    expect(explained.suggestion).toMatch(/needs `await`/);
  });

  it("maps a failure through the host handler", () => {
    const onFailed = vi.fn();
    const { worker, host } = setup();
    host.run({
      runId: "r1",
      source: "",
      sourceMap: SOURCE_MAP,
      handlers: { onFailed },
    });

    worker.emit({
      kind: "failed",
      runId: "r1",
      error: { message: "boom", errorType: "TypeError", line: 8 },
    });

    expect(onFailed).toHaveBeenCalledWith(
      expect.objectContaining({ blockId: "b2", deviceAlias: "s1" }),
    );
  });
});
