from __future__ import annotations

from pathlib import Path

import pytest
from cit_runtime.fabric_local_console import _console_url, _read_bootstrap_token


def test_local_console_reads_only_the_exact_generated_credential(tmp_path: Path) -> None:
    environment = tmp_path / "remote-plug-runtime.env"
    token = "cit-admin-" + "a" * 43
    environment.write_text(
        f'CITXR_PUBLIC_ORIGIN="http://127.0.0.1:8766"\nCITXR_FABRIC_BOOTSTRAP_TOKEN="{token}"\n',
        encoding="utf-8",
    )
    environment.chmod(0o600)

    assert _read_bootstrap_token(environment) == token


def test_local_console_rejects_duplicate_credentials(tmp_path: Path) -> None:
    environment = tmp_path / "remote-plug-runtime.env"
    token = "cit-admin-" + "a" * 43
    environment.write_text(
        f'CITXR_FABRIC_BOOTSTRAP_TOKEN="{token}"\nCITXR_FABRIC_BOOTSTRAP_TOKEN="{token}"\n',
        encoding="utf-8",
    )
    environment.chmod(0o600)

    with pytest.raises(ValueError, match="missing or invalid"):
        _read_bootstrap_token(environment)


def test_local_console_ticket_stays_in_the_url_fragment() -> None:
    ticket = "a" * 43

    assert _console_url(ticket) == ("http://127.0.0.1:8766/fabric#console-ticket=" + ticket)
