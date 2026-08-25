import { describe, expect, it } from "vitest";

import {
  clearAircraftGroundedConfirmation,
  clearFlightSafetyConfirmation,
  readAircraftGroundedConfirmation,
  readFlightSafetyConfirmation,
  saveAircraftGroundedConfirmation,
  saveFlightSafetyConfirmation,
} from "./fabric-session-confirmations.js";

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  };
}

describe("browser-session safety confirmations", () => {
  it("restores both confirmations independently", () => {
    const storage = memoryStorage();

    saveAircraftGroundedConfirmation(true, storage);
    expect(readAircraftGroundedConfirmation(storage)).toBe(true);
    expect(readFlightSafetyConfirmation(storage)).toBe(false);

    saveFlightSafetyConfirmation(true, storage);
    expect(readAircraftGroundedConfirmation(storage)).toBe(true);
    expect(readFlightSafetyConfirmation(storage)).toBe(true);
  });

  it("removes an individual confirmation when unchecked", () => {
    const storage = memoryStorage();
    saveAircraftGroundedConfirmation(true, storage);
    saveFlightSafetyConfirmation(true, storage);

    saveFlightSafetyConfirmation(false, storage);

    expect(readAircraftGroundedConfirmation(storage)).toBe(true);
    expect(readFlightSafetyConfirmation(storage)).toBe(false);
  });

  it("clears confirmations on their respective safety reset", () => {
    const storage = memoryStorage();
    saveAircraftGroundedConfirmation(true, storage);
    saveFlightSafetyConfirmation(true, storage);

    clearAircraftGroundedConfirmation(storage);
    clearFlightSafetyConfirmation(storage);

    expect(readAircraftGroundedConfirmation(storage)).toBe(false);
    expect(readFlightSafetyConfirmation(storage)).toBe(false);
  });

  it("fails closed when browser storage is unavailable", () => {
    const unavailable = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    };

    expect(readAircraftGroundedConfirmation(unavailable)).toBe(false);
    expect(readFlightSafetyConfirmation(unavailable)).toBe(false);
    expect(() =>
      saveAircraftGroundedConfirmation(true, unavailable),
    ).not.toThrow();
    expect(() => saveFlightSafetyConfirmation(true, unavailable)).not.toThrow();
    expect(() => clearAircraftGroundedConfirmation(unavailable)).not.toThrow();
    expect(() => clearFlightSafetyConfirmation(unavailable)).not.toThrow();
  });
});
