"""Student SDK checks that need no event loop."""

from __future__ import annotations

import pytest
from citxr import ALLOWED_CALLS, device, every


def test_the_allowlist_has_no_escape_hatch() -> None:
    assert ALLOWED_CALLS == {"command", "read_sensor", "log", "sleep", "device_info"}
    for forbidden in ("exec", "eval", "open", "socket", "subprocess", "env", "shell"):
        assert forbidden not in ALLOWED_CALLS


def test_the_sdk_exposes_no_filesystem_or_process_surface() -> None:
    """FR-013 as a property of the module, not a promise in a comment."""

    import citxr

    for name in dir(citxr):
        attribute = getattr(citxr, name)
        module = getattr(attribute, "__module__", "")
        assert not module.startswith(("os", "subprocess", "socket", "shutil"))
    assert not hasattr(citxr, "open")
    assert not hasattr(citxr, "system")


def test_a_device_id_must_be_a_real_string() -> None:
    with pytest.raises(ValueError):
        device("")


def test_an_interval_must_be_positive() -> None:
    with pytest.raises(ValueError):
        every(0)
