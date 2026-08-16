import { spawnSync } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { compile } from "json-schema-to-typescript";
import { format } from "prettier";

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
const committed = {
  pythonModels: path.join(
    root,
    "packages",
    "protocol-py",
    "src",
    "cit_protocol",
    "generated.py",
  ),
  pythonSchema: path.join(
    root,
    "packages",
    "protocol-py",
    "src",
    "cit_protocol",
    "cit-protocol.schema.json",
  ),
  tsModels: path.join(
    root,
    "packages",
    "protocol-ts",
    "src",
    "generated",
    "models.ts",
  ),
  tsSchema: path.join(
    root,
    "packages",
    "protocol-ts",
    "src",
    "generated",
    "schema.ts",
  ),
};

const generate = async (destinations) => {
  const source = await readFile(schemaPath, "utf8");
  const schema = JSON.parse(source);
  const bannerComment = [
    "/* eslint-disable */",
    "/**",
    " * Generated from packages/protocol-schema/schemas/cit-protocol.schema.json.",
    " * Do not edit by hand.",
    " */",
    "",
  ].join("\n");
  const compiledTsModels = await compile(schema, "CitProtocolMessage", {
    bannerComment,
    additionalProperties: false,
    declareExternallyReferenced: true,
    enableConstEnums: false,
    format: true,
    strictIndexSignatures: true,
    style: {
      bracketSpacing: true,
      printWidth: 100,
      semi: true,
      singleQuote: false,
    },
    unreachableDefinitions: true,
  });
  const tsModels = await format(compiledTsModels, { parser: "typescript" });
  const tsSchema = await format(
    `${bannerComment}export const protocolSchema = ${JSON.stringify(
      schema,
      null,
      2,
    )} as const;\n\nexport type ProtocolDefinitionName = keyof typeof protocolSchema.$defs;\n`,
    { parser: "typescript" },
  );
  const pythonSchema = await format(`${JSON.stringify(schema, null, 2)}\n`, {
    parser: "json",
  });

  await Promise.all(
    Object.values(destinations).map((destination) =>
      mkdir(path.dirname(destination), { recursive: true }),
    ),
  );
  await writeFile(destinations.tsModels, tsModels, "utf8");
  await writeFile(destinations.tsSchema, tsSchema, "utf8");
  await writeFile(destinations.pythonSchema, pythonSchema, "utf8");

  const executable = process.platform === "win32" ? "uv.exe" : "uv";
  const generated = spawnSync(
    executable,
    [
      "run",
      "datamodel-codegen",
      "--input",
      schemaPath,
      "--input-file-type",
      "jsonschema",
      "--output",
      destinations.pythonModels,
      "--output-model-type",
      "pydantic_v2.BaseModel",
      "--target-python-version",
      "3.11",
      "--class-name",
      "CitProtocolMessage",
      "--use-title-as-name",
      "--collapse-root-models",
      "--use-standard-collections",
      "--use-union-operator",
      "--use-annotated",
      "--strict-nullable",
      "--use-default",
      "--disable-timestamp",
    ],
    { cwd: root, encoding: "utf8" },
  );
  if (generated.status !== 0) {
    throw new Error(
      `Python model generation failed:\n${generated.stdout}${generated.stderr}`,
    );
  }
  const pythonModels = await readFile(destinations.pythonModels, "utf8");
  await writeFile(
    destinations.pythonModels,
    pythonModels.replaceAll("\r\n", "\n"),
    "utf8",
  );
};

const assertGeneratedMatches = async (actual, expected) => {
  const [actualText, expectedText] = await Promise.all([
    readFile(actual, "utf8"),
    readFile(expected, "utf8").catch(() => undefined),
  ]);
  if (expectedText === undefined || actualText !== expectedText) {
    throw new Error(
      `Generated file is stale or missing: ${path.relative(root, expected)}. Run pnpm generate.`,
    );
  }
};

if (process.argv.includes("--check")) {
  const temporaryRoot = await mkdtemp(path.join(tmpdir(), "citxr-protocol-"));
  const temporary = Object.fromEntries(
    Object.entries(committed).map(([key, value]) => [
      key,
      path.join(temporaryRoot, key, path.basename(value)),
    ]),
  );
  try {
    await generate(temporary);
    await Promise.all(
      Object.keys(committed).map((key) =>
        assertGeneratedMatches(temporary[key], committed[key]),
      ),
    );
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
} else {
  await generate(committed);
}
