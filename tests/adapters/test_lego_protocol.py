"""FR-050: the framed hub protocol refuses everything it does not recognise."""

from __future__ import annotations

import pytest
from cit_lego_pybricks import (
    ARITY,
    HOST_OPERATIONS,
    HUB_OPERATIONS,
    MAX_ARGUMENTS,
    MAX_FRAME_CHARS,
    PROTOCOL_TAG,
    Frame,
    FrameError,
    Operation,
    decode,
    next_sequence,
    sanitize_text,
)


def test_frame_round_trips_through_the_wire_form() -> None:
    frame = Frame(sequence=7, operation=Operation.MOTOR_RUN, arguments=("A", "40", "1000"))

    assert frame.encode() == "C1|7|MOTOR_RUN|A|40|1000"
    assert frame.encode_line().endswith("\n")
    assert decode(frame.encode_line()) == frame


def test_every_operation_has_a_declared_arity() -> None:
    assert set(ARITY) == set(Operation)


def test_the_required_operations_all_exist() -> None:
    # The exact list FR-050 requires. Extra operations are allowed; a missing
    # one is a gap in what a lesson can ask a hub to do.
    required = {
        "HELLO",
        "HEARTBEAT",
        "ACK",
        "ERROR",
        "MOTOR_RUN",
        "MOTOR_RUN_ANGLE",
        "MOTOR_STOP",
        "DRIVE",
        "TURN",
        "SENSOR_READ",
        "SENSOR_SUBSCRIBE",
        "DISPLAY",
        "SOUND",
        "STOP_ALL",
        "TELEMETRY",
    }

    assert required <= {operation.value for operation in Operation}


def test_no_operation_carries_code() -> None:
    """There is no path from a frame to hub-side evaluation."""

    forbidden = {"EVAL", "EXEC", "RUN_PYTHON", "IMPORT", "COMPILE", "SHELL"}

    assert forbidden.isdisjoint({operation.value for operation in Operation})


def test_host_and_hub_vocabularies_do_not_overlap_except_hello() -> None:
    assert HOST_OPERATIONS & HUB_OPERATIONS == {Operation.HELLO}


@pytest.mark.parametrize(
    "line",
    [
        "",
        "   ",
        "C2|1|HEARTBEAT|200",
        "C1|x|HEARTBEAT|200",
        "C1|1|LAUNCH|200",
        "C1|1|MOTOR_RUN|A|40",
        "C1|1|MOTOR_RUN|A|40|1000|extra",
        "C1|1|HEARTBEAT|" + "9" * 25,
        "C1|1|DISPLAY|hello$world",
        "C1|1",
    ],
)
def test_a_malformed_frame_is_refused_rather_than_half_parsed(line: str) -> None:
    with pytest.raises(FrameError):
        decode(line)


def test_a_frame_cannot_exceed_the_hub_buffer() -> None:
    with pytest.raises(FrameError):
        decode(f"{PROTOCOL_TAG}|1|DISPLAY|" + "a" * (MAX_FRAME_CHARS + 10))


def test_an_argument_cannot_smuggle_a_second_frame() -> None:
    with pytest.raises(FrameError):
        Frame(sequence=1, operation=Operation.DISPLAY, arguments=("go|C1|2|STOP_ALL|now",))


def test_argument_count_is_bounded_by_the_grammar() -> None:
    assert MAX_ARGUMENTS == 4
    for minimum, maximum in ARITY.values():
        assert 1 <= minimum <= maximum <= MAX_ARGUMENTS


def test_sequences_wrap_instead_of_growing() -> None:
    assert next_sequence(0) == 1
    assert next_sequence(9999) == 0


def test_student_text_is_filtered_rather_than_refused() -> None:
    assert sanitize_text("Hello! 안녕 <world>") == "Hello  world"
    assert sanitize_text("x" * 40) == "x" * 24
    assert sanitize_text("!!!") == ""


def test_decoding_never_returns_an_operation_the_frame_did_not_carry() -> None:
    frame = decode("C1|12|ACK|11")

    assert frame.operation is Operation.ACK
    assert frame.integer(0) == 11
