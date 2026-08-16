"""The CIT hub agent: the program that runs on a LEGO hub under Pybricks.

This file is downloaded to a SPIKE Prime, SPIKE Essential, or MINDSTORMS Robot
Inventor hub running Pybricks firmware, and it is the only thing on the hub that
the runtime talks to. It reads framed lines from ``stdin``, performs bounded
motor, sensor, and display operations, and prints framed replies to ``stdout``
(FR-047, FR-050).

Three properties matter more than anything else here:

- **It never evaluates anything.** There is no ``eval``, no ``exec``, and no
  operation that carries code. A frame selects one of a fixed list of actions
  with numeric arguments, and an unknown operation is an error reply.
- **It stops on its own.** If the runtime goes quiet for longer than the
  watchdog window, the hub stops its motors without being asked (FR-049,
  FR-053). Losing Bluetooth must not mean a robot that keeps driving.
- **It runs on MicroPython.** No dataclasses, no typing module, no f-string
  nesting tricks, no comprehension the hub cannot afford. Every hardware import
  happens inside :func:`build_machine`, so this module also imports cleanly on
  CPython and its logic is tested there
  (``tests/firmware/test_hub_agent.py``).

The host half of the protocol lives in
``adapters/lego-pybricks/src/cit_lego_pybricks/protocol.py``. A test encodes with
each side and decodes with the other, so the two cannot drift.
"""

PROTOCOL_TAG = "C1"
PROTOCOL_VERSION = 1
MAX_FRAME_CHARS = 96
MAX_ARGUMENTS = 4
MAX_ARGUMENT_CHARS = 24
SEQUENCE_MODULUS = 10000

ALLOWED_ARGUMENT_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 _.,:+-"

OPERATIONS = (
    "HELLO",
    "HEARTBEAT",
    "ACK",
    "ERROR",
    "MOTOR_RUN",
    "MOTOR_RUN_ANGLE",
    "MOTOR_RUN_TARGET",
    "MOTOR_STOP",
    "DRIVE",
    "DRIVE_STRAIGHT",
    "TURN",
    "SENSOR_READ",
    "SENSOR_SUBSCRIBE",
    "DISPLAY",
    "SOUND",
    "STOP_ALL",
    "TELEMETRY",
)

ARITY = {
    "HELLO": (2, 4),
    "HEARTBEAT": (1, 1),
    "ACK": (1, 2),
    "ERROR": (2, 2),
    "MOTOR_RUN": (3, 3),
    "MOTOR_RUN_ANGLE": (3, 3),
    "MOTOR_RUN_TARGET": (3, 3),
    "MOTOR_STOP": (1, 1),
    "DRIVE": (3, 3),
    "DRIVE_STRAIGHT": (2, 2),
    "TURN": (2, 2),
    "SENSOR_READ": (2, 2),
    "SENSOR_SUBSCRIBE": (3, 3),
    "DISPLAY": (1, 1),
    "SOUND": (2, 2),
    "STOP_ALL": (1, 1),
    "TELEMETRY": (2, 3),
}

PORT_CODES = {"empty": "-", "motor": "m", "distance": "d", "color": "c", "force": "f"}

WATCHDOG_MILLISECONDS = 500
MAX_MOTOR_PERCENT = 100
MAX_COMMAND_MILLISECONDS = 5000
MAX_MOTOR_DEGREES_PER_SECOND = 1000


class FrameError(Exception):
    """A frame that must not be acted on."""


def encode_frame(sequence, operation, arguments):
    """Build one wire line. Raises FrameError rather than emitting nonsense."""

    if operation not in ARITY:
        raise FrameError("unknown operation")
    low, high = ARITY[operation]
    if len(arguments) < low or len(arguments) > high:
        raise FrameError("wrong argument count")
    parts = [PROTOCOL_TAG, str(sequence % SEQUENCE_MODULUS), operation]
    for argument in arguments:
        text = str(argument)
        if len(text) > MAX_ARGUMENT_CHARS:
            raise FrameError("argument too long")
        for character in text:
            if character not in ALLOWED_ARGUMENT_CHARS:
                raise FrameError("forbidden character")
        parts.append(text)
    line = "|".join(parts)
    if len(line) > MAX_FRAME_CHARS:
        raise FrameError("frame too long")
    return line


