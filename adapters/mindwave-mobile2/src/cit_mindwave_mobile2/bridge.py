"""Independent authenticated Fabric bridge for MindWave Mobile 2."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cit_integration_sdk import FabricAdapterClient, FabricConnectionConfiguration
from cit_protocol import HealthReport

from .backend import MindWaveBackend, MindWaveBackendError, MindWaveEvent
from .contract import (
    ATTENTION_CAPABILITY,
    BLINK_CAPABILITY,
    MEDITATION_CAPABILITY,
    SIGNAL_QUALITY_CAPABILITY,
    build_manifest,
    build_node,
)


@dataclass(frozen=True, slots=True)
class BridgeConfiguration:
    connection: FabricConnectionConfiguration
    host_id: str
    node_id: str
    activation_file: Path
    simulated: bool


class FabricMindWaveBridge:
    def __init__(self, configuration: BridgeConfiguration, *, backend: MindWaveBackend) -> None:
        self.configuration = configuration
        self._backend = backend
        self._last_error: str | None = None
        self._connected = False
        self._latest_signal_quality: float | None = None

    async def run(self) -> None:
        try:
            await self._backend.start()
            self._connected = True
            node = build_node(
                at=datetime.now(UTC),
                host_id=self.configuration.host_id,
                site_id=self.configuration.connection.site_id,
                room_id=self.configuration.connection.room_id,
                node_id=self.configuration.node_id,
                simulated=self.configuration.simulated,
            )
            client = FabricAdapterClient(
                self.configuration.connection,
                manifest=build_manifest(),
                nodes=[node],
            )
            async with client.connected():
                tasks = (
                    asyncio.create_task(self._receive(client), name="mindwave-fabric-receive"),
                    asyncio.create_task(self._heartbeat(client), name="mindwave-heartbeat"),
                    asyncio.create_task(self._events(client), name="mindwave-events"),
                    asyncio.create_task(self._activation_watch(), name="mindwave-activation-watch"),
                )
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    task.result()
        finally:
            self._connected = False
            await self._backend.close()

    async def _receive(self, client: FabricAdapterClient) -> None:
        while True:
            frame = await client.receive_json()
            frame_type = frame.get("frameType")
            if frame_type == "adapter.ack":
                continue
            if frame_type == "adapter.stop":
                if frame.get("nodeId") != self.configuration.node_id:
                    raise RuntimeError("Fabric stop frame targeted a different MindWave node")
                return
            if frame_type == "adapter.command":
                raise RuntimeError("MindWave is publish-only and cannot receive commands")
            raise RuntimeError(f"Unexpected Fabric adapter frame {frame_type!r}")

    async def _events(self, client: FabricAdapterClient) -> None:
        while True:
            try:
                event = await self._backend.next_event()
                self._last_error = None
            except (MindWaveBackendError, OSError) as error:
                self._last_error = str(error)[:500]
                raise
            if event.kind == "status":
                self._connected = bool(event.connected)
                self._last_error = None if event.connected else event.message
                continue
            if not self.configuration.activation_file.is_file():
                continue
            await self._publish_event(client, event)

    async def _publish_event(
        self,
        client: FabricAdapterClient,
        event: MindWaveEvent,
    ) -> None:
        if event.kind == "blink" and event.blink_strength is not None:
            await client.publish_event(
                topic=BLINK_CAPABILITY,
                source_node_id=self.configuration.node_id,
                payload={"strength": event.blink_strength, "vendor": "NeuroSky"},
                confidence=1.0,
                ttl_ms=500,
                data_classification="biosignal_derived",
            )
            return
        if (
            event.kind != "reading"
            or event.attention is None
            or event.meditation is None
            or event.signal_quality is None
        ):
            return
        self._latest_signal_quality = event.signal_quality
        confidence = max(0.0, min(1.0, event.signal_quality / 100.0))
        common = {
            "signalQualityPercent": event.signal_quality,
            "vendor": "NeuroSky",
            "vendorDerived": True,
            "medicalMeasurement": False,
        }
        for topic, value in (
            (ATTENTION_CAPABILITY, event.attention),
            (MEDITATION_CAPABILITY, event.meditation),
            (SIGNAL_QUALITY_CAPABILITY, event.signal_quality),
        ):
            await client.publish_event(
                topic=topic,
                source_node_id=self.configuration.node_id,
                payload={**common, "value": value},
                confidence=confidence,
                ttl_ms=1_500,
                data_classification="biosignal_derived",
            )

    async def _heartbeat(self, client: FabricAdapterClient) -> None:
        while True:
            await asyncio.sleep(5)
            healthy = self._connected and self._last_error is None
            await client.publish_heartbeat(
                [
                    HealthReport.model_validate(
                        {
                            "schemaVersion": "1.0",
                            "nodeId": self.configuration.node_id,
                            "reportedAt": datetime.now(UTC),
                            "connectionState": "connected" if healthy else "degraded",
                            "healthState": "healthy" if healthy else "degraded",
                            "message": self._last_error,
                            "metrics": {
                                "semanticPublicationActive": (
                                    self.configuration.activation_file.is_file()
                                ),
                                "rawEegPublished": False,
                                "signalQualityPercent": self._latest_signal_quality,
                            },
                        }
                    )
                ]
            )

    async def _activation_watch(self) -> None:
        while not self.configuration.activation_file.is_file():  # noqa: ASYNC110
            await asyncio.sleep(0.1)
        while self.configuration.activation_file.is_file():  # noqa: ASYNC110
            await asyncio.sleep(0.1)
