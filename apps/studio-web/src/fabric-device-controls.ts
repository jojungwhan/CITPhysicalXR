interface CapabilityBinding {
  requiredCapability: string;
}

const SPATIAL_ACTUATION_CAPABILITY_PREFIXES = [
  "mobility.ground.",
  "mobility.flight.",
  "robot.motor.",
] as const;

export const requiresSpatialSafetyConfirmation = (
  bindings: readonly CapabilityBinding[],
): boolean =>
  bindings.some(({ requiredCapability }) =>
    SPATIAL_ACTUATION_CAPABILITY_PREFIXES.some((prefix) =>
      requiredCapability.startsWith(prefix),
    ),
  );
