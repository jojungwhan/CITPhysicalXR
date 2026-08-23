import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { format } from "prettier";
import YAML from "yaml";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const runtimePackage = path.join(
  root,
  "apps",
  "runtime-py",
  "src",
  "cit_runtime",
);
const coursePackRoot = path.join(root, "course-packs");
const coursePackIds = (await readdir(coursePackRoot, { withFileTypes: true }))
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
  .sort();
const coursePackIndexPath = path.join(
  runtimePackage,
  "course-packs",
  "index.generated.json",
);
const coursePackIndex = await format(
  `${JSON.stringify({ schemaVersion: "1.0", coursePackIds }, null, 2)}\n`,
  { parser: "json" },
);

if (process.argv.includes("--check")) {
  const committed = await readFile(coursePackIndexPath, "utf8").catch(
    () => undefined,
  );
  if (committed !== coursePackIndex) {
    throw new Error(
      `Generated course-pack index is stale or missing: ${path.relative(root, coursePackIndexPath)}. Run pnpm generate.`,
    );
  }
} else {
  await mkdir(path.dirname(coursePackIndexPath), { recursive: true });
  await writeFile(coursePackIndexPath, coursePackIndex, "utf8");
}

// Schemas the runtime validates against but does not own. Each is copied into
// the Python package so a built wheel carries it, and `--check` fails when the
// copy drifts from the source of truth.
const schemas = [
  {
    source: path.join(root, "config", "schema.json"),
    packaged: path.join(runtimePackage, "config.schema.json"),
    label: "configuration",
  },
  {
    source: path.join(
      root,
      "packages",
      "project-format",
      "schemas",
      "cit-project.schema.json",
    ),
    packaged: path.join(runtimePackage, "cit-project.schema.json"),
    label: "project",
  },
];

for (const { source: sourcePath, packaged: packagedPath, label } of schemas) {
  const source = JSON.parse(await readFile(sourcePath, "utf8"));
  const generated = await format(`${JSON.stringify(source, null, 2)}\n`, {
    parser: "json",
  });

  if (process.argv.includes("--check")) {
    const committed = await readFile(packagedPath, "utf8").catch(
      () => undefined,
    );
    if (committed !== generated) {
      throw new Error(
        `Packaged ${label} schema is stale or missing: ${path.relative(root, packagedPath)}. Run pnpm generate.`,
      );
    }
  } else {
    await mkdir(path.dirname(packagedPath), { recursive: true });
    await writeFile(packagedPath, generated, "utf8");
  }
}

const generatedData = [
  {
    source: path.join(root, "config", "integration-catalog.yaml"),
    outputs: [
      path.join(runtimePackage, "integration-catalog.generated.json"),
      path.join(
        root,
        "tools",
        "hardware",
        "integration-catalog.generated.json",
      ),
    ],
    label: "integration catalog",
  },
  {
    source: path.join(root, "config", "capability-catalog.yaml"),
    outputs: [
      path.join(
        root,
        "packages",
        "integration-sdk-py",
        "src",
        "cit_integration_sdk",
        "capability-catalog.generated.json",
      ),
    ],
    label: "capability catalog",
  },
  {
    source: path.join(root, "config", "external-sources.yaml"),
    outputs: [
      path.join(
        root,
        "packages",
        "integration-sdk-py",
        "src",
        "cit_integration_sdk",
        "external-sources.generated.json",
      ),
      path.join(root, "tools", "hardware", "external-sources.generated.json"),
    ],
    label: "external source catalog",
  },
  ...coursePackIds.map((coursePackId) => ({
    source: path.join(root, "course-packs", coursePackId, "course-pack.yaml"),
    outputs: [
      path.join(
        runtimePackage,
        "course-packs",
        `${coursePackId}.generated.json`,
      ),
      ...(coursePackId === "gesture-ground-robot"
        ? [
            path.join(
              root,
              "adapters",
              "robomaster-leap",
              "src",
              "cit_robomaster_leap",
              "course-pack.generated.json",
            ),
          ]
        : []),
    ],
    label: `${coursePackId} course pack`,
  })),
];

for (const { source: sourcePath, outputs, label } of generatedData) {
  const value = YAML.parse(await readFile(sourcePath, "utf8"));
  const generated = await format(`${JSON.stringify(value, null, 2)}\n`, {
    parser: "json",
  });
  for (const outputPath of outputs) {
    if (process.argv.includes("--check")) {
      const committed = await readFile(outputPath, "utf8").catch(
        () => undefined,
      );
      if (committed !== generated) {
        throw new Error(
          `Generated ${label} is stale or missing: ${path.relative(root, outputPath)}. Run pnpm generate.`,
        );
      }
    } else {
      await mkdir(path.dirname(outputPath), { recursive: true });
      await writeFile(outputPath, generated, "utf8");
    }
  }
}
