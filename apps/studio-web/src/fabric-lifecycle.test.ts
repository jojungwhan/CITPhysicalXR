import { describe, expect, it } from "vitest";

import { countActiveFabricCommands } from "./fabric-lifecycle.js";

describe("Fabric command lifecycle projection", () => {
  it("does not count historical stages after a command succeeds", () => {
    expect(
      countActiveFabricCommands([
        lifecycle(1, "command-a", "PROPOSED"),
        lifecycle(2, "command-a", "RUNNING"),
        lifecycle(3, "command-a", "SUCCEEDED"),
      ]),
    ).toBe(0);
  });

  it("counts each command only when its latest stage is nonterminal", () => {
    expect(
      countActiveFabricCommands([
        lifecycle(4, "command-a", "RUNNING"),
        lifecycle(2, "command-b", "REJECTED"),
        lifecycle(1, "command-a", "PROPOSED"),
        lifecycle(3, "command-c", "ACCEPTED"),
      ]),
    ).toBe(2);
  });
});

const lifecycle = (
  streamSequence: number,
  commandId: string,
  stage: string,
) => ({
  streamSequence,
  lifecycle: { commandId, stage },
});
