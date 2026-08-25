import type { FabricCommandLifecycleEvent } from "@citxr/protocol";
import { describe, expect, it, vi } from "vitest";

import { awaitFabricCommandTerminal } from "./fabric-command-chain.js";

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
});

const lifecycle = (stage: string) =>
  ({
    commandId: "command-a",
    stage,
  }) as FabricCommandLifecycleEvent;
