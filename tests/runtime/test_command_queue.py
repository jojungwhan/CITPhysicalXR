"""FR-072. The priority queue itself, with no runtime around it."""

from __future__ import annotations

import pytest
from cit_runtime import CommandPriority, CommandQueue
from conftest import make_command


def test_queue_pops_in_priority_order() -> None:
    queue = CommandQueue()
    student = make_command(session_id="s", device_id="d", source="student_blocks")
    proposal = make_command(session_id="s", device_id="d", source="agent_mesh")
    stop = make_command(session_id="s", device_id="d", action="stop_all", source="instructor")

    queue.push(proposal, priority=CommandPriority.AI_OR_WEARABLE_PROPOSAL)
    queue.push(student, priority=CommandPriority.STUDENT_COMMAND)
    queue.push(stop, priority=CommandPriority.INSTRUCTOR_STOP_ALL)

    assert queue.pop() is stop
    assert queue.pop() is student
    assert queue.pop() is proposal
    assert queue.pop() is None


def test_queue_refuses_to_grow_without_bound() -> None:
    queue = CommandQueue(max_depth=2)
    for _ in range(2):
        queue.push(
            make_command(session_id="s", device_id="d"),
            priority=CommandPriority.STUDENT_COMMAND,
        )
    with pytest.raises(OverflowError):
        queue.push(
            make_command(session_id="s", device_id="d"),
            priority=CommandPriority.STUDENT_COMMAND,
        )
