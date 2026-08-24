import { describe, expect, it } from "vitest";

import {
  availableDeviceControlKinds,
  requiresSpatialSafetyConfirmation,
  resolvedDeviceControlKind,
} from "./fabric-device-controls.js";

describe("Fabric device-control modal policy", () => {
  it("lists every available control category exactly once in a stable order", () => {
    expect(
      availableDeviceControlKinds({
        sphero: 2,
        wonder: 1,
        drone: 3,
        smartPlug: 2,
      }),
    ).toEqual(["sphero", "wonder", "drone", "smart_plug"]);

    expect(
      availableDeviceControlKinds({
        sphero: 0,
        wonder: 0,
        drone: 0,
        smartPlug: 0,
      }),
    ).toEqual([]);
  });

  it("keeps an available requested section and otherwise selects the first", () => {
    const available = ["sphero", "smart_plug"] as const;

    expect(resolvedDeviceControlKind("smart_plug", available)).toBe(
      "smart_plug",
    );
    expect(resolvedDeviceControlKind("drone", available)).toBe("sphero");
    expect(resolvedDeviceControlKind(undefined, [])).toBeUndefined();
  });

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
