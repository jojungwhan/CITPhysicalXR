import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { format } from "prettier";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const sourcePath = path.join(root, "config", "schema.json");
const packagedPath = path.join(
  root,
  "apps",
  "runtime-py",
  "src",
  "cit_runtime",
  "config.schema.json",
);
const source = JSON.parse(await readFile(sourcePath, "utf8"));
const generated = await format(`${JSON.stringify(source, null, 2)}\n`, {
  parser: "json",
});

if (process.argv.includes("--check")) {
  const committed = await readFile(packagedPath, "utf8").catch(() => undefined);
  if (committed !== generated) {
    throw new Error(
      `Packaged configuration schema is stale or missing: ${path.relative(root, packagedPath)}. Run pnpm generate.`,
    );
  }
} else {
  await mkdir(path.dirname(packagedPath), { recursive: true });
  await writeFile(packagedPath, generated, "utf8");
}
