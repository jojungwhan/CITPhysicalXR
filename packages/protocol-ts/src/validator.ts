import {
  Ajv2020,
  type ErrorObject,
  type ValidateFunction,
} from "ajv/dist/2020.js";
import addFormatsModule, { type FormatsPlugin } from "ajv-formats";

import {
  protocolSchema,
  type ProtocolDefinitionName,
} from "./generated/schema.js";

export type ValidationResult =
  | { readonly valid: true }
  | { readonly valid: false; readonly errors: readonly string[] };

const ajv = new Ajv2020({ allErrors: true, strict: true });
const addFormats = addFormatsModule as unknown as FormatsPlugin;
addFormats(ajv);
ajv.addSchema(protocolSchema);

const validators = new Map<ProtocolDefinitionName, ValidateFunction>();

const formatError = (error: ErrorObject): string => {
  const location =
    error.instancePath.length === 0 ? "$" : `$${error.instancePath}`;
  return `${location}: ${error.message ?? error.keyword}`;
};

const validatorFor = (name: ProtocolDefinitionName): ValidateFunction => {
  const cached = validators.get(name);
  if (cached !== undefined) return cached;
  const schemaId = `${protocolSchema.$id}#/$defs/${name}`;
  const validator = ajv.getSchema(schemaId);
  if (validator === undefined) {
    throw new TypeError(`Unknown protocol definition: ${name}`);
  }
  validators.set(name, validator);
  return validator;
};

export const validateDefinition = (
  name: ProtocolDefinitionName,
  value: unknown,
): ValidationResult => {
  const validator = validatorFor(name);
  if (validator(value)) return { valid: true };
  return {
    valid: false,
    errors: (validator.errors ?? []).map(formatError),
  };
};
