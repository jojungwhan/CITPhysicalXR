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


def test_a_session_may_renew_its_own_write_lease() -> None:
    """Every command takes a lease, so the holder must be able to re-take it."""

    leases = InMemoryDeviceLeaseRegistry()
    first = leases.acquire(
        device_id="fake-s1-main",
        session_id="class-a",
        mode=LeaseMode.WRITE,
        now=NOW,
        ttl=timedelta(seconds=5),
    )

    renewed = leases.acquire(
        device_id="fake-s1-main",
        session_id="class-a",
        mode=LeaseMode.WRITE,
        now=NOW + timedelta(seconds=1),
        ttl=timedelta(seconds=5),
    )

    assert renewed.session_id == "class-a"
    assert renewed.lease_id != first.lease_id
    assert renewed.expires_at > first.expires_at

    # Renewal must not have quietly opened the device to anyone else.
    with pytest.raises(DeviceLeaseConflict):
        leases.acquire(
            device_id="fake-s1-main",
            session_id="class-b",
            mode=LeaseMode.WRITE,
            now=NOW + timedelta(seconds=2),
            ttl=timedelta(seconds=5),
        )


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
