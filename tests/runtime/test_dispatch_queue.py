"""FR-072 and FR-067. The queue is the dispatch path, not a structure beside it.

Until this suite existed the queue implemented priority ordering and clearing
for nobody: ``submit`` handed every command straight to an adapter, so a stop
could not overtake a command that was already queued, and clearing a queue
cleared something no command had ever been in.

Every test here holds one adapter inside ``execute`` so there is a command in
flight and a queue behind it, which is the only state in which any of this is
observable.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import pytest
from cit_protocol import CommandResult, DeviceCommandIntent
from cit_runtime import AuditAction, ExecutionMode, Runtime
from cit_runtime.pipeline import CommandQueue
from conftest import make_command

pytestmark = pytest.mark.asyncio


class _Gate:
    """Holds one device's adapter inside ``execute`` until it is released.

    A wrapper in front of the registry's adapter rather than a patched method:
    the fakes use slots, and a test that has to reach inside an object to hold
    it still is a test that will break for reasons unrelated to the runtime.
    """

    def __init__(self, runtime: Runtime, device_id: str) -> None:
        self.opened = asyncio.Event()
        self.entered = asyncio.Event()
        self.order: list[str] = []
        self._inner = runtime.registry.adapter(device_id)
        runtime.registry._adapters[device_id] = self

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def execute(self, command: DeviceCommandIntent, *, now: datetime) -> CommandResult:
        self.order.append(command.action)
        if not self.entered.is_set():
            self.entered.set()
            await self.opened.wait()
        return await self._inner.execute(command, now=now)


async def _session(runtime: Runtime, *device_ids: str) -> str:
    await runtime.start()
    session = runtime.create_session(
        project_id="lesson-1",
        user_id="student-1",
        instructor_id="instructor-1",
        execution_mode=ExecutionMode.SIMULATION,
        safety_policy_id="classroom-physical",
    )
    runtime.bind_devices(session.session_id, list(device_ids))
    runtime.advance_to_ready(session.session_id)
    return session.session_id


async def _until(condition: Any) -> None:
    """Yield to the loop until something becomes true, or fail loudly."""

    for _ in range(1000):
        if condition():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition never became true")


# --------------------------------------------------------------------- FR-072


async def test_a_stop_overtakes_a_student_command_already_queued(runtime: Runtime) -> None:
    session_id = await _session(runtime, "fake-s1-main")
    gate = _Gate(runtime, "fake-s1-main")

    first = asyncio.create_task(
        runtime.submit(make_command(session_id=session_id, device_id="fake-s1-main"))
    )
    await gate.entered.wait()

    queued_student = asyncio.create_task(
        runtime.submit(make_command(session_id=session_id, device_id="fake-s1-main"))
    )
    queued_stop = asyncio.create_task(
        runtime.submit(
            make_command(
                session_id=session_id,
                device_id="fake-s1-main",
                action="halt",
                source="instructor",
            )
        )
    )
    await _until(lambda: len(runtime.pipeline.queue) == 2)

    gate.opened.set()
    await asyncio.gather(first, queued_student, queued_stop)

    # The stop was submitted last and ran first: the queue reorders what has
    # not been dispatched yet, which is the whole of FR-072.
    assert gate.order == ["set", "halt", "set"]


async def test_one_slow_device_does_not_hold_up_another(runtime: Runtime) -> None:
    session_id = await _session(runtime, "fake-s1-main", "fake-lego-main")
    gate = _Gate(runtime, "fake-s1-main")

    held = asyncio.create_task(
        runtime.submit(make_command(session_id=session_id, device_id="fake-s1-main"))
    )
    await gate.entered.wait()

    # A robot executes one command at a time; a classroom does not. Serializing
    # the room would make one student's slow command the reason another
    # student's robot stood still (FR-057).
    other = await runtime.submit(make_command(session_id=session_id, device_id="fake-lego-main"))
    assert other.accepted

    gate.opened.set()
    assert (await held).accepted


# --------------------------------------------------------------------- FR-067


async def test_clearing_the_queue_answers_the_student_whose_command_it_dropped(
    runtime: Runtime,
) -> None:
    session_id = await _session(runtime, "fake-s1-main")
    gate = _Gate(runtime, "fake-s1-main")

    held = asyncio.create_task(
        runtime.submit(make_command(session_id=session_id, device_id="fake-s1-main"))
    )
    await gate.entered.wait()
    queued = asyncio.create_task(
        runtime.submit(make_command(session_id=session_id, device_id="fake-s1-main"))
    )
    await _until(lambda: len(runtime.pipeline.queue) == 1)

    cleared = runtime.clear_queue(device_id=None, actor_id="instructor-1")
    gate.opened.set()

    assert cleared == 1
    dropped = await queued
    # Not a silence and not a hang: the command was refused, with a reason.
    assert not dropped.accepted
    assert dropped.error is not None
    assert dropped.error.code == "SAFETY_POLICY_DENIED"
    assert "discarded" in dropped.error.message
    assert (await held).accepted
    assert runtime.audit.entries(action=AuditAction.COMMAND_DENIED)
    # It never reached the adapter, which is what "cleared" has to mean.
    assert gate.order == ["set"]


async def test_stop_all_leaves_nothing_waiting_for_a_result(runtime: Runtime) -> None:
    session_id = await _session(runtime, "fake-s1-main")
    gate = _Gate(runtime, "fake-s1-main")

    held = asyncio.create_task(
        runtime.submit(make_command(session_id=session_id, device_id="fake-s1-main"))
    )
    await gate.entered.wait()
    queued = asyncio.create_task(
        runtime.submit(make_command(session_id=session_id, device_id="fake-s1-main"))
    )
    await _until(lambda: len(runtime.pipeline.queue) == 1)

    await runtime.stop_all(actor_id="instructor-1")
    gate.opened.set()

    dropped = await asyncio.wait_for(queued, timeout=2)
    assert not dropped.accepted
    assert len(runtime.pipeline.queue) == 0
    await held


async def test_a_disconnect_refuses_that_devices_queued_commands(runtime: Runtime) -> None:
    session_id = await _session(runtime, "fake-s1-main")
    gate = _Gate(runtime, "fake-s1-main")

    held = asyncio.create_task(
        runtime.submit(make_command(session_id=session_id, device_id="fake-s1-main"))
    )
    await gate.entered.wait()
    queued = asyncio.create_task(
        runtime.submit(make_command(session_id=session_id, device_id="fake-s1-main"))
    )
    await _until(lambda: len(runtime.pipeline.queue) == 1)

    await runtime.pipeline.handle_disconnect("fake-s1-main", reason="cable pulled")
    gate.opened.set()

    assert not (await asyncio.wait_for(queued, timeout=2)).accepted
    await held


# ------------------------------------------------------------------ NFR 12.4


async def test_a_full_queue_is_refused_rather_than_growing(runtime: Runtime) -> None:
    session_id = await _session(runtime, "fake-s1-main")
    runtime.pipeline.queue = CommandQueue(max_depth=1)
    gate = _Gate(runtime, "fake-s1-main")

    held = asyncio.create_task(
        runtime.submit(make_command(session_id=session_id, device_id="fake-s1-main"))
    )
    await gate.entered.wait()
    queued = asyncio.create_task(
        runtime.submit(make_command(session_id=session_id, device_id="fake-s1-main"))
    )
    await _until(lambda: len(runtime.pipeline.queue) == 1)

    shed = await runtime.submit(make_command(session_id=session_id, device_id="fake-s1-main"))

    assert not shed.accepted
    assert shed.error is not None
    assert shed.error.code == "SAFETY_POLICY_DENIED"
    gate.opened.set()
    assert (await held).accepted
    assert (await queued).accepted