def decode_frame(line):
    """Parse one wire line into ``(sequence, operation, arguments)``."""

    if line is None:
        raise FrameError("empty frame")
    text = line.strip()
    if not text:
        raise FrameError("empty frame")
    if len(text) > MAX_FRAME_CHARS:
        raise FrameError("frame too long")
    parts = text.split("|")
    if len(parts) < 3:
        raise FrameError("short frame")
    if parts[0] != PROTOCOL_TAG:
        raise FrameError("bad tag")
    if not parts[1].isdigit():
        raise FrameError("bad sequence")
    sequence = int(parts[1])
    if sequence >= SEQUENCE_MODULUS:
        raise FrameError("bad sequence")
    operation = parts[2]
    if operation not in ARITY:
        raise FrameError("unknown operation")
    arguments = parts[3:]
    if len(arguments) > MAX_ARGUMENTS:
        raise FrameError("too many arguments")
    low, high = ARITY[operation]
    if len(arguments) < low or len(arguments) > high:
        raise FrameError("wrong argument count")
    for argument in arguments:
        if len(argument) > MAX_ARGUMENT_CHARS:
            raise FrameError("argument too long")
        for character in argument:
            if character not in ALLOWED_ARGUMENT_CHARS:
                raise FrameError("forbidden character")
    return sequence, operation, arguments


def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def to_int(text):
    try:
        return int(text)
    except (TypeError, ValueError) as error:
        raise FrameError("not a number") from error


def percent_to_speed(percent):
    """Hub percent to the degrees per second Pybricks actually wants."""

    bounded = clamp(percent, -MAX_MOTOR_PERCENT, MAX_MOTOR_PERCENT)
    return int(bounded * MAX_MOTOR_DEGREES_PER_SECOND / 100)


