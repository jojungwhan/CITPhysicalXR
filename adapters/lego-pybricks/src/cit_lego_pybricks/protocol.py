"""The framed hub-agent protocol (FR-050).

A SPIKE hub running Pybricks is a MicroPython machine with a few hundred
kilobytes of RAM and a BLE link that delivers small writes. The protocol is
therefore text, one frame per line, bounded in every dimension:

```text
C1|<sequence>|<OPERATION>|<argument1>|<argument2>
```

Rules that are enforced rather than documented:

- **Bounded.** A frame is at most :data:`MAX_FRAME_CHARS` characters with at
  most :data:`MAX_ARGUMENTS` arguments of :data:`MAX_ARGUMENT_CHARS` each. A
  hub cannot be made to allocate an unbounded buffer by a peer that lies.
- **Closed vocabulary.** The operation must be a member of :class:`Operation`
  and must carry exactly the number of arguments that operation takes. There is
  no `EVAL`, no `EXEC`, and no operation that carries Python source: the only
  code that ever reaches the hub is the firmware and an explicitly downloaded
  program (FR-048), never a frame.
- **Restricted alphabet.** ``|`` and newline can never appear inside a field, so
  a frame cannot be smuggled inside an argument.
- **Sequenced.** Every command carries a sequence number that its ``ACK`` or
  ``ERROR`` quotes back, so a reply is matched to a request rather than assumed.

The hub agent in ``firmware/lego-hub-agent/hub_agent.py`` implements the same
grammar in MicroPython-safe code. ``tests/firmware/test_hub_agent.py`` encodes
with one side and decodes with the other, so the two cannot drift apart
silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

PROTOCOL_TAG = "C1"
PROTOCOL_VERSION = 1
FIELD_SEPARATOR = "|"
FRAME_TERMINATOR = "\n"

MAX_FRAME_CHARS = 96
MAX_ARGUMENTS = 4
MAX_ARGUMENT_CHARS = 24
SEQUENCE_MODULUS = 10_000

_ALLOWED_ARGUMENT_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 _.,:+-"
)


class Operation(StrEnum):
    """Every operation the hub agent understands. There are no others."""

    HELLO = "HELLO"
    HEARTBEAT = "HEARTBEAT"
    ACK = "ACK"
    ERROR = "ERROR"
    MOTOR_RUN = "MOTOR_RUN"
    MOTOR_RUN_ANGLE = "MOTOR_RUN_ANGLE"
    MOTOR_RUN_TARGET = "MOTOR_RUN_TARGET"
    MOTOR_STOP = "MOTOR_STOP"
    DRIVE = "DRIVE"
    DRIVE_STRAIGHT = "DRIVE_STRAIGHT"
    TURN = "TURN"
    SENSOR_READ = "SENSOR_READ"
    SENSOR_SUBSCRIBE = "SENSOR_SUBSCRIBE"
    DISPLAY = "DISPLAY"
    SOUND = "SOUND"
    STOP_ALL = "STOP_ALL"
    TELEMETRY = "TELEMETRY"


#: Inclusive ``(minimum, maximum)`` argument count for each operation.
ARITY: dict[Operation, tuple[int, int]] = {
    Operation.HELLO: (2, 4),
    Operation.HEARTBEAT: (1, 1),
    Operation.ACK: (1, 2),
    Operation.ERROR: (2, 2),
    Operation.MOTOR_RUN: (3, 3),
    Operation.MOTOR_RUN_ANGLE: (3, 3),
    Operation.MOTOR_RUN_TARGET: (3, 3),
    Operation.MOTOR_STOP: (1, 1),
    Operation.DRIVE: (3, 3),
    Operation.DRIVE_STRAIGHT: (2, 2),
    Operation.TURN: (2, 2),
    Operation.SENSOR_READ: (2, 2),
    Operation.SENSOR_SUBSCRIBE: (3, 3),
    Operation.DISPLAY: (1, 1),
    Operation.SOUND: (2, 2),
    Operation.STOP_ALL: (1, 1),
    Operation.TELEMETRY: (2, 3),
}

#: Operations only the runtime may send.
HOST_OPERATIONS: frozenset[Operation] = frozenset(
    {
        Operation.HELLO,
        Operation.HEARTBEAT,
        Operation.MOTOR_RUN,
        Operation.MOTOR_RUN_ANGLE,
        Operation.MOTOR_RUN_TARGET,
        Operation.MOTOR_STOP,
        Operation.DRIVE,
        Operation.DRIVE_STRAIGHT,
        Operation.TURN,
        Operation.SENSOR_READ,
        Operation.SENSOR_SUBSCRIBE,
        Operation.DISPLAY,
        Operation.SOUND,
        Operation.STOP_ALL,
    }
)

#: Operations only the hub may send.
HUB_OPERATIONS: frozenset[Operation] = frozenset(
    {
        Operation.HELLO,
        Operation.ACK,
        Operation.ERROR,
        Operation.TELEMETRY,
    }
)


class HubErrorCode(StrEnum):
    """The closed set of failures a hub may report."""

    BAD_FRAME = "BAD_FRAME"
    BAD_PORT = "BAD_PORT"
    BAD_ARGUMENT = "BAD_ARGUMENT"
    UNSUPPORTED = "UNSUPPORTED"
    BUSY = "BUSY"
    WATCHDOG = "WATCHDOG"


class FrameError(ValueError):
    """A frame that must not be acted on. Never raised past a rejection."""


@dataclass(frozen=True, slots=True)
class Frame:
    """One protocol line, already validated."""

    sequence: int
    operation: Operation
    arguments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_sequence(self.sequence)
        minimum, maximum = ARITY[self.operation]
        if not minimum <= len(self.arguments) <= maximum:
            raise FrameError(
                f"{self.operation.value} takes {minimum}-{maximum} arguments, "
                f"got {len(self.arguments)}"
            )
        for argument in self.arguments:
            _validate_argument(argument)
        if len(self.encode()) > MAX_FRAME_CHARS:
            raise FrameError(f"Frame exceeds {MAX_FRAME_CHARS} characters")

    def encode(self) -> str:
        """The wire line, without its terminator."""

        parts = [PROTOCOL_TAG, str(self.sequence), self.operation.value, *self.arguments]
        return FIELD_SEPARATOR.join(parts)

    def encode_line(self) -> str:
        """The wire line with its terminator, ready to write to hub stdin."""

        return f"{self.encode()}{FRAME_TERMINATOR}"

    def argument(self, index: int) -> str:
        try:
            return self.arguments[index]
        except IndexError as error:
            raise FrameError(f"{self.operation.value} has no argument {index}") from error

    def integer(self, index: int) -> int:
        raw = self.argument(index)
        try:
            return int(raw)
        except ValueError as error:
            raise FrameError(f"{raw!r} is not an integer") from error


def _validate_sequence(sequence: int) -> None:
    if not isinstance(sequence, int) or isinstance(sequence, bool):
        raise FrameError("Sequence must be an integer")
    if not 0 <= sequence < SEQUENCE_MODULUS:
        raise FrameError(f"Sequence must be within [0, {SEQUENCE_MODULUS})")


def _validate_argument(argument: str) -> None:
    if not isinstance(argument, str):
        raise FrameError("Frame arguments must be strings")
    if len(argument) > MAX_ARGUMENT_CHARS:
        raise FrameError(f"Argument exceeds {MAX_ARGUMENT_CHARS} characters")
    illegal = sorted(set(argument) - _ALLOWED_ARGUMENT_CHARS)
    if illegal:
        raise FrameError(f"Argument contains forbidden characters: {illegal}")


def next_sequence(current: int) -> int:
    """Sequences wrap rather than grow, so the field stays four characters."""

    return (current + 1) % SEQUENCE_MODULUS


def sanitize_text(text: str, *, limit: int = MAX_ARGUMENT_CHARS) -> str:
    """Make arbitrary student text safe to place in one argument.

    A student writes what they like on the hub display. Rejecting the whole
    command because they typed an exclamation mark would be a worse lesson than
    showing them the letters that fit, so the text is filtered and truncated
    rather than refused.
    """

    filtered = "".join(character for character in text if character in _ALLOWED_ARGUMENT_CHARS)
    return filtered.strip()[:limit]


def decode(line: str) -> Frame:
    """Parse one line. Anything unexpected raises rather than half-parses."""

    if not isinstance(line, str):
        raise FrameError("A frame must be text")
    stripped = line.strip("\r\n")
    if not stripped:
        raise FrameError("Empty frame")
    if len(stripped) > MAX_FRAME_CHARS:
        raise FrameError(f"Frame exceeds {MAX_FRAME_CHARS} characters")

    parts = stripped.split(FIELD_SEPARATOR)
    if len(parts) < 3:
        raise FrameError("A frame needs a tag, a sequence, and an operation")
    tag, raw_sequence, raw_operation, *arguments = parts

    if tag != PROTOCOL_TAG:
        raise FrameError(f"Unsupported protocol tag {tag!r}; this runtime speaks {PROTOCOL_TAG}")
    if not raw_sequence.isdigit():
        raise FrameError(f"Sequence {raw_sequence!r} is not a number")
    try:
        operation = Operation(raw_operation)
    except ValueError as error:
        raise FrameError(f"Unknown operation {raw_operation!r}") from error
    if len(arguments) > MAX_ARGUMENTS:
        raise FrameError(f"A frame carries at most {MAX_ARGUMENTS} arguments")

    return Frame(
        sequence=int(raw_sequence),
        operation=operation,
        arguments=tuple(arguments),
    )
