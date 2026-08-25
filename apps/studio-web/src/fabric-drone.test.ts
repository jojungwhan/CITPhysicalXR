import { describe, expect, it } from "vitest";

import {
  FLIGHT_EMERGENCY_STOP_CAPABILITY,
  FLIGHT_LAND_CAPABILITY,
  FLIGHT_MOVE_CAPABILITY,
  FLIGHT_ROTATE_CAPABILITY,
  FLIGHT_TAKEOFF_CAPABILITY,
  isSafeStateTelloNode,
  isSafetyDroneRole,
  preferredTelloControlSession,
  supportsManualTelloFlight,
} from "./fabric-drone.js";

const node = (
  consumed: string[],
  connectionState = "connected",
  healthState = "healthy",
) =>
  ({
    pluginId: "cit.tello",
    connectionState,
    healthState,
    consumedCapabilities: consumed.map((name) => ({ name })),
  }) as Parameters<typeof isSafeStateTelloNode>[0];

describe("safe Tello UI boundary", () => {
  it("recognizes only the fixed monitoring role range", () => {
    expect(isSafetyDroneRole("safety_drone_1")).toBe(true);
    expect(isSafetyDroneRole("safety_drone_8")).toBe(true);
    expect(isSafetyDroneRole("safety_drone_9")).toBe(false);
    expect(isSafetyDroneRole("demonstration_drone")).toBe(false);
  });

  it("keeps safe-state support and recognizes the bounded manual contract", () => {
    const safe = [FLIGHT_LAND_CAPABILITY, FLIGHT_EMERGENCY_STOP_CAPABILITY];
    expect(isSafeStateTelloNode(node(safe))).toBe(true);
    expect(supportsManualTelloFlight(node(safe))).toBe(false);
    expect(
      supportsManualTelloFlight(
        node([
          ...safe,
          FLIGHT_TAKEOFF_CAPABILITY,
          FLIGHT_MOVE_CAPABILITY,
          FLIGHT_ROTATE_CAPABILITY,
        ]),
      ),
    ).toBe(true);
  });

  it("does not enable manual flight for a stale or unhealthy Tello", () => {
    const manual = [
      FLIGHT_LAND_CAPABILITY,
      FLIGHT_EMERGENCY_STOP_CAPABILITY,
      FLIGHT_TAKEOFF_CAPABILITY,
      FLIGHT_MOVE_CAPABILITY,
      FLIGHT_ROTATE_CAPABILITY,
    ];

    expect(supportsManualTelloFlight(node(manual, "degraded"))).toBe(false);
    expect(
      supportsManualTelloFlight(node(manual, "connected", "unhealthy")),
    ).toBe(false);
  });

  it("selects the live session that already owns the connected Tello", () => {
    const sessions = [
      {
        sessionId: "old",
        state: "ready",
        armed: false,
        updatedAt: "2026-08-25T00:00:00Z",
        roleBindings: [{ role: "safety_drone_1", nodeId: "tello-a" }],
      },
      {
        sessionId: "active",
        state: "active",
        armed: true,
        updatedAt: "2026-08-25T00:01:00Z",
        roleBindings: [{ role: "safety_drone_1", nodeId: "tello-a" }],
      },
    ];

    expect(preferredTelloControlSession(sessions, ["tello-a"])?.sessionId).toBe(
      "active",
    );
  });
});