class HubAgent:
    """The protocol half. Hardware lives behind ``machine``."""

    def __init__(self, machine, watchdog_milliseconds=WATCHDOG_MILLISECONDS):
        self.machine = machine
        self.watchdog_milliseconds = watchdog_milliseconds
        self.sequence = 0
        self.last_frame_at = 0
        self.motors_running = False
        self.running = True
        self.subscriptions = []

    # ------------------------------------------------------------------ replies

    def _emit(self, operation, arguments):
        self.sequence = (self.sequence + 1) % SEQUENCE_MODULUS
        return encode_frame(self.sequence, operation, arguments)

    def _ack(self, sequence):
        return self._emit("ACK", [str(sequence)])

    def _error(self, sequence, code):
        return self._emit("ERROR", [str(sequence), code])

    # ------------------------------------------------------------------ inbound

    def handle_line(self, line, now_milliseconds):
        """Act on one received line and return the lines to send back."""

        try:
            sequence, operation, arguments = decode_frame(line)
        except FrameError:
            return [self._error(0, "BAD_FRAME")]

        self.last_frame_at = now_milliseconds
        try:
            return self._dispatch(sequence, operation, arguments)
        except FrameError:
            return [self._error(sequence, "BAD_ARGUMENT")]

    def _dispatch(self, sequence, operation, arguments):
        if operation == "HELLO":
            return [
                self._emit(
                    "HELLO",
                    [
                        str(PROTOCOL_VERSION),
                        self.machine.model_id,
                        str(self.machine.battery()),
                        self._port_report(),
                    ],
                )
            ]
        if operation == "HEARTBEAT":
            return [self._ack(sequence)]
        if operation == "STOP_ALL":
            self._stop_all()
            return [self._ack(sequence)]
        if operation == "MOTOR_STOP":
            port = arguments[0]
            if port == "ALL":
                self._stop_all()
                return [self._ack(sequence)]
            if not self._is_motor(port):
                return [self._error(sequence, "BAD_PORT")]
            self.machine.motor_stop(port)
            self.motors_running = False
            return [self._ack(sequence)]
        if operation == "MOTOR_RUN":
            port = arguments[0]
            if not self._is_motor(port):
                return [self._error(sequence, "BAD_PORT")]
            percent = clamp(to_int(arguments[1]), -MAX_MOTOR_PERCENT, MAX_MOTOR_PERCENT)
            milliseconds = clamp(to_int(arguments[2]), 1, MAX_COMMAND_MILLISECONDS)
            self.machine.motor_run(port, percent_to_speed(percent), milliseconds)
            self.motors_running = True
            return [self._ack(sequence)]
        if operation in ("MOTOR_RUN_ANGLE", "MOTOR_RUN_TARGET"):
            port = arguments[0]
            if not self._is_motor(port):
                return [self._error(sequence, "BAD_PORT")]
            angle = clamp(to_int(arguments[1]), -3600, 3600)
            percent = clamp(to_int(arguments[2]), -MAX_MOTOR_PERCENT, MAX_MOTOR_PERCENT)
            speed = percent_to_speed(percent)
            if operation == "MOTOR_RUN_ANGLE":
                self.machine.motor_run_angle(port, speed, angle)
            else:
                self.machine.motor_run_target(port, speed, angle)
            self.motors_running = True
            return [self._ack(sequence)]
        if operation in ("DRIVE", "DRIVE_STRAIGHT", "TURN"):
            if not self.machine.has_drive_base():
                return [self._error(sequence, "UNSUPPORTED")]
            return self._drive(sequence, operation, arguments)
        if operation == "SENSOR_READ":
            port = arguments[0]
            kind = arguments[1]
            value = self.machine.sensor_read(port, kind)
            if value is None:
                return [self._error(sequence, "BAD_PORT")]
            return [self._ack(sequence), self._emit("TELEMETRY", [kind, str(value)])]
        if operation == "SENSOR_SUBSCRIBE":
            port = arguments[0]
            kind = arguments[1]
            interval = clamp(to_int(arguments[2]), 50, 5000)
            if self.machine.sensor_read(port, kind) is None:
                return [self._error(sequence, "BAD_PORT")]
            self.subscriptions.append([port, kind, interval, 0])
            return [self._ack(sequence)]
        if operation == "DISPLAY":
            self.machine.display(arguments[0])
            return [self._ack(sequence)]
        if operation == "SOUND":
            frequency = clamp(to_int(arguments[0]), 50, 10000)
            milliseconds = clamp(to_int(arguments[1]), 1, MAX_COMMAND_MILLISECONDS)
            self.machine.sound(frequency, milliseconds)
            return [self._ack(sequence)]
        return [self._error(sequence, "UNSUPPORTED")]

    def _drive(self, sequence, operation, arguments):
        if operation == "DRIVE":
            percent = clamp(to_int(arguments[0]), -MAX_MOTOR_PERCENT, MAX_MOTOR_PERCENT)
            turn = clamp(to_int(arguments[1]), -MAX_MOTOR_PERCENT, MAX_MOTOR_PERCENT)
            milliseconds = clamp(to_int(arguments[2]), 1, MAX_COMMAND_MILLISECONDS)
            self.machine.drive(percent_to_speed(percent), turn, milliseconds)
        elif operation == "DRIVE_STRAIGHT":
            millimetres = clamp(to_int(arguments[0]), -2000, 2000)
            self.machine.drive_straight(millimetres)
        else:
            angle = clamp(to_int(arguments[0]), -720, 720)
            self.machine.turn(angle)
        self.motors_running = True
        return [self._ack(sequence)]

    # ------------------------------------------------------------------- timing

    def poll(self, now_milliseconds):
        """Run the watchdog and the hub's own controls. Returns lines to send."""

        outgoing = []

        button = self.machine.button_pressed()
        if button:
            # FR-053: the button on the hub is a stop control that works even
            # when the computer is not listening.
            self._stop_all()
            outgoing.append(self._emit("TELEMETRY", ["button", button]))

        elapsed = now_milliseconds - self.last_frame_at
        if self.motors_running and elapsed > self.watchdog_milliseconds:
            self._stop_all()
            outgoing.append(self._error(0, "WATCHDOG"))

        for subscription in self.subscriptions:
            port, kind, interval, last = subscription
            if now_milliseconds - last < interval:
                continue
            subscription[3] = now_milliseconds
            value = self.machine.sensor_read(port, kind)
            if value is not None:
                outgoing.append(self._emit("TELEMETRY", [kind, str(value)]))

        return outgoing

    # ------------------------------------------------------------------ helpers

    def _stop_all(self):
        self.machine.stop_all()
        self.motors_running = False

    def _is_motor(self, port):
        return self.machine.ports.get(port) == "motor"

    def _port_report(self):
        report = ""
        for port in self.machine.port_order:
            kind = self.machine.ports.get(port, "empty")
            report += PORT_CODES.get(kind, "-")
        return report


