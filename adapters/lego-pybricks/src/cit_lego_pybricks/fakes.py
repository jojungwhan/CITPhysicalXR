"""A hub simulated in memory, so the adapter can be tested without a radio.

This is not a physics model and does not pretend to be one. It is a protocol
peer: it answers exactly what a hub running the agent answers, refuses exactly
what the agent refuses, and can be told to fail in the ways a real hub fails --
never answering, going away mid-lesson, or having its button pressed by a child
who has decided the lesson is over.

Nothing here is evidence of hardware support (the same rule as the Milestone 1
fakes). It is evidence that the adapter's logic is correct given a hub that
behaves.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .diagnostics import HubDiagnostic, HubTransportError, link_lost
from .hubs import HubModel, PortKind, encode_ports
from .protocol import (
    PROTOCOL_VERSION,
    Frame,
    FrameError,
    HubErrorCode,
    Operation,
    decode,
    next_sequence,
)

DEFAULT_SENSOR_VALUES: Mapping[str, int] = {
    "distance": 320,
    "color": 3,
    "reflection": 42,
    "force": 5,
    "gyro": 0,
    "imu": 0,
    "battery": 87,
}


@dataclass(slots=True)
class FakeHubTransport:
    """An in-memory hub that speaks the framed protocol."""

    hub_name: str
    model: HubModel
    ports: Mapping[str, PortKind]
    battery_percent: int = 87
    #: Set to refuse the next connect, with the diagnostic a real failure has.
    fail_connect: HubDiagnostic | None = None
    #: When true the hub receives frames and never answers them.
    silent: bool = False
    #: A hub that reports a different model than the class configured.
    reported_model_id: str | None = None
    _connected: bool = field(default=False, init=False)
    _outbox: list[str] = field(default_factory=list, init=False)
    _sequence: int = field(default=0, init=False)
    _sensor_values: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_SENSOR_VALUES), init=False
    )
    #: Every frame the hub received, for tests that assert what was sent.
    received: list[Frame] = field(default_factory=list, init=False)
    #: Programs installed through :meth:`download_program` (FR-048).
    downloaded: list[tuple[str, str]] = field(default_factory=list, init=False)
    #: Reasons the hub stopped its motors, in order.
    stops: list[str] = field(default_factory=list, init=False)
    motors_running: bool = field(default=False, init=False)

    # ------------------------------------------------------------- transport

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        if self.fail_connect is not None:
            raise HubTransportError(self.fail_connect)
        self._connected = True

    async def disconnect(self) -> None:
        if self._connected and self.motors_running:
            # A hub whose link drops stops on its own watchdog (FR-053). The
            # fake does it immediately because the point under test is that the
            # runtime never assumes the motors are still under its control.
            self._stop_motors("link-closed")
        self._connected = False

    async def send_line(self, line: str) -> None:
        if not self._connected:
            raise HubTransportError(link_lost(self.hub_name, "the link is closed"))
        try:
            frame = decode(line)
        except FrameError as error:
            self._emit(Operation.ERROR, ("0", HubErrorCode.BAD_FRAME.value))
            del error
            return
        self.received.append(frame)
        if self.silent:
            return
        self._handle(frame)

    def drain_lines(self) -> tuple[str, ...]:
        lines = tuple(self._outbox)
        self._outbox.clear()
        return lines

    async def download_program(self, source: str, *, name: str) -> None:
        if not self._connected:
            raise HubTransportError(link_lost(self.hub_name, "the link is closed"))
        self.downloaded.append((name, source))

    # ------------------------------------------------------------ fault knobs

    def simulate_link_loss(self, reason: str = "out of range") -> None:
        """The hub goes away mid-lesson."""

        if self.motors_running:
            self._stop_motors(f"link-lost:{reason}")
        self._connected = False

    def simulate_button_press(self) -> None:
        """FR-053: the physical button on the hub is a stop control."""

        self._stop_motors("hub-button")
        self._emit(Operation.TELEMETRY, ("button", "center"))

    def set_sensor(self, kind: str, value: int) -> None:
        self._sensor_values[kind] = value

    # ---------------------------------------------------------------- hub side

    def _handle(self, frame: Frame) -> None:
        operation = frame.operation
        if operation is Operation.HELLO:
            self._emit(
                Operation.HELLO,
                (
                    str(PROTOCOL_VERSION),
                    self.reported_model_id or self.model.model_id,
                    str(self.battery_percent),
                    encode_ports(self.model, self.ports),
                ),
            )
            return
        if operation is Operation.STOP_ALL:
            self._stop_motors(frame.argument(0))
            self._ack(frame)
            return
        if operation in _MOTOR_OPERATIONS:
            port = frame.argument(0)
            if port != "ALL" and self.ports.get(port) is not PortKind.MOTOR:
                self._error(frame, HubErrorCode.BAD_PORT)
                return
            self.motors_running = operation is not Operation.MOTOR_STOP
            self._ack(frame)
            return
        if operation in _DRIVE_OPERATIONS:
            if len([kind for kind in self.ports.values() if kind is PortKind.MOTOR]) < 2:
                self._error(frame, HubErrorCode.UNSUPPORTED)
                return
            self.motors_running = True
            self._ack(frame)
            return
        if operation is Operation.SENSOR_READ:
            port, kind = frame.argument(0), frame.argument(1)
            if port == "HUB":
                if kind not in {"battery", "gyro", "imu", "button"}:
                    self._error(frame, HubErrorCode.BAD_PORT)
                    return
            elif port not in self.ports:
                self._error(frame, HubErrorCode.BAD_PORT)
                return
            self._ack(frame)
            self._emit(Operation.TELEMETRY, (kind, str(self._sensor_values.get(kind, 0))))
            return
        if operation in {Operation.HEARTBEAT, Operation.DISPLAY, Operation.SOUND}:
            self._ack(frame)
            return
        if operation is Operation.SENSOR_SUBSCRIBE:
            self._ack(frame)
            return
        self._error(frame, HubErrorCode.UNSUPPORTED)

    def _stop_motors(self, reason: str) -> None:
        self.motors_running = False
        self.stops.append(reason)

    def _ack(self, frame: Frame) -> None:
        self._emit(Operation.ACK, (str(frame.sequence),))

    def _error(self, frame: Frame, code: HubErrorCode) -> None:
        self._emit(Operation.ERROR, (str(frame.sequence), code.value))

    def _emit(self, operation: Operation, arguments: tuple[str, ...]) -> None:
        self._sequence = next_sequence(self._sequence)
        self._outbox.append(
            Frame(sequence=self._sequence, operation=operation, arguments=arguments).encode_line()
        )


_MOTOR_OPERATIONS = frozenset(
    {
        Operation.MOTOR_RUN,
        Operation.MOTOR_RUN_ANGLE,
        Operation.MOTOR_RUN_TARGET,
        Operation.MOTOR_STOP,
    }
)

_DRIVE_OPERATIONS = frozenset(
    {
        Operation.DRIVE,
        Operation.DRIVE_STRAIGHT,
        Operation.TURN,
    }
)
