import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const root = resolve(import.meta.dirname, "../..");
const allowed = new Set(
  JSON.parse(
    readFileSync(join(root, "tools/license-check/allowed-spdx.json"), "utf8"),
  ).allowed,
);

const requiredFiles = ["LICENSE", "THIRD_PARTY_NOTICES.md"];
for (const filename of requiredFiles) {
  try {
    statSync(join(root, filename));
  } catch {
    throw new Error(`Missing required licence file: ${filename}`);
  }
}

const packageManifests = [];
const walk = (directory) => {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if ([".git", ".venv", "dist", "node_modules"].includes(entry.name))
      continue;
    const candidate = join(directory, entry.name);
    if (entry.isDirectory()) walk(candidate);
    else if (entry.name === "package.json") packageManifests.push(candidate);
  }
};
walk(root);

for (const manifestPath of packageManifests) {
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  if (manifest.license !== "Apache-2.0") {
    throw new Error(
      `${relative(root, manifestPath)} must declare license Apache-2.0, got ${manifest.license}`,
    );
  }
}

const virtualStore = join(root, "node_modules", ".pnpm");
if (!existsSync(virtualStore)) {
  throw new Error(
    "node_modules/.pnpm is missing; run the locked pnpm install first",
  );
}

const installedPackages = new Map();
for (const storeEntry of readdirSync(virtualStore, { withFileTypes: true })) {
  if (!storeEntry.isDirectory()) continue;
  const modulesDirectory = join(virtualStore, storeEntry.name, "node_modules");
  if (!existsSync(modulesDirectory)) continue;
  for (const moduleEntry of readdirSync(modulesDirectory, {
    withFileTypes: true,
  })) {
    if (moduleEntry.name.startsWith(".")) continue;
    const modulePath = join(modulesDirectory, moduleEntry.name);
    const candidates = moduleEntry.name.startsWith("@")
      ? readdirSync(modulePath).map((name) => join(modulePath, name))
      : [modulePath];
    for (const candidate of candidates) {
      const manifestPath = join(candidate, "package.json");
      if (!existsSync(manifestPath)) continue;
      const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
      if (
        typeof manifest.name !== "string" ||
        typeof manifest.version !== "string"
      ) {
        continue;
      }
      installedPackages.set(`${manifest.name}@${manifest.version}`, manifest);
    }
  }
}

const licenseGroups = new Set();
for (const [identity, manifest] of installedPackages) {
  if (typeof manifest.license !== "string") {
    throw new Error(`${identity} has no single SPDX licence declaration`);
  }
  if (!allowed.has(manifest.license)) {
    throw new Error(
      `${identity} has disallowed npm licence ${manifest.license}`,
    );
  }
  licenseGroups.add(manifest.license);
}

const pythonLicences = spawnSync(
  "uv",
  ["run", "python", "tools/license-check/check_python.py"],
  {
    cwd: root,
    encoding: "utf8",
  },
);
if (pythonLicences.status !== 0) {
  throw new Error(pythonLicences.stderr || pythonLicences.stdout);
}

const notices = readFileSync(join(root, "THIRD_PARTY_NOTICES.md"), "utf8");
for (const license of new Set([...licenseGroups, "PSF-2.0"])) {
  if (!notices.includes(`\`${license}\``)) {
    throw new Error(
      `THIRD_PARTY_NOTICES.md does not mention detected licence ${license}`,
    );
  }
}

process.stdout.write(
  `Validated ${packageManifests.length} workspace manifests, ${installedPackages.size} installed npm packages, and ${licenseGroups.size} npm licence groups.\n${pythonLicences.stdout}`,
);