def build_machine():  # pragma: no cover - runs only on a hub
    """Build the hardware machine. Every Pybricks import happens here.

    Untested: this half needs a hub. `docs/LEGO_SETUP.md` is the bring-up
    checklist.
    """

    from pybricks.parameters import Button, Port
    from pybricks.pupdevices import ColorSensor, ForceSensor, Motor, UltrasonicSensor
    from pybricks.robotics import DriveBase
    from pybricks.tools import wait

    try:
        from pybricks.hubs import PrimeHub as Hub

        model_id = "spike-prime"
        port_order = ("A", "B", "C", "D", "E", "F")
    except ImportError:
        from pybricks.hubs import EssentialHub as Hub

        model_id = "spike-essential"
        port_order = ("A", "B")

    hub = Hub()
    devices = {}
    kinds = {}
    for letter in port_order:
        port = getattr(Port, letter)
        for kind, factory in (
            ("motor", Motor),
            ("distance", UltrasonicSensor),
            ("color", ColorSensor),
            ("force", ForceSensor),
        ):
            try:
                devices[letter] = factory(port)
                kinds[letter] = kind
                break
            except OSError:
                continue
        else:
            kinds[letter] = "empty"

    motors = [letter for letter in port_order if kinds.get(letter) == "motor"]
    drive_base = None
    if len(motors) >= 2:
        drive_base = DriveBase(
            devices[motors[0]], devices[motors[1]], wheel_diameter=56, axle_track=114
        )

    class PybricksMachine:
        model_id = None
        ports = None
        port_order = ()

        def battery(self):
            return int(hub.battery.voltage() / 80)

        def has_drive_base(self):
            return drive_base is not None

        def motor_run(self, port, speed, milliseconds):
            devices[port].run_time(speed, milliseconds, wait=False)

        def motor_run_angle(self, port, speed, angle):
            devices[port].run_angle(speed, angle, wait=False)

        def motor_run_target(self, port, speed, angle):
            devices[port].run_target(speed, angle, wait=False)

        def motor_stop(self, port):
            devices[port].stop()

        def drive(self, speed, turn, milliseconds):
            drive_base.drive(speed, turn)
            wait(milliseconds)
            drive_base.stop()

        def drive_straight(self, millimetres):
            drive_base.straight(millimetres)

        def turn(self, angle):
            drive_base.turn(angle)

        def stop_all(self):
            if drive_base is not None:
                drive_base.stop()
            for letter in motors:
                devices[letter].stop()

        def sensor_read(self, port, kind):
            if port == "HUB":
                if kind == "battery":
                    return self.battery()
                if kind in ("gyro", "imu"):
                    return int(hub.imu.heading())
                if kind == "button":
                    return 1 if hub.buttons.pressed() else 0
                return None
            device = devices.get(port)
            if device is None:
                return None
            if kind == "distance":
                return int(device.distance())
            if kind == "color":
                return int(device.reflection())
            if kind == "reflection":
                return int(device.reflection())
            if kind == "force":
                return int(device.force())
            return None

        def display(self, text):
            hub.display.text(text)

        def sound(self, frequency, milliseconds):
            hub.speaker.beep(frequency, milliseconds)

        def button_pressed(self):
            pressed = hub.buttons.pressed()
            if Button.CENTER in pressed:
                return "center"
            return None

    machine = PybricksMachine()
    machine.model_id = model_id
    machine.ports = kinds
    machine.port_order = port_order
    return machine


def main():  # pragma: no cover - runs only on a hub
    """Read stdin frames forever, answering each one."""

    import uselect
    import usys
    from pybricks.tools import StopWatch

    machine = build_machine()
    agent = HubAgent(machine)
    clock = StopWatch()
    poller = uselect.poll()
    poller.register(usys.stdin)
    buffer = ""

    while agent.running:
        for line in agent.poll(clock.time()):
            print(line)
        if not poller.poll(10):
            continue
        buffer += usys.stdin.read(1)
        if not buffer.endswith("\n"):
            if len(buffer) > MAX_FRAME_CHARS:
                buffer = ""
            continue
        line, buffer = buffer, ""
        for reply in agent.handle_line(line, clock.time()):
            print(reply)


if __name__ == "__main__":  # pragma: no cover - runs only on a hub
    main()
