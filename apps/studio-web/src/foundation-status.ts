export interface FoundationStatus {
  milestone: 0;
  mode: "foundation-only";
  physicalControl: false;
  agentMeshRequired: false;
}

export const foundationStatus = (): FoundationStatus => ({
  milestone: 0,
  mode: "foundation-only",
  physicalControl: false,
  agentMeshRequired: false,
});
