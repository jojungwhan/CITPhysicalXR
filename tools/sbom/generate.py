"""Generate a deterministic CycloneDX inventory from pnpm and uv lockfiles."""

from __future__ import annotations

import hashlib
import json
import tomllib
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts/sbom.cdx.json"


def npm_name_version(lock_key: str) -> tuple[str, str]:
    name, separator, version = lock_key.rpartition("@")
    if not separator or not name or not version:
        raise ValueError(f"Unrecognized pnpm package key: {lock_key}")
    return name, version


def npm_components(lock: dict[str, Any]) -> list[dict[str, Any]]:
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        raise ValueError("pnpm-lock.yaml has no packages mapping")
    components: list[dict[str, Any]] = []
    for lock_key in packages:
        name, version = npm_name_version(lock_key)
        purl = f"pkg:npm/{quote(name, safe='/')}@{version}"
        components.append(
            {
                "type": "library",
                "bom-ref": purl,
                "name": name,
                "version": version,
                "purl": purl,
                "properties": [{"name": "citxr:ecosystem", "value": "npm"}],
            }
        )
    return components


def python_components(lock: dict[str, Any]) -> list[dict[str, Any]]:
    packages = lock.get("package")
    if not isinstance(packages, list):
        raise ValueError("uv.lock has no package inventory")
    components: list[dict[str, Any]] = []
    for package in packages:
        if not isinstance(package, dict):
            continue
        name = package.get("name")
        version = package.get("version")
        source = package.get("source")
        if not isinstance(name, str) or not isinstance(version, str):
            raise ValueError(f"Malformed uv package entry: {package!r}")
        registry_package = isinstance(source, dict) and "registry" in source
        namespace = "pypi" if registry_package else "generic"
        purl = f"pkg:{namespace}/{quote(name)}@{version}"
        components.append(
            {
                "type": "library" if registry_package else "application",
                "bom-ref": purl,
                "name": name,
                "version": version,
                "purl": purl,
                "properties": [
                    {
                        "name": "citxr:ecosystem",
                        "value": "python-registry" if registry_package else "python-workspace",
                    }
                ],
            }
        )
    return components


pnpm_text = (ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8")
uv_text = (ROOT / "uv.lock").read_text(encoding="utf-8")
pnpm_lock: object = yaml.safe_load(pnpm_text)
uv_lock: object = tomllib.loads(uv_text)
if not isinstance(pnpm_lock, dict) or not isinstance(uv_lock, dict):
    raise SystemExit("A lockfile root is not an object")

components = npm_components(pnpm_lock) + python_components(uv_lock)
components.sort(key=lambda component: component["bom-ref"])
references = [component["bom-ref"] for component in components]
if len(references) != len(set(references)):
    raise SystemExit("SBOM component references are not unique")

lock_digest = hashlib.sha256((pnpm_text + "\0" + uv_text).encode()).hexdigest()
bom = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.6",
    "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, lock_digest)}",
    "version": 1,
    "metadata": {
        "component": {
            "type": "application",
            "bom-ref": "pkg:generic/cit-physical-xr@0.0.0",
            "name": "cit-physical-xr",
            "version": "0.0.0",
        },
        "properties": [
            {"name": "citxr:source", "value": "pnpm-lock.yaml + uv.lock"},
            {"name": "citxr:lockDigestSha256", "value": lock_digest},
        ],
    },
    "components": components,
}

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(bom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(components)} locked components.")
