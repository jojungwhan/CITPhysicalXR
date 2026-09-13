import { describe, expect, it, vi } from "vitest";

import { registerFabricPwa } from "./pwa.js";

describe("Fabric Android PWA registration", () => {
  it("registers the same-origin worker only for the Fabric control route", async () => {
    const register = vi.fn().mockResolvedValue({ scope: "https://cit.test/" });

    await registerFabricPwa(
      { pathname: "/fabric" },
      { register },
      "https://cit.test",
    );

    expect(register).toHaveBeenCalledWith("https://cit.test/fabric-sw.js", {
      scope: "/",
    });
  });

  it("does not install a device-control worker on unrelated Studio routes", async () => {
    const register = vi.fn();

    await registerFabricPwa(
      { pathname: "/projects" },
      { register },
      "https://cit.test",
    );

    expect(register).not.toHaveBeenCalled();
  });
});
