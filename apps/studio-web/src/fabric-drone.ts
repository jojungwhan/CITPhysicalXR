import type { IntegrationNode } from "@citxr/protocol";

export const FLIGHT_LAND_CAPABILITY = "mobility.flight.land";
export const FLIGHT_EMERGENCY_STOP_CAPABILITY =
  "mobility.flight.emergency_stop";

export const isSafetyDroneRole = (role: string) =>
  /^safety_drone_[1-8]$/.test(role);

export const isSafeStateTelloNode = (node: IntegrationNode) => {
  const consumed = new Set(
    node.consumedCapabilities.map((capability) => capability.name),
  );
  return (
    node.pluginId === "cit.tello" &&
    consumed.has(FLIGHT_LAND_CAPABILITY) &&
    consumed.has(FLIGHT_EMERGENCY_STOP_CAPABILITY) &&
    ![...consumed].some(
      (capability) =>
        capability.includes("takeoff") || capability.includes("move"),
    )
  );
};
