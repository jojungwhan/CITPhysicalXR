import { describe, expect, it } from "vitest";

import { requiresSpatialSafetyConfirmation } from "./fabric-device-controls.js";

describe("Fabric device-control safety policy", () => {
  it("requires a position check only for spatial actuation capabilities", () => {
    expect(
      requiresSpatialSafetyConfirmation([
        { requiredCapability: "power.switch.set" },
      ]),
    ).toBe(false);
    expect(
      requiresSpatialSafetyConfirmation([
        { requiredCapability: "display.text.render" },
      ]),
    ).toBe(false);
    expect(
      requiresSpatialSafetyConfirmation([
        { requiredCapability: "mobility.ground.set_velocity" },
      ]),
    ).toBe(true);
    expect(
      requiresSpatialSafetyConfirmation([
        { requiredCapability: "mobility.flight.land" },
      ]),
    ).toBe(true);
    expect(
      requiresSpatialSafetyConfirmation([
        { requiredCapability: "robot.motor.run" },
      ]),
    ).toBe(true);
  });
});
