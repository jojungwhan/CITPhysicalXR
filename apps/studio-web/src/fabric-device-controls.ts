export type FabricDeviceControlKind =
  "sphero" | "wonder" | "drone" | "smart_plug";

interface FabricDeviceControlCounts {
  sphero: number;
  wonder: number;
  drone: number;
  smartPlug: number;
}

interface CapabilityBinding {
  requiredCapability: string;
}

const SPATIAL_ACTUATION_CAPABILITY_PREFIXES = [
  "mobility.ground.",
  "mobility.flight.",
  "robot.motor.",
] as const;

const DEVICE_CONTROL_ORDER: readonly FabricDeviceControlKind[] = [
  "sphero",
  "wonder",
  "drone",
  "smart_plug",
];

export const availableDeviceControlKinds = ({
  sphero,
  wonder,
  drone,
  smartPlug,
}: FabricDeviceControlCounts): FabricDeviceControlKind[] => {
  const counts: Record<FabricDeviceControlKind, number> = {
    sphero,
    wonder,
    drone,
    smart_plug: smartPlug,
  };
  return DEVICE_CONTROL_ORDER.filter((kind) => counts[kind] > 0);
};

export const resolvedDeviceControlKind = (
  requested: FabricDeviceControlKind | undefined,
  available: readonly FabricDeviceControlKind[],
): FabricDeviceControlKind | undefined =>
  requested !== undefined && available.includes(requested)
    ? requested
    : available[0];

export const requiresSpatialSafetyConfirmation = (
  bindings: readonly CapabilityBinding[],
): boolean =>
  bindings.some(({ requiredCapability }) =>
    SPATIAL_ACTUATION_CAPABILITY_PREFIXES.some((prefix) =>
      requiredCapability.startsWith(prefix),
    ),
  );
