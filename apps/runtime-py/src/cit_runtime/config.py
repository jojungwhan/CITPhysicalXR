"""Validated, cross-platform selection of external repository paths."""

from __future__ import annotations

import json
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


class ConfigurationError(ValueError):
    """Raised when a configuration file does not match the public schema."""


class RepositoryPathUnavailable(ValueError):
    """Raised when an external checkout has no path for the requested host."""


def _schema() -> dict[str, Any]:
    resource = files("cit_runtime").joinpath("config.schema.json")
    value: object = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Packaged configuration schema root must be an object")
    return value


def load_config(path: str | Path) -> dict[str, Any]:
    """Load YAML and reject unknown or unsafe configuration fields."""

    source = Path(path)
    value: object = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError("Configuration root must be an object")

    validator = Draft202012Validator(_schema(), format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(value),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
            for error in errors
        )
        raise ConfigurationError(f"Invalid configuration: {details}")
    return value


def select_repository_path(config: Mapping[str, Any], repository_id: str, *, platform: str) -> str:
    """Return the configured platform-native path without rewriting its syntax."""

    if platform not in {"linux", "windows"}:
        raise ValueError(f"Unsupported platform {platform!r}; expected 'windows' or 'linux'")

    repositories = config.get("externalRepositories")
    repository = repositories.get(repository_id) if isinstance(repositories, Mapping) else None
    paths = repository.get("paths") if isinstance(repository, Mapping) else None
    selected = paths.get(platform) if isinstance(paths, Mapping) else None

    if not isinstance(selected, str) or not selected:
        raise RepositoryPathUnavailable(
            f"External repository {repository_id!r} has no {platform!r} path"
        )
    return selected
