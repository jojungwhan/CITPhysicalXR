from __future__ import annotations

from datetime import UTC, datetime

import pytest
from cit_mindwave_mobile2.backend import (
    Brain2DevicesApiMindWaveBackend,
    SimulatedMindWaveBackend,
)
from cit_mindwave_mobile2.contract import (
    ATTENTION_CAPABILITY,
    BRAIN2DEVICES_REVISION,
    build_manifest,
    build_node,
)


def test_mindwave_contract_is_publish_only_and_explicitly_vendor_derived() -> None:
    manifest = build_manifest()
    node = build_node(
        at=datetime.now(UTC),
        host_id="host-a",
        site_id="site-a",
        room_id="room-a",
        node_id="mindwave-a",
        simulated=False,
    )

    assert manifest.consumedCapabilities == []
    assert ATTENTION_CAPABILITY in {item.name for item in manifest.publishedCapabilities}
    metadata = node.metadata.model_dump()
    assert metadata["brain2devicesRevision"] == BRAIN2DEVICES_REVISION
    assert metadata["vendorDerivedSignals"] is True
    assert metadata["medicalMeasurement"] is False
    assert metadata["rawEegPublished"] is False
    assert node.dataClassifications == ["biosignal_derived"]


@pytest.mark.asyncio
async def test_mindwave_simulator_emits_only_semantic_readings() -> None:
    backend = SimulatedMindWaveBackend(sample_interval_seconds=0)
    await backend.start()

    event = await backend.next_event()

    assert event.kind == "reading"
    assert event.attention is not None
    assert event.meditation is not None
    assert event.signal_quality == 96.0
    assert not hasattr(event, "raw_eeg")


@pytest.mark.asyncio
async def test_latest_brain2devices_api_blink_is_emitted_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Brain2DevicesApiMindWaveBackend(sample_interval_seconds=0.2)
    states = iter(
        [
            {
                "headset": {
                    "connection": "connected",
                    "attention": 40,
                    "meditation": 60,
                    "signal_quality": 95.0,
                    "blink": {"count": 2, "strength": 30},
                }
            },
            {
                "headset": {
                    "connection": "connected",
                    "attention": 41,
                    "meditation": 61,
                    "signal_quality": 96.0,
                    "blink": {"count": 3, "strength": 88},
                }
            },
            {
                "headset": {
                    "connection": "connected",
                    "attention": 42,
                    "meditation": 62,
                    "signal_quality": 97.0,
                    "blink": {"count": 3, "strength": 88},
                }
            },
        ]
    )
    monkeypatch.setattr(backend, "_state", lambda: next(states))

    await backend.start()
    blink = await backend.next_event()
    reading = await backend.next_event()

    assert blink.kind == "blink"
    assert blink.blink_strength == 88
    assert reading.kind == "reading"
    assert reading.attention == 42
