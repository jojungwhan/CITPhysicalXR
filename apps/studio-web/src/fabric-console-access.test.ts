import { describe, expect, it, vi } from "vitest";

import {
  consumeConsoleAccess,
  consumeConsoleTicket,
} from "./fabric-console-access.js";

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

  it("marks only the launcher-created Android handoff as persistent", () => {
    const replaceState = vi.fn();
    const ticket = "a".repeat(43);

    expect(
      consumeConsoleAccess(
        {
          hash: `#android-console-ticket=${ticket}`,
          pathname: "/fabric",
          search: "",
        },
        { replaceState },
      ),
    ).toEqual({ ticket, persistAndroidSession: true });
    expect(replaceState).toHaveBeenCalledWith(null, "", "/fabric");
  });

  it("does not let an arbitrary Android flag make a URL persistent", () => {
    const replaceState = vi.fn();

    expect(
      consumeConsoleAccess(
        {
          hash: "#android-session=1",
          pathname: "/fabric",
          search: "",
        },
        { replaceState },
      ),
    ).toBeUndefined();
    expect(replaceState).not.toHaveBeenCalled();
  });
});
