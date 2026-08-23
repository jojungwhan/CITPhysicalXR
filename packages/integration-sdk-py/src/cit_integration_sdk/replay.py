"""Bounded command-result replay for independently deployed adapters."""

from __future__ import annotations

from collections import OrderedDict
from typing import Generic, TypeVar

ResultT = TypeVar("ResultT")


class CommandReplayCache(Generic[ResultT]):
    """Retain recent terminal results without unbounded adapter memory growth."""

    def __init__(self, *, max_entries: int = 4_096) -> None:
        if max_entries <= 0:
            raise ValueError("Command replay cache size must be positive")
        self._max_entries = max_entries
        self._entries: OrderedDict[str, ResultT] = OrderedDict()

    def contains(self, command_id: str) -> bool:
        return command_id in self._entries

    def get(self, command_id: str) -> ResultT:
        result = self._entries[command_id]
        self._entries.move_to_end(command_id)
        return result

    def remember(self, command_id: str, result: ResultT) -> None:
        self._entries[command_id] = result
        self._entries.move_to_end(command_id)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def __len__(self) -> int:
        return len(self._entries)
