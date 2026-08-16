export interface FoundationStatus {
  milestone: 1;
  mode: "runtime-simulation";
  /** No hardware adapter exists yet; M2/M4/M5 add them. */
  physicalControl: false;
  agentMeshRequired: false;
  /** M1 does add a local runtime API, unlike M0. */
  localRuntimeApi: true;
}

export const foundationStatus = (): FoundationStatus => ({
  milestone: 1,
  mode: "runtime-simulation",
  physicalControl: false,
  agentMeshRequired: false,
  localRuntimeApi: true,
});
