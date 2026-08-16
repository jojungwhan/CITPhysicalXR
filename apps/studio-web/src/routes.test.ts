import { describe, expect, it } from "vitest";

import { ROUTES, routeFromHash } from "./routes.js";
import { catalog } from "./i18n.js";

describe("navigation (UI 11.1)", () => {
  it("has exactly the eight views the PRD names, in its order", () => {
    expect([...ROUTES]).toEqual([
      "projects",
      "program",
      "devices",
      "xr",
      "simulation",
      "instructor",
      "logs",
      "settings",
    ]);
  });

  it("labels every view in both languages", () => {
    for (const locale of ["en", "ko"] as const) {
      for (const route of ROUTES) {
        expect(
          catalog(locale)[`nav.${route}`],
          `${locale}.${route}`,
        ).toBeTruthy();
      }
    }
  });

  it("reads a view out of the hash", () => {
    expect(routeFromHash("#/instructor")).toBe("instructor");
    expect(routeFromHash("#instructor")).toBe("instructor");
  });

  it("falls back to the program rather than a blank page", () => {
    expect(routeFromHash("")).toBe("program");
    expect(routeFromHash("#/nonsense")).toBe("program");
  });
});
