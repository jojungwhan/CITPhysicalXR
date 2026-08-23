"""Read exact external-source pins generated from the workspace catalog."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path


class ExternalSourceCheckoutError(RuntimeError):
    """An external checkout does not match its characterized source state."""


@dataclass(frozen=True, slots=True)
class ExternalSource:
    repository: str
    revision: str
    local_directory: str
    license_boundary: str


@lru_cache(maxsize=1)
def _catalog() -> dict[str, ExternalSource]:
    resource = files("cit_integration_sdk").joinpath("external-sources.generated.json")
    value: object = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schemaVersion") != "1.0":
        raise RuntimeError("Packaged CIT external-source catalog is invalid")
    sources = value.get("sources")
    if not isinstance(sources, dict):
        raise RuntimeError("Packaged CIT external-source catalog has no sources")
    result: dict[str, ExternalSource] = {}
    for key, descriptor in sources.items():
        if not isinstance(key, str) or not isinstance(descriptor, dict):
            raise RuntimeError("Packaged CIT external-source catalog has an invalid entry")
        repository = descriptor.get("repository")
        revision = descriptor.get("revision")
        local_directory = descriptor.get("localDirectory")
        license_boundary = descriptor.get("licenseBoundary")
        if not isinstance(repository, str) or not repository:
            raise RuntimeError(f"External-source entry {key!r} has no repository")
        if not isinstance(revision, str) or not revision:
            raise RuntimeError(f"External-source entry {key!r} has no revision")
        if not isinstance(local_directory, str) or not local_directory:
            raise RuntimeError(f"External-source entry {key!r} has no local directory")
        if not isinstance(license_boundary, str) or not license_boundary:
            raise RuntimeError(f"External-source entry {key!r} is incomplete")
        if len(revision) != 40 or any(
            character not in "0123456789abcdef" for character in revision
        ):
            raise RuntimeError(f"External-source entry {key!r} has an invalid revision")
        result[key] = ExternalSource(
            repository=repository,
            revision=revision,
            local_directory=local_directory,
            license_boundary=license_boundary,
        )
    return result


def external_source(key: str) -> ExternalSource:
    """Return one immutable, exact external-source descriptor."""

    try:
        return _catalog()[key]
    except KeyError as error:
        raise KeyError(f"Unknown CIT external source {key!r}") from error


def verify_external_git_checkout(
    repository: Path,
    *,
    expected_revision: str,
    required_path: str,
    source_name: str,
) -> None:
    """Require one exact, clean Git checkout before importing vendor code."""

    resolved_repository = repository.resolve()
    resolved_required_path = (resolved_repository / required_path).resolve()
    if not resolved_required_path.is_relative_to(resolved_repository):
        raise ExternalSourceCheckoutError(f"{source_name} required path escapes its checkout")
    if not resolved_required_path.is_file():
        raise ExternalSourceCheckoutError(
            f"{source_name} required source was not found at {resolved_required_path}"
        )
    try:
        revision_result = subprocess.run(
            ["git", "-C", str(resolved_repository), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        status_result = subprocess.run(
            [
                "git",
                "-C",
                str(resolved_repository),
                "status",
                "--porcelain=v1",
                "--untracked-files=normal",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ExternalSourceCheckoutError(
            f"{source_name} checkout could not be verified"
        ) from error
    revision = revision_result.stdout.strip() if revision_result.returncode == 0 else ""
    if revision != expected_revision:
        raise ExternalSourceCheckoutError(
            f"{source_name} checkout is {revision or 'unknown'}, but this adapter is "
            f"characterized for {expected_revision}"
        )
    if status_result.returncode != 0:
        raise ExternalSourceCheckoutError(f"{source_name} checkout status could not be verified")
    if status_result.stdout.strip():
        raise ExternalSourceCheckoutError(
            f"{source_name} checkout contains local or untracked changes; use a separate "
            f"clean checkout at {expected_revision}"
        )
