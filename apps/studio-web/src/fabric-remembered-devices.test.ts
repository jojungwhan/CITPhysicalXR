import { describe, expect, it } from "vitest";

import { resolveAutoReconnectRemembered } from "./fabric-remembered-devices.js";

describe("remembered-device reconnect preference", () => {
  it("is opt-in and accepts only the exact persisted true value", () => {
    expect(resolveAutoReconnectRemembered(undefined)).toBe(false);
    expect(resolveAutoReconnectRemembered(null)).toBe(false);
    expect(resolveAutoReconnectRemembered("false")).toBe(false);
    expect(resolveAutoReconnectRemembered("TRUE")).toBe(false);
    expect(resolveAutoReconnectRemembered("true")).toBe(true);
  });
});
