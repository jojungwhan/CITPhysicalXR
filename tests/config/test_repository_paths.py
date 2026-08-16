from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from cit_runtime.config import (
    ConfigurationError,
    RepositoryPathUnavailable,
    load_config,
    select_repository_path,
)

CONFIG = {
    "version": 1,
    "externalRepositories": {
        "agentMesh": {
            "paths": {
                "windows": r"D:\dev\glasses2CLI",
                "linux": "/srv/cit/agent-cli-mesh",
            }
        }
    },
}


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("windows", r"D:\dev\glasses2CLI"),
        ("linux", "/srv/cit/agent-cli-mesh"),
    ],
)
def test_repository_path_selection_preserves_platform_syntax(platform: str, expected: str) -> None:
    assert select_repository_path(CONFIG, "agentMesh", platform=platform) == expected


def test_committed_external_repository_example_matches_configuration_schema() -> None:
    example = load_config("config/examples/local-foundation.example.yaml")

    assert example["version"] == 1
    assert select_repository_path(example, "agentMesh", platform="windows") == r"D:\dev\glasses2CLI"


def test_configuration_schema_rejects_literal_credential_fields(tmp_path: Path) -> None:
    value = load_config("config/default.yaml")
    value["credentials"] = {"token": "must-not-be-committed"}
    candidate = tmp_path / "unsafe.yaml"
    candidate.write_text(yaml.safe_dump(value), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="credentials"):
        load_config(candidate)


def test_missing_platform_path_is_actionable() -> None:
    windows_only = {
        "externalRepositories": {"agentMesh": {"paths": {"windows": r"D:\dev\glasses2CLI"}}}
    }

    with pytest.raises(RepositoryPathUnavailable, match="linux"):
        select_repository_path(windows_only, "agentMesh", platform="linux")
