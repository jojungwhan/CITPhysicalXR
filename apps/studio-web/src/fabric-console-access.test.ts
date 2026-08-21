import { describe, expect, it, vi } from "vitest";

import { consumeConsoleTicket } from "./fabric-console-access.js";

describe("launcher-assisted console access", () => {
  it("takes the one-use ticket and immediately removes it from the address bar", () => {
    const replaceState = vi.fn();

    const ticket = consumeConsoleTicket(
      {
        hash: `#console-ticket=${"t".repeat(43)}`,
        pathname: "/fabric",
        search: "?language=en",
      },
      { replaceState },
    );

    expect(ticket).toBe("t".repeat(43));
    expect(replaceState).toHaveBeenCalledWith(null, "", "/fabric?language=en");
  });

  it("does not change ordinary console URLs", () => {
    const replaceState = vi.fn();

    expect(
      consumeConsoleTicket(
        { hash: "", pathname: "/fabric", search: "" },
        { replaceState },
      ),
    ).toBeUndefined();
    expect(replaceState).not.toHaveBeenCalled();
  });
});
