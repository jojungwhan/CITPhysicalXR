import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { format } from "prettier";

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
