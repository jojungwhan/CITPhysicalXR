from __future__ import annotations

import pytest
from cit_integration_sdk import CommandReplayCache


def test_command_replay_cache_retains_recent_results_and_evicts_oldest() -> None:
    cache = CommandReplayCache[dict[str, object]](max_entries=2)
    cache.remember("command-a", {"result": "a"})
    cache.remember("command-b", {"result": "b"})

    assert cache.get("command-a") == {"result": "a"}
    cache.remember("command-c", {"result": "c"})

    assert cache.contains("command-a")
    assert not cache.contains("command-b")
    assert cache.get("command-c") == {"result": "c"}
    assert len(cache) == 2


def test_command_replay_cache_rejects_unbounded_or_empty_configuration() -> None:
    with pytest.raises(ValueError, match="positive"):
        CommandReplayCache[bool](max_entries=0)
