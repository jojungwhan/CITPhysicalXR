import { describe, expect, it } from "vitest";

import {
  FLIGHT_EMERGENCY_STOP_CAPABILITY,
  FLIGHT_LAND_CAPABILITY,
  isSafeStateTelloNode,
  isSafetyDroneRole,
} from "./fabric-drone.js";

const node = (consumed: string[]) =>
  ({
    pluginId: "cit.tello",
    consumedCapabilities: consumed.map((name) => ({ name })),
  }) as Parameters<typeof isSafeStateTelloNode>[0];

describe("safe Tello UI boundary", () => {
  it("recognizes only the fixed monitoring role range", () => {
    expect(isSafetyDroneRole("safety_drone_1")).toBe(true);
    expect(isSafetyDroneRole("safety_drone_8")).toBe(true);
    expect(isSafetyDroneRole("safety_drone_9")).toBe(false);
    expect(isSafetyDroneRole("demonstration_drone")).toBe(false);
  });

  it("refuses a node that advertises takeoff or movement", () => {
    const safe = [FLIGHT_LAND_CAPABILITY, FLIGHT_EMERGENCY_STOP_CAPABILITY];
    expect(isSafeStateTelloNode(node(safe))).toBe(true);
    expect(
      isSafeStateTelloNode(node([...safe, "mobility.flight.takeoff"])),
    ).toBe(false);
  });
});
