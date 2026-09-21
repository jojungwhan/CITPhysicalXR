import { describe, expect, it } from "vitest";

import { browserRandomUuid } from "./browser-random-uuid.js";

describe("browserRandomUuid", () => {
  it("creates an RFC 4122 v4 UUID in a LAN HTTP browser without randomUUID", () => {
    const entropy = Uint8Array.from([
      0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b,
      0x0c, 0x0d, 0x0e, 0x0f,
    ]);
    const lanHttpCrypto = {
      getRandomValues(target: Uint8Array): Uint8Array {
        target.set(entropy);
        return target;
      },
    };

    expect(browserRandomUuid(lanHttpCrypto)).toBe(
      "00010203-0405-4607-8809-0a0b0c0d0e0f",
    );
  });
});
