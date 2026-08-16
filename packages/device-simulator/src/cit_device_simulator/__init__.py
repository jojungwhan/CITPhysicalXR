"""Device adapter contract and required Milestone 0 fake families."""

from .contract import DeviceAdapter
from .fakes import (
    FakeDeviceAdapter,
    create_fake_leap_adapter,
    create_fake_lego_adapter,
    create_fake_quest_adapter,
    create_fake_s1_adapter,
)

__all__ = [
    "DeviceAdapter",
    "FakeDeviceAdapter",
    "create_fake_leap_adapter",
    "create_fake_lego_adapter",
    "create_fake_quest_adapter",
    "create_fake_s1_adapter",
]
