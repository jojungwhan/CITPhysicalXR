import { readFileSync, readdirSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import YAML from "yaml";

const root = resolve(import.meta.dirname, "../..");
const excludedDirectories = new Set([
  ".git",
  ".mypy_cache",
  ".pytest_cache",
  ".ruff_cache",
  ".venv",
  "artifacts",
  "dist",
  "node_modules",
  "__pycache__",
]);
const textExtensions = new Set([
  ".gd",
  ".godot",
  ".html",
  ".js",
  ".json",
  ".md",
  ".mjs",
  ".py",
  ".toml",
  ".ts",
  ".tscn",
  ".tsx",
  ".yaml",
  ".yml",
]);
const credentialPatterns = [
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
  /\bAKIA[0-9A-Z]{16}\b/,
  /\bgh[opsu]_[A-Za-z0-9]{20,}\b/,
  /\bsk-[A-Za-z0-9_-]{24,}\b/,
];

const textFiles = [];
const walk = (directory) => {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (entry.isDirectory() && excludedDirectories.has(entry.name)) continue;
    const candidate = join(directory, entry.name);
    if (entry.isDirectory()) walk(candidate);
    else if (
      textExtensions.has(entry.name.slice(entry.name.lastIndexOf(".")))
    ) {
      textFiles.push(candidate);
    }
  }
};
walk(root);

for (const file of textFiles) {
  const content = readFileSync(file, "utf8");
  for (const pattern of credentialPatterns) {
    if (pattern.test(content)) {
      throw new Error(
        `Possible committed credential in ${relative(root, file)}: ${pattern}`,
      );
    }
  }
}

const forbiddenConfigKey =
  /^(?:api[_-]?key|credential|password|secret|token|wifi[_-]?password)$/i;
const inspectConfig = (value, path, filename) => {
  if (Array.isArray(value)) {
    value.forEach((item, index) =>
      inspectConfig(item, `${path}[${index}]`, filename),
    );
  } else if (value !== null && typeof value === "object") {
    for (const [key, nested] of Object.entries(value)) {
      if (forbiddenConfigKey.test(key)) {
        throw new Error(
          `Literal credential field ${path}.${key} in ${filename}`,
        );
      }
      inspectConfig(nested, `${path}.${key}`, filename);
    }
  }
};

const configFiles = [
  join(root, "config", "default.yaml"),
  ...readdirSync(join(root, "config", "examples"))
    .filter((filename) => filename.endsWith(".yaml"))
    .map((filename) => join(root, "config", "examples", filename)),
];
for (const file of configFiles) {
  inspectConfig(
    YAML.parse(readFileSync(file, "utf8")),
    "$",
    relative(root, file),
  );
}

process.stdout.write(
  `Scanned ${textFiles.length} source files and ${configFiles.length} committed configs for credential material.\n`,
);
