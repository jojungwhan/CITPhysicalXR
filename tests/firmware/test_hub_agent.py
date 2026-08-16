"""The hub agent, exercised on CPython with a machine that is not a hub.

The agent is written for MicroPython on a LEGO hub, and it will never be
imported by the runtime. It is tested here because the alternative -- a firmware
file whose watchdog and parser are only ever checked by plugging in a robot --
is how a stop that does not stop ships.

The hardware half (:func:`build_machine`) is not covered: it needs a hub.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from cit_lego_pybricks import Frame, Operation, decode

FIRMWARE = Path(__file__).resolve().parents[2] / "firmware/lego-hub-agent/hub_agent.py"


def load_agent_module() -> ModuleType:
    specification = importlib.util.spec_from_file_location("cit_hub_agent", FIRMWARE)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


agent_module = load_agent_module()


class FakeMachine:
    """The hardware the agent would drive, recorded instead of driven."""

    def __init__(self, *, ports: dict[str, str] | None = None) -> None:
        self.model_id = "spike-prime"
        self.port_order = ("A", "B", "C", "D", "E", "F")
        self.ports = ports or {
            "A": "motor",
            "B": "motor",
            "C": "distance",
            "D": "empty",
            "E": "empty",
            "F": "empty",
        }
        self.calls: list[tuple[Any, ...]] = []
        self.stops = 0
        self.button: str | None = None
        self.readings = {"distance": 300, "battery": 88}

    def battery(self) -> int:
        return 88

    def has_drive_base(self) -> bool:
        return sum(1 for kind in self.ports.values() if kind == "motor") >= 2

    def motor_run(self, port: str, speed: int, milliseconds: int) -> None:
        self.calls.append(("motor_run", port, speed, milliseconds))

    def motor_run_angle(self, port: str, speed: int, angle: int) -> None:
        self.calls.append(("motor_run_angle", port, speed, angle))

    def motor_run_target(self, port: str, speed: int, angle: int) -> None:
        self.calls.append(("motor_run_target", port, speed, angle))

    def motor_stop(self, port: str) -> None:
        self.calls.append(("motor_stop", port))

    def drive(self, speed: int, turn: int, milliseconds: int) -> None:
        self.calls.append(("drive", speed, turn, milliseconds))

    def drive_straight(self, millimetres: int) -> None:
        self.calls.append(("drive_straight", millimetres))

    def turn(self, angle: int) -> None:
        self.calls.append(("turn", angle))

    def stop_all(self) -> None:
        self.stops += 1
        self.calls.append(("stop_all",))

    def sensor_read(self, port: str, kind: str) -> int | None:
        if port == "HUB":
            return self.readings.get(kind)
        if port not in self.ports or self.ports[port] == "empty":
            return None
        return self.readings.get(kind)

    def display(self, text: str) -> None:
        self.calls.append(("display", text))

    def sound(self, frequency: int, milliseconds: int) -> None:
        self.calls.append(("sound", frequency, milliseconds))

    def button_pressed(self) -> str | None:
        return self.button


def make_agent(**kwargs: Any) -> tuple[Any, FakeMachine]:
    machine = FakeMachine(**kwargs)
    return agent_module.HubAgent(machine), machine


def host_line(sequence: int, operation: Operation, arguments: tuple[str, ...]) -> str:
    return Frame(sequence=sequence, operation=operation, arguments=arguments).encode_line()


# ------------------------------------------------------------ the two codecs


def test_the_hub_decodes_exactly_what_the_runtime_encodes() -> None:
    cases = [
        (1, Operation.HELLO, ("1", "cit-runtime")),
        (2, Operation.MOTOR_RUN, ("A", "-40", "1500")),
        (3, Operation.SENSOR_READ, ("C", "distance")),
        (4, Operation.DISPLAY, ("go")),
        (9999, Operation.STOP_ALL, ("watchdog",)),
    ]

    for sequence, operation, arguments in cases:
        argument_tuple = arguments if isinstance(arguments, tuple) else (arguments,)
        line = host_line(sequence, operation, argument_tuple)
        assert agent_module.decode_frame(line) == (
            sequence,
            operation.value,
            list(argument_tuple),
        )


def test_the_runtime_decodes_exactly_what_the_hub_encodes() -> None:
    line = agent_module.encode_frame(12, "TELEMETRY", ["distance", "300"])

    frame = decode(line)

    assert frame.sequence == 12
    assert frame.operation is Operation.TELEMETRY
    assert frame.arguments == ("distance", "300")


def test_both_sides_agree_on_every_operation_and_arity() -> None:
    from cit_lego_pybricks import ARITY as host_arity

    assert set(agent_module.ARITY) == {operation.value for operation in Operation}
    assert {name: tuple(value) for name, value in agent_module.ARITY.items()} == {
        operation.value: arity for operation, arity in host_arity.items()
    }


def test_both_sides_agree_on_the_frame_bounds() -> None:
    from cit_lego_pybricks import MAX_ARGUMENTS, MAX_FRAME_CHARS, PROTOCOL_TAG

    assert agent_module.PROTOCOL_TAG == PROTOCOL_TAG
    assert agent_module.MAX_FRAME_CHARS == MAX_FRAME_CHARS
    assert agent_module.MAX_ARGUMENTS == MAX_ARGUMENTS


# ------------------------------------------------------------------ behaviour


def test_the_hub_reports_its_model_battery_and_ports_on_hello() -> None:
    agent, _ = make_agent()

    replies = agent.handle_line(host_line(1, Operation.HELLO, ("1", "cit-runtime")), 0)

    frame = decode(replies[0])
    assert frame.operation is Operation.HELLO
    assert frame.arguments == ("1", "spike-prime", "88", "mmd---")


def test_a_motor_command_is_acknowledged_and_performed() -> None:
    agent, machine = make_agent()

    replies = agent.handle_line(host_line(7, Operation.MOTOR_RUN, ("A", "40", "1000")), 0)

    assert decode(replies[0]).operation is Operation.ACK
    assert decode(replies[0]).arguments == ("7",)
    assert machine.calls == [("motor_run", "A", 400, 1000)]


def test_a_malformed_frame_is_answered_with_an_error_not_an_action() -> None:
    agent, machine = make_agent()

    replies = agent.handle_line("C1|1|LAUNCH_ROCKET|now\n", 0)

    frame = decode(replies[0])
    assert frame.operation is Operation.ERROR
    assert frame.arguments == ("0", "BAD_FRAME")
    assert machine.calls == []


def test_an_empty_port_is_refused_by_the_hub_as_well() -> None:
    agent, machine = make_agent()

    replies = agent.handle_line(host_line(2, Operation.MOTOR_RUN, ("D", "40", "500")), 0)

    assert decode(replies[0]).arguments == ("2", "BAD_PORT")
    assert machine.calls == []


def test_a_hub_with_one_motor_refuses_to_drive() -> None:
    agent, machine = make_agent(
        ports={"A": "motor", "B": "empty", "C": "empty", "D": "empty", "E": "empty", "F": "empty"}
    )

    replies = agent.handle_line(host_line(3, Operation.DRIVE, ("40", "0", "500")), 0)

    assert decode(replies[0]).arguments == ("3", "UNSUPPORTED")
    assert machine.calls == []


def test_the_hub_clamps_what_the_runtime_sends() -> None:
    agent, machine = make_agent()

    agent.handle_line(host_line(4, Operation.MOTOR_RUN, ("A", "400", "99999")), 0)

    assert machine.calls == [("motor_run", "A", 1000, 5000)]


def test_a_sensor_read_answers_with_a_reading() -> None:
    agent, _ = make_agent()

    replies = agent.handle_line(host_line(5, Operation.SENSOR_READ, ("C", "distance")), 0)

    assert [decode(reply).operation for reply in replies] == [
        Operation.ACK,
        Operation.TELEMETRY,
    ]
    assert decode(replies[1]).arguments == ("distance", "300")


# --------------------------------------------------------------------- safety


def test_the_hub_stops_itself_when_the_runtime_goes_quiet() -> None:
    """FR-049 and FR-053: losing the link must not mean a robot that keeps going."""

    agent, machine = make_agent()
    agent.handle_line(host_line(1, Operation.MOTOR_RUN, ("A", "40", "2000")), 0)

    quiet = agent.poll(400)
    expired = agent.poll(600)

    assert quiet == []
    assert machine.stops == 1
    assert decode(expired[0]).arguments == ("0", "WATCHDOG")
    assert agent.motors_running is False


def test_the_watchdog_does_not_fire_while_the_runtime_keeps_talking() -> None:
    agent, machine = make_agent()
    agent.handle_line(host_line(1, Operation.MOTOR_RUN, ("A", "40", "2000")), 0)

    agent.handle_line(host_line(2, Operation.HEARTBEAT, ("200",)), 300)
    outgoing = agent.poll(600)

    assert outgoing == []
    assert machine.stops == 0


def test_the_button_stops_the_hub_without_being_asked() -> None:
    agent, machine = make_agent()
    agent.handle_line(host_line(1, Operation.MOTOR_RUN, ("A", "40", "2000")), 0)
    machine.button = "center"

    outgoing = agent.poll(100)

    assert machine.stops == 1
    assert decode(outgoing[0]).arguments == ("button", "center")


def test_a_subscription_reports_on_its_own_interval() -> None:
    agent, _ = make_agent()
    agent.handle_line(host_line(1, Operation.SENSOR_SUBSCRIBE, ("C", "distance", "100")), 0)

    first = agent.poll(150)
    immediately_after = agent.poll(180)

    assert decode(first[0]).arguments == ("distance", "300")
    assert immediately_after == []


def test_the_hub_agent_has_no_way_to_evaluate_what_it_is_sent() -> None:
    source = FIRMWARE.read_text(encoding="utf-8")

    for forbidden in ("eval(", "exec(", "__import__(", "compile("):
        assert forbidden not in source


@pytest.mark.parametrize(
    "line",
    ["", "C2|1|HEARTBEAT|200", "C1|1|MOTOR_RUN|A", "C1|9999999|HEARTBEAT|200"],
)
def test_the_hub_never_acts_on_a_frame_it_could_not_parse(line: str) -> None:
    agent, machine = make_agent()

    replies = agent.handle_line(line, 0)

    assert decode(replies[0]).arguments[1] == "BAD_FRAME"
    assert machine.calls == []
