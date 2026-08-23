from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from cit_integration_sdk import ExternalSourceCheckoutError, verify_external_git_checkout


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _clean_checkout(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "external-source"
    required = repository / "src" / "vendor" / "port.py"
    required.parent.mkdir(parents=True)
    required.write_text("PORT = 'characterized'\n", encoding="utf-8")
    _git(repository, "init")
    _git(repository, "config", "user.email", "tests@cit.invalid")
    _git(repository, "config", "user.name", "CIT Tests")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "characterized source")
    return repository, _git(repository, "rev-parse", "HEAD")


def test_exact_clean_external_checkout_is_accepted(tmp_path: Path) -> None:
    repository, revision = _clean_checkout(tmp_path)

    verify_external_git_checkout(
        repository,
        expected_revision=revision,
        required_path="src/vendor/port.py",
        source_name="Test source",
    )


@pytest.mark.parametrize("change_kind", ["tracked", "untracked"])
def test_modified_external_checkout_is_rejected(tmp_path: Path, change_kind: str) -> None:
    repository, revision = _clean_checkout(tmp_path)
    if change_kind == "tracked":
        (repository / "src" / "vendor" / "port.py").write_text(
            "PORT = 'locally modified'\n",
            encoding="utf-8",
        )
    else:
        (repository / "src" / "vendor" / "new_port.py").write_text(
            "PORT = 'untracked'\n",
            encoding="utf-8",
        )

    with pytest.raises(ExternalSourceCheckoutError, match="clean checkout"):
        verify_external_git_checkout(
            repository,
            expected_revision=revision,
            required_path="src/vendor/port.py",
            source_name="Test source",
        )
