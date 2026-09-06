import type { FabricCommandLifecycleEvent } from "@citxr/protocol";
import { describe, expect, it, vi } from "vitest";

import {
  awaitFabricCommandBatch,
  awaitFabricCommandTerminal,
} from "./fabric-command-chain.js";

describe("Fabric command chaining", () => {
  it("waits for the exact command to succeed before a dependent command", async () => {
    const dispatched = lifecycle("DISPATCHED");
    const succeeded = lifecycle("SUCCEEDED");
    const listLifecycle = vi
      .fn()
      .mockResolvedValue([{ streamSequence: 7, lifecycle: succeeded }]);

    const terminal = await awaitFabricCommandTerminal(
      { listLifecycle },
      { lifecycle: [dispatched] },
      { pollIntervalMs: 0 },
    );

    expect(terminal.stage).toBe("SUCCEEDED");
    expect(listLifecycle).toHaveBeenCalledWith(0, "command-a");
  });

  it("returns an initial rejection without polling", async () => {
    const rejected = lifecycle("REJECTED");
    const listLifecycle = vi.fn();

    const terminal = await awaitFabricCommandTerminal(
      { listLifecycle },
      { lifecycle: [rejected] },
    );

    expect(terminal).toBe(rejected);
    expect(listLifecycle).not.toHaveBeenCalled();
  });

  it("counts delayed terminal success for every command in a dispatched batch", async () => {
    const commandIds = ["command-a", "command-b", "command-c"];
    const listLifecycle = vi.fn(
      async (_afterSequence: number, commandId?: string) => [
        {
          streamSequence: 7,
          lifecycle: lifecycle("SUCCEEDED", commandId),
        },
      ],
    );

    const result = await awaitFabricCommandBatch(
      { listLifecycle },
      commandIds.map((commandId) =>
        Promise.resolve({
          lifecycle: [lifecycle("DISPATCHED", commandId)],
        }),
      ),
      { pollIntervalMs: 0 },
    );

    expect(result).toEqual({ succeeded: 3, failed: 0 });
    expect(listLifecycle).toHaveBeenCalledTimes(3);
  });

  it("counts terminal failures and rejected submissions as failed batch commands", async () => {
    const result = await awaitFabricCommandBatch({ listLifecycle: vi.fn() }, [
      Promise.resolve({ lifecycle: [lifecycle("SUCCEEDED", "command-a")] }),
      Promise.resolve({ lifecycle: [lifecycle("FAILED", "command-b")] }),
      Promise.reject(new Error("submission failed")),
    ]);

    expect(result).toEqual({ succeeded: 1, failed: 2 });
  });
});

const lifecycle = (stage: string, commandId = "command-a") =>
  ({
    commandId,
    stage,
  }) as FabricCommandLifecycleEvent;
