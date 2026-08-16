"""FR-051: capabilities reflect the hub and what is plugged into it."""

from __future__ import annotations

import pytest
from cit_device_simulator import create_fake_lego_adapter
from cit_lego_pybricks import (
    HUB_MODELS,
    ROBOT_INVENTOR,
    SPIKE_ESSENTIAL,
    SPIKE_PRIME,
    PortKind,
    UnknownHubModel,
    capabilities_for,
    decode_ports,
    encode_ports,
    hub_model,
    parse_port_map,
    sensor_port_for,
)

DRIVING_BASE = {
    "A": PortKind.MOTOR,
    "B": PortKind.MOTOR,
    "C": PortKind.DISTANCE,
    "D": PortKind.EMPTY,
    "E": PortKind.EMPTY,
    "F": PortKind.EMPTY,
}


def test_the_three_version_one_hubs_are_supported() -> None:
    """FR-045 and FR-054."""

    assert set(HUB_MODELS) == {"spike-prime", "spike-essential", "robot-inventor"}
    assert SPIKE_PRIME.ports == ROBOT_INVENTOR.ports
    assert SPIKE_ESSENTIAL.ports == ("A", "B")


def test_robot_inventor_uses_the_same_pybricks_path_as_spike_prime() -> None:
    prime = capabilities_for(SPIKE_PRIME, DRIVING_BASE)
    inventor = capabilities_for(ROBOT_INVENTOR, DRIVING_BASE)

    assert prime == inventor


def test_one_motor_is_a_mechanism_and_two_are_a_drive_base() -> None:
    one = capabilities_for(SPIKE_PRIME, {**DRIVING_BASE, "B": PortKind.EMPTY})
    two = capabilities_for(SPIKE_PRIME, DRIVING_BASE)

    assert "motor.run" in one
    assert "drive.straight" not in one
    assert "drive.straight" in two


def test_a_hub_with_nothing_plugged_in_still_has_its_own_capabilities() -> None:
    bare = capabilities_for(SPIKE_PRIME, dict.fromkeys(SPIKE_PRIME.ports, PortKind.EMPTY))

    assert set(bare) == {
        "hub.battery",
        "hub.button",
        "hub.display",
        "hub.sound",
        "sensor.gyro",
        "sensor.imu",
    }


def test_each_sensor_brings_only_its_own_capability() -> None:
    ports = {**DRIVING_BASE, "D": PortKind.COLOR, "E": PortKind.FORCE}
    capabilities = capabilities_for(SPIKE_PRIME, ports)

    assert {"sensor.color", "sensor.reflection", "sensor.force"} <= set(capabilities)
    assert sensor_port_for(ports, "sensor.color") == "D"
    assert sensor_port_for(ports, "sensor.force") == "E"
    assert sensor_port_for(DRIVING_BASE, "sensor.force") is None


def test_the_lego_fake_advertises_what_a_real_driving_base_advertises() -> None:
    """The simulated hub and the real one must teach the same blocks."""

    fake = create_fake_lego_adapter()
    real = capabilities_for(SPIKE_PRIME, {**DRIVING_BASE, "D": PortKind.COLOR})

    assert tuple(sorted(fake.capabilities)) == real


def test_a_port_the_hub_does_not_have_is_a_configuration_error() -> None:
    with pytest.raises(ValueError, match="has no port"):
        parse_port_map(SPIKE_ESSENTIAL, {"C": "motor"})


def test_an_unknown_attachment_names_the_ones_that_exist() -> None:
    with pytest.raises(ValueError, match="expected one of"):
        parse_port_map(SPIKE_PRIME, {"A": "laser"})


def test_an_unknown_hub_model_names_the_supported_ones() -> None:
    with pytest.raises(UnknownHubModel, match="spike-prime"):
        hub_model("ev3")


def test_the_port_report_round_trips_within_one_frame_argument() -> None:
    encoded = encode_ports(SPIKE_PRIME, DRIVING_BASE)

    assert encoded == "mmd---"
    assert len(encoded) <= 24
    assert decode_ports(SPIKE_PRIME, encoded) == DRIVING_BASE


def test_a_hub_that_miscounts_its_ports_is_not_trusted() -> None:
    with pytest.raises(ValueError, match="reported"):
        decode_ports(SPIKE_PRIME, "mm")
    with pytest.raises(ValueError, match="unknown port code"):
        decode_ports(SPIKE_PRIME, "mmz---")
