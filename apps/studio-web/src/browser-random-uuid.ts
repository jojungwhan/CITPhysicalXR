export type BrowserUuidCrypto = {
  randomUUID?(): string;
  getRandomValues(target: Uint8Array): Uint8Array;
};

/**
 * Create a cryptographically random UUID in both secure and LAN HTTP contexts.
 *
 * Browsers expose crypto.getRandomValues() on ordinary HTTP pages but reserve
 * crypto.randomUUID() for secure contexts. Control Tower intentionally supports
 * an authenticated local-LAN URL for its paired phone, so use the native UUID
 * method when available and otherwise format RFC 4122 version-4 bytes locally.
 */
export function browserRandomUuid(
  cryptoSource: BrowserUuidCrypto = globalThis.crypto,
): string {
  if (typeof cryptoSource.randomUUID === "function") {
    return cryptoSource.randomUUID();
  }

  const bytes = cryptoSource.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6]! & 0x0f) | 0x40;
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}
