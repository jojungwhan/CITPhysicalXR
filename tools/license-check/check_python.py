"""Validate installed Python registry-package licences against an allowlist."""

from __future__ import annotations

import importlib.metadata
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = set(
    json.loads((ROOT / "tools/license-check/allowed-spdx.json").read_text(encoding="utf-8"))[
        "allowed"
    ]
)
CLASSIFIER_TO_SPDX = {
    "Apache Software License": "Apache-2.0",
    "BSD License": "BSD-3-Clause",
    "ISC License (ISCL)": "ISC",
    "MIT License": "MIT",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
}
LICENSE_TEXT_TO_SPDX = {
    "Apache Software License": "Apache-2.0",
    "Apache-2.0": "Apache-2.0",
    "MIT": "MIT",
    "MIT License": "MIT",
    "MIT license": "MIT",
    "Modified BSD License": "BSD-3-Clause",
    "MPL 2.0": "MPL-2.0",
    "BSD-3-Clause": "BSD-3-Clause",
}


def expression_identifiers(expression: str) -> set[str]:
    words = set(re.findall(r"[A-Za-z0-9][A-Za-z0-9.-]*", expression))
    return words - {"AND", "OR", "WITH"}


def detected_licences(metadata: importlib.metadata.PackageMetadata) -> set[str]:
    expression = metadata.get("License-Expression")
    if expression:
        return expression_identifiers(expression)

    detected: set[str] = set()
    for classifier in metadata.get_all("Classifier", []):
        prefix = "License :: OSI Approved :: "
        if classifier.startswith(prefix):
            mapped = CLASSIFIER_TO_SPDX.get(classifier.removeprefix(prefix))
            if mapped:
                detected.add(mapped)

    first_license_line = (metadata.get("License") or "").strip().splitlines()
    if first_license_line:
        mapped = LICENSE_TEXT_TO_SPDX.get(first_license_line[0])
        if mapped:
            detected.add(mapped)
    return detected


lock: dict[str, object] = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
packages = lock.get("package")
if not isinstance(packages, list):
    raise SystemExit("uv.lock has no package inventory")

errors: list[str] = []
checked = 0
skipped_conditionals = 0
workspace_manifests = 0
for manifest_path in ROOT.rglob("pyproject.toml"):
    if any(part in {".venv", "dist"} for part in manifest_path.parts):
        continue
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    project = manifest.get("project")
    if not isinstance(project, dict):
        continue
    if project.get("license") != "Apache-2.0":
        errors.append(f"{manifest_path.relative_to(ROOT)}: project.license must be Apache-2.0")
    workspace_manifests += 1

for package in packages:
    if not isinstance(package, dict):
        continue
    source = package.get("source")
    if not isinstance(source, dict) or "registry" not in source:
        continue
    name = package.get("name")
    version = package.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        errors.append(f"Malformed registry package entry: {package!r}")
        continue
    try:
        metadata = importlib.metadata.metadata(name)
    except importlib.metadata.PackageNotFoundError:
        skipped_conditionals += 1
        continue
    licences = detected_licences(metadata)
    if not licences:
        errors.append(f"{name}=={version}: licence could not be normalized")
    elif not licences <= ALLOWED:
        errors.append(f"{name}=={version}: disallowed licence(s) {sorted(licences - ALLOWED)}")
    checked += 1

if errors:
    raise SystemExit("Python licence validation failed:\n- " + "\n- ".join(errors))
print(
    f"Validated {workspace_manifests} Python workspace manifests and "
    f"{checked} installed Python registry package licences; "
    f"skipped {skipped_conditionals} platform-conditional lock entries."
)
