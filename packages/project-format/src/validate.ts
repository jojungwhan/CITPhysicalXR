/**
 * Schema validation and explicit migration (FR-002, FR-003).
 *
 * Importing a project is the one place untrusted JSON enters the Studio, so it
 * is validated against the schema rather than cast. A file from a future
 * version is refused with its version named, not "repaired" by guessing.
 */

import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";
import addFormatsModule, { type FormatsPlugin } from "ajv-formats";

import schema from "../schemas/cit-project.schema.json" with { type: "json" };
import { type CitProject, PROJECT_SCHEMA_VERSION } from "./types.js";

export class ProjectValidationError extends Error {
  readonly detail: string;

  constructor(detail: string) {
    super(`Project file is not valid: ${detail}`);
    this.name = "ProjectValidationError";
    this.detail = detail;
  }
}

const ajv = new Ajv2020({ allErrors: true, strict: true });
const addFormats = addFormatsModule as unknown as FormatsPlugin;
addFormats(ajv);
const validator: ValidateFunction = ajv.compile(schema);

export const projectSchema = schema;

export function isCitProject(value: unknown): value is CitProject {
  return validator(value) === true;
}

export function assertCitProject(value: unknown): CitProject {
  if (!validator(value)) {
    throw new ProjectValidationError(ajv.errorsText(validator.errors));
  }
  return value as CitProject;
}

/**
 * A migration takes one schema version to the next. There is deliberately no
 * "latest" catch-all: adding version 2 means writing the 1 -> 2 step here.
 */
type Migration = (project: Record<string, unknown>) => Record<string, unknown>;

const MIGRATIONS: ReadonlyMap<number, Migration> = new Map();

export function migrateProject(value: unknown): CitProject {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ProjectValidationError("a project must be a JSON object");
  }
  let current = { ...(value as Record<string, unknown>) };
  const version = current["schemaVersion"];
  if (typeof version !== "number" || !Number.isInteger(version)) {
    throw new ProjectValidationError(
      "schemaVersion is missing or not an integer",
    );
  }
  if (version > PROJECT_SCHEMA_VERSION) {
    throw new ProjectValidationError(
      `schemaVersion ${version} is newer than this build understands ` +
        `(${PROJECT_SCHEMA_VERSION}). Update the Studio rather than editing the file.`,
    );
  }

  for (let step = version; step < PROJECT_SCHEMA_VERSION; step += 1) {
    const migration = MIGRATIONS.get(step);
    if (migration === undefined) {
      throw new ProjectValidationError(
        `no migration is registered from schemaVersion ${step} to ${step + 1}`,
      );
    }
    current = migration(current);
  }

  return assertCitProject(current);
}

/** FR-001 import. Parses, migrates, and validates in that order. */
export function importProject(text: string): CitProject {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new ProjectValidationError(
      error instanceof Error ? error.message : "the file is not JSON",
    );
  }
  return migrateProject(parsed);
}
