from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cit_safety import DeviceLeaseConflict, InMemoryDeviceLeaseRegistry, LeaseMode

NOW = datetime(2026, 8, 16, 4, 0, 0, tzinfo=UTC)


def test_only_one_session_can_hold_a_device_write_lease() -> None:
    leases = InMemoryDeviceLeaseRegistry()

    first = leases.acquire(
        device_id="fake-s1-main",
        session_id="class-a",
        mode=LeaseMode.WRITE,
        now=NOW,
        ttl=timedelta(seconds=5),
    )

    with pytest.raises(DeviceLeaseConflict) as conflict:
        leases.acquire(
            device_id="fake-s1-main",
            session_id="class-b",
            mode=LeaseMode.WRITE,
            now=NOW,
            ttl=timedelta(seconds=5),
        )

    assert first.session_id == "class-a"
    assert conflict.value.device_id == "fake-s1-main"
    assert conflict.value.holder_session_id == "class-a"


def test_expired_write_lease_does_not_block_the_next_session() -> None:
    leases = InMemoryDeviceLeaseRegistry()
    leases.acquire(
        device_id="fake-s1-main",
        session_id="class-a",
        mode=LeaseMode.WRITE,
        now=NOW,
        ttl=timedelta(seconds=5),
    )

    replacement = leases.acquire(
        device_id="fake-s1-main",
        session_id="class-b",
        mode=LeaseMode.WRITE,
        now=NOW + timedelta(seconds=5),
        ttl=timedelta(seconds=5),
    )

    assert replacement.session_id == "class-b"
