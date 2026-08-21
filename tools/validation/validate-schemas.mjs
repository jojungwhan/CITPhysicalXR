import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import YAML from "yaml";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const schemaPath = path.join(
  root,
  "packages",
  "protocol-schema",
  "schemas",
  "cit-protocol.schema.json",
);
const schema = JSON.parse(await readFile(schemaPath, "utf8"));
const ajv = new Ajv2020({
  allErrors: true,
  strict: true,
  validateSchema: true,
});
addFormats(ajv);
if (!ajv.validateSchema(schema)) {
  throw new Error(`Invalid protocol schema: ${ajv.errorsText(ajv.errors)}`);
}
ajv.addSchema(schema);

const fixtures = {
  CitEnvelope: "valid-envelope.json",
  DeviceCommandIntent: "valid-command.json",
  DeviceEvent: "valid-event.json",
  DeviceDescriptor: "valid-device.json",
  PluginManifest: "valid-plugin-manifest.json",
  IntegrationNode: "valid-integration-node.json",
  FabricEventEnvelope: "valid-fabric-event.json",
  CoursePack: "valid-course-pack.json",
  AdapterRegistrationFrame: "valid-adapter-registration.json",
};

for (const [definition, filename] of Object.entries(fixtures)) {
  const value = JSON.parse(
    await readFile(
      path.join(root, "packages", "protocol-schema", "fixtures", filename),
      "utf8",
    ),
  );
  const validate = ajv.getSchema(`${schema.$id}#/$defs/${definition}`);
  if (validate === undefined || !validate(value)) {
    throw new Error(
      `${filename} does not satisfy ${definition}: ${ajv.errorsText(validate?.errors)}`,
    );
  }
}

const configSchemaPath = path.join(root, "config", "schema.json");
const packagedConfigSchemaPath = path.join(
  root,
  "apps",
  "runtime-py",
  "src",
  "cit_runtime",
  "config.schema.json",
);
const [configSchemaText, packagedConfigSchemaText] = await Promise.all([
  readFile(configSchemaPath, "utf8"),
  readFile(packagedConfigSchemaPath, "utf8"),
]);
const configSchema = JSON.parse(configSchemaText);
const packagedConfigSchema = JSON.parse(packagedConfigSchemaText);
if (JSON.stringify(configSchema) !== JSON.stringify(packagedConfigSchema)) {
  throw new Error(
    "Packaged runtime configuration schema has drifted from config/schema.json",
  );
}

const configAjv = new Ajv2020({
  allErrors: true,
  strict: true,
  validateSchema: true,
});
if (!configAjv.validateSchema(configSchema)) {
  throw new Error(
    `Invalid configuration schema: ${configAjv.errorsText(configAjv.errors)}`,
  );
}
const validateConfig = configAjv.compile(configSchema);
const configFiles = [
  path.join(root, "config", "default.yaml"),
  ...(await readdir(path.join(root, "config", "examples")))
    .filter((filename) => filename.endsWith(".yaml"))
    .map((filename) => path.join(root, "config", "examples", filename)),
];

for (const configFile of configFiles) {
  const value = YAML.parse(await readFile(configFile, "utf8"));
  if (!validateConfig(value)) {
    throw new Error(
      `${path.relative(root, configFile)} is invalid: ${configAjv.errorsText(validateConfig.errors)}`,
    );
  }
}

process.stdout.write(
  `Validated ${Object.keys(fixtures).length} protocol fixtures and ${configFiles.length} configuration files.\n`,
);
