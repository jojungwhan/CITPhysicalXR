"""Process-independent Leap and RoboMaster Fabric bridges.

The preserved compatibility bridge remains available, but production launchers
use these classes so loss of Leap tracking cannot tear down the robot adapter
and a robot transport failure cannot stop gesture publication.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cit_integration_sdk import FabricAdapterClient, FabricConnectionConfiguration
from cit_protocol import FabricResolvedCommand, HealthReport

from .backend import (
    GestureSignal,
    RobotBackend,
    VendorLeapProcess,
    VendorProcessError,
    demo_gesture_signals,
    demo_hand_preview_signal,
    gesture_event_payload,
)
from .contract import (
    FLIGHT_SEQUENCE_INTENT_CAPABILITY,
    GESTURE_CAPABILITY,
    ROBOT_TELEMETRY_CAPABILITY,
    ROBOT_VELOCITY_CAPABILITY,
    build_leap_manifest,
    build_leap_node,
    build_robot_manifest,
    build_robot_node,
)
from .media import RoboMasterMediaPublisher
from .robot_commands import RobotCommandHandler


@dataclass(frozen=True, slots=True)
class LeapBridgeConfiguration:
    connection: FabricConnectionConfiguration
    host_id: str
    node_id: str
    activation_file: Path
    input_mode: str
    preferred_hand: str


@dataclass(frozen=True, slots=True)
class RobotBridgeConfiguration:
    connection: FabricConnectionConfiguration
    host_id: str
    node_id: str
    activation_file: Path
    robot_mode: str
    media_publisher: RoboMasterMediaPublisher | None = None


class LeapFlightSequenceIntentProjector:
    """Project one deliberate pinch-engage edge into one semantic intent."""

    def __init__(self) -> None:
        self._previous_state: str | None = None

    def observe(self, signal: GestureSignal) -> dict[str, object] | None:
        previous = self._previous_state
        self._previous_state = signal.state
        if (
            signal.tracking
            and signal.confidence >= 0.8
            and signal.state == "DRIVING"
            and previous != "DRIVING"
        ):
            return {
                "intent": "start",
                "inputModality": "leap_pinch",
                "gestureState": signal.state,
                "vendorSequence": signal.sequence,
            }
        return None


class FabricLeapBridge:
    def __init__(
        self,
        configuration: LeapBridgeConfiguration,
        *,
        leap: VendorLeapProcess | None,
    ) -> None:
        if configuration.input_mode not in {"demo", "leap"}:
            raise ValueError("input_mode must be 'demo' or 'leap'")
        if configuration.input_mode == "leap" and leap is None:
            raise ValueError("Physical Leap input requires a Leap worker")
        self.configuration = configuration
        self._leap = leap
        self._last_error: str | None = None
        self._sequence_projector = LeapFlightSequenceIntentProjector()

    async def run(self) -> None:
        node = build_leap_node(
            at=datetime.now(UTC),
            host_id=self.configuration.host_id,
            site_id=self.configuration.connection.site_id,
            room_id=self.configuration.connection.room_id,
            node_id=self.configuration.node_id,
            simulated=self.configuration.input_mode == "demo",
            preferred_hand=self.configuration.preferred_hand,
        )
        client = FabricAdapterClient(
            self.configuration.connection,
            manifest=build_leap_manifest(),
            nodes=[node],
        )
        try:
            async with client.connected():
                tasks = (
                    asyncio.create_task(self._receive(client), name="leap-fabric-receive"),
                    asyncio.create_task(self._heartbeat(client), name="leap-heartbeat"),
                    asyncio.create_task(self._publish(client), name="leap-input"),
                )
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    task.result()
        finally:
            if self._leap is not None:
                await self._leap.close()

    async def _receive(self, client: FabricAdapterClient) -> None:
        while True:
            frame = await client.receive_json()
            frame_type = frame.get("frameType")
            if frame_type == "adapter.ack":
                continue
            if frame_type == "adapter.stop":
                if frame.get("nodeId") != self.configuration.node_id:
                    raise RuntimeError("Fabric stop frame targeted a different Leap node")
                return
            if frame_type == "adapter.command":
                raise RuntimeError("Leap Motion is publish-only")
            raise RuntimeError(f"Unexpected Fabric adapter frame {frame_type!r}")

    async def _publish(self, client: FabricAdapterClient) -> None:
        if self.configuration.input_mode == "demo":
            while not self.configuration.activation_file.is_file():  # noqa: ASYNC110
                await asyncio.sleep(0.1)
            signals = demo_gesture_signals()
            for signal in signals:
                if not self.configuration.activation_file.is_file():
                    return
                await self._publish_gesture(client, signal)
                await asyncio.sleep(0.25)
            sequence = signals[-1].sequence + 1
            while self.configuration.activation_file.is_file():
                await self._publish_gesture(client, demo_hand_preview_signal(sequence))
                sequence += 1
                await asyncio.sleep(1.0)
            return
        leap = self._leap
        if leap is None:
            raise RuntimeError("Leap worker is unavailable")
        try:
            async for signal in leap.events():
                await self._publish_gesture(client, signal)
        except VendorProcessError as error:
            self._last_error = str(error)[:500]
            raise

    async def _publish_gesture(
        self,
        client: FabricAdapterClient,
        signal: GestureSignal,
    ) -> None:
        await client.publish_event(
            topic=GESTURE_CAPABILITY,
            source_node_id=self.configuration.node_id,
            confidence=signal.confidence,
            ttl_ms=250,
            payload=gesture_event_payload(signal),
        )
        intent = self._sequence_projector.observe(signal)
        if intent is not None:
            await client.publish_event(
                topic=FLIGHT_SEQUENCE_INTENT_CAPABILITY,
                source_node_id=self.configuration.node_id,
                confidence=signal.confidence,
                ttl_ms=2_000,
                payload=intent,
            )

    async def _heartbeat(self, client: FabricAdapterClient) -> None:
        while True:
            await asyncio.sleep(5)
            healthy = self._last_error is None
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
                                "trackingActive": self.configuration.input_mode == "leap",
                                "lessonActive": self.configuration.activation_file.is_file(),
                                "semanticEventsOnly": True,
                            },
                        }
                    )
                ]
            )


class FabricRoboMasterBridge:
    def __init__(
        self,
        configuration: RobotBridgeConfiguration,
        *,
        robot: RobotBackend,
    ) -> None:
        self.configuration = configuration
        self._robot = robot
        self._handler = RobotCommandHandler(robot, robot_node_id=configuration.node_id)
        self._last_error: str | None = None

    async def run(self) -> None:
        await self._robot.start()
        try:
            node = build_robot_node(
                at=datetime.now(UTC),
                host_id=self.configuration.host_id,
                site_id=self.configuration.connection.site_id,
                room_id=self.configuration.connection.room_id,
                node_id=self.configuration.node_id,
                simulated=self.configuration.robot_mode == "dry-run",
                robot_mode=self.configuration.robot_mode,
            )
            client = FabricAdapterClient(
                self.configuration.connection,
                manifest=build_robot_manifest(),
                nodes=[node],
            )
            async with client.connected():
                tasks = (
                    asyncio.create_task(self._receive(client), name="robot-fabric-receive"),
                    asyncio.create_task(self._heartbeat(client), name="robot-heartbeat"),
                    asyncio.create_task(self._activation_watch(), name="robot-activation-watch"),
                    *(
                        (
                            asyncio.create_task(
                                self.configuration.media_publisher.run(),
                                name="robomaster-media-publisher",
                            ),
                        )
                        if self.configuration.media_publisher is not None
                        else ()
                    ),
                )
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    task.result()
        finally:
            await self._robot.stop(reason="fabric_bridge_shutdown")
            await self._robot.close()

    async def _receive(self, client: FabricAdapterClient) -> None:
        while True:
            frame = await client.receive_json()
            frame_type = frame.get("frameType")
            if frame_type == "adapter.ack":
                continue
            if frame_type == "adapter.stop":
                if frame.get("nodeId") != self.configuration.node_id:
                    raise RuntimeError("Fabric stop frame targeted a different RoboMaster node")
                await self._robot.stop(reason=str(frame.get("reason", "fabric_stop")))
                continue
            if frame_type != "adapter.command":
                raise RuntimeError(f"Unexpected Fabric adapter frame {frame_type!r}")
            command = FabricResolvedCommand.model_validate(frame.get("command"))
            await self._handle_command(client, command)

    async def _handle_command(
        self,
        client: FabricAdapterClient,
        command: FabricResolvedCommand,
    ) -> None:
        if self._handler.has_seen(str(command.commandId)):
            return
        try:
            self._handler.validate(command)
        except ValueError as error:
            self._last_error = str(error)[:500]
            await client.publish_lifecycle(
                command,
                "REJECTED",
                code="ADAPTER_PARAMETER_REJECTED",
                message=self._last_error,
            )
            return
        try:
            await client.publish_lifecycle(command, "ACCEPTED")
            await client.publish_lifecycle(command, "RUNNING")
            execution = await self._handler.execute(command)
            self._last_error = None
            await client.publish_lifecycle(
                command,
                "SUCCEEDED",
                details=dict(execution.details),
            )
            if command.action == ROBOT_VELOCITY_CAPABILITY:
                await client.publish_event(
                    topic=ROBOT_TELEMETRY_CAPABILITY,
                    source_node_id=self.configuration.node_id,
                    correlation_id=command.correlationId,
                    causation_id=command.commandId,
                    payload=dict(execution.details),
                )
        except (VendorProcessError, OSError) as error:
            self._last_error = str(error)[:500]
            await self._robot.stop(reason="vendor_process_failure")
            await client.publish_lifecycle(
                command,
                "FAILED",
                code="VENDOR_PROCESS_FAILED",
                message=self._last_error,
            )

    async def _heartbeat(self, client: FabricAdapterClient) -> None:
        while True:
            await asyncio.sleep(5)
            healthy = self._last_error is None
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
                                "lessonActive": self.configuration.activation_file.is_file(),
                                "localWatchdogMilliseconds": 200,
                                "cameraFramesPublished": (
                                    self.configuration.media_publisher.frames_published
                                    if self.configuration.media_publisher is not None
                                    else 0
                                ),
                                "cameraError": (
                                    self.configuration.media_publisher.last_error
                                    if self.configuration.media_publisher is not None
                                    else None
                                ),
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
