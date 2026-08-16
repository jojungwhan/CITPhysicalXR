/**
 * The versioned project file (FR-002).
 *
 * These types are hand-written to mirror `schemas/cit-project.schema.json`.
 * `validate.ts` checks a value against the schema at runtime, and a test asserts
 * the two stay in step, so a field cannot be added here without adding it there.
 */

export const PROJECT_SCHEMA_VERSION = 1 as const;

export type AuthoringMode = "blocks" | "python";
export type ExecutionMode = "simulation" | "physical";
export type AssetKind = "image" | "audio" | "model" | "data";

export interface BlockNode {
  id: string;
  type: string;
  fields?: Record<string, unknown>;
  children?: BlockNode[];
  disabled?: boolean;
  comment?: string;
}

export interface BlocksVariable {
  id: string;
  name: string;
}

export interface BlocksState {
  blocks: BlockNode[];
  variables?: BlocksVariable[];
}

/** FR-019: a binding names an exact deviceId. There is no family binding. */
export interface DeviceBinding {
  alias: string;
  deviceId: string;
  required?: boolean;
}

export interface Asset {
  assetId: string;
  kind: AssetKind;
  name: string;
  bytes?: number;
}

export interface CitProject {
  schemaVersion: typeof PROJECT_SCHEMA_VERSION;
  projectId: string;
  name: string;
  authoringMode: AuthoringMode;
  blocksState: BlocksState;
  generatedPython: string;
  pythonSource: string;
  lastBlocksSnapshot?: BlocksState | null;
  targetProfile: string;
  deviceBindings: DeviceBinding[];
  questScene: Record<string, unknown>;
  safetyPreset: string;
  executionMode?: ExecutionMode;
  assets: Asset[];
  createdAt: string;
  updatedAt: string;
}

export const EMPTY_BLOCKS_STATE: BlocksState = { blocks: [] };
