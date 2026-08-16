export type BridgeOperation =
  | "status"
  | "diagnostics"
  | "pause_program"
  | "stop_device"
  | "emergency_stop"
  | "request_local_arming"
  | "physical_movement";

export type BridgeAuthorization =
  { allowed: true } | { allowed: false; reason: string };

export const authorizeBridgeOperation = (
  operation: BridgeOperation,
): BridgeAuthorization => {
  if (operation === "physical_movement") {
    return {
      allowed: false,
      reason: "Agent Mesh cannot initiate physical movement",
    };
  }
  return { allowed: true };
};
