"""Python 3.8-compatible JSON-lines worker for the existing vendor repository.

This file is executed by the owner-selected external interpreter, not imported
by the CIT runtime.  Keep its syntax compatible with Python 3.8.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import deque
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

PROTOCOL_STDOUT = sys.stdout


def _write(value: Any) -> None:
    PROTOCOL_STDOUT.write(json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n")
    PROTOCOL_STDOUT.flush()


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _bounded(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def _install_repository(path: str) -> Path:
    repository = Path(path).resolve()
    package = repository / "robomaster_gesture" / "__init__.py"
    if not package.is_file():
        raise RuntimeError(f"upstream package was not found at {repository}")
    sys.path.insert(0, str(repository))
    return repository


def _robot(args: argparse.Namespace) -> int:
    _install_repository(args.repository)
    with redirect_stdout(sys.stderr):
        from robomaster_gesture.models import VelocityCommand  # type: ignore[import-not-found]
        from robomaster_gesture.robot_adapter import (  # type: ignore[import-not-found]
            CommandPump,
            CommandPumpConfig,
            DjiRobotAdapter,
            DryRunRobot,
            S1AppKeyboardAdapter,
        )

    if args.robot_mode == "dry-run":
        robot = DryRunRobot()
    elif args.robot_mode == "s1-app":
        robot = S1AppKeyboardAdapter(watchdog_s=0.25)
    else:
        robot = DjiRobotAdapter(
            conn_type=args.connection,
            proto_type=args.protocol,
            robot_ip=args.robot_ip,
            local_ip=args.local_ip,
            serial_number=args.serial_number,
        )

    pump: Any = None
    connected = False
    seen: set[str] = set()
    seen_order: deque[str] = deque()
    try:
        for raw in sys.stdin:
            request_id = "unknown"
            try:
                request: dict[str, Any] = json.loads(raw)
                if not isinstance(request, dict):
                    raise ValueError("request must be an object")
                request_id = str(request.get("requestId", ""))
                if not request_id or len(request_id) > 128:
                    raise ValueError("requestId is required")
                operation = request.get("operation")
                if operation == "connect":
                    if not connected:
                        with redirect_stdout(sys.stderr):
                            robot.connect()
                            pump = CommandPump(
                                robot,
                                CommandPumpConfig(
                                    rate_hz=15.0,
                                    stale_after_s=0.20,
                                    moving_keepalive_s=0.15,
                                    robot_timeout_s=0.35,
                                ),
                            )
                            pump.start()
                        connected = True
                    _write({"requestId": request_id, "ok": True, "connected": True})
                    continue
                if not connected or pump is None:
                    raise RuntimeError("robot worker is not connected")
                if operation == "set_velocity":
                    key = str(request.get("idempotencyKey", ""))
                    if not key:
                        raise ValueError("idempotencyKey is required")
                    if key in seen:
                        _write({"requestId": request_id, "ok": True, "duplicate": True})
                        continue
                    forward = _bounded(
                        _finite_number(request.get("forwardMetersPerSecond"), "forward"),
                        args.max_speed,
                    )
                    right = _bounded(
                        _finite_number(request.get("rightMetersPerSecond"), "right"),
                        args.max_speed,
                    )
                    clockwise_radians = _bounded(
                        _finite_number(request.get("clockwiseRadiansPerSecond"), "clockwise"),
                        math.radians(args.max_yaw),
                    )
                    command = VelocityCommand(
                        forward_m_s=forward,
                        right_m_s=right,
                        clockwise_deg_s=math.degrees(clockwise_radians),
                    )
                    with redirect_stdout(sys.stderr):
                        pump.submit(command)
                    seen.add(key)
                    seen_order.append(key)
                    while len(seen_order) > 4096:
                        seen.discard(seen_order.popleft())
                    _write(
                        {
                            "requestId": request_id,
                            "ok": True,
                            "duplicate": False,
                            "bounded": {
                                "forwardMetersPerSecond": forward,
                                "rightMetersPerSecond": right,
                                "clockwiseRadiansPerSecond": clockwise_radians,
                            },
                        }
                    )
                elif operation == "stop":
                    with redirect_stdout(sys.stderr):
                        pump.halt()
                        robot.stop()
                    _write({"requestId": request_id, "ok": True, "stopped": True})
                elif operation == "shutdown":
                    with redirect_stdout(sys.stderr):
                        pump.halt()
                        robot.stop()
                    _write({"requestId": request_id, "ok": True, "stopped": True})
                    break
                else:
                    raise ValueError(f"unsupported operation {operation!r}")
            except Exception as exc:
                _write(
                    {
                        "requestId": request_id,
                        "ok": False,
                        "errorType": type(exc).__name__,
                        "message": str(exc)[:500],
                    }
                )
    finally:
        with redirect_stdout(sys.stderr):
            if pump is not None:
                pump.close()
            try:
                robot.stop()
            except Exception:
                pass
            robot.close()
    return 0


def _decision_payload(decision: Any, sequence: int) -> dict[str, Any]:
    command = decision.command
    hand_present = decision.hand is not None
    return {
        "type": "gesture",
        "sequence": sequence,
        "monotonicNanoseconds": int(time.monotonic() * 1000000000),
        "state": decision.state,
        "reason": decision.reason,
        "confidence": 1.0 if hand_present else 0.0,
        "forwardMetersPerSecond": float(command.forward_m_s),
        "rightMetersPerSecond": float(command.right_m_s),
        "clockwiseRadiansPerSecond": math.radians(float(command.clockwise_deg_s)),
        "tracking": hand_present,
    }


def _leap(args: argparse.Namespace) -> int:
    _install_repository(args.repository)
    with redirect_stdout(sys.stderr):
        from robomaster_gesture.gesture import (  # type: ignore[import-not-found]
            GestureConfig,
            GestureController,
        )
        from robomaster_gesture.leap_source import LeapSource  # type: ignore[import-not-found]

    source = LeapSource(Path(args.bridge_dll))
    controller = GestureController(
        GestureConfig(
            preferred_hand=args.hand,
            max_translation_m_s=args.max_speed,
            max_yaw_deg_s=args.max_yaw,
            strafe_sign=-1.0 if args.invert_strafe else 1.0,
            yaw_sign=-1.0 if args.invert_yaw else 1.0,
        )
    )
    sequence = 0
    last_frame_at = time.monotonic()
    last_emit_at = 0.0
    last_signature: tuple[Any, ...] | None = None
    was_moving = False
    try:
        with redirect_stdout(sys.stderr):
            source.open()
        _write(
            {
                "type": "ready",
                "serviceConnected": source.service_connected,
                "devicePresent": source.device_present,
            }
        )
        while not Path(args.stop_file).exists():
            now = time.monotonic()
            with redirect_stdout(sys.stderr):
                frame = source.poll(timeout_ms=50)
            if frame is None:
                if now - last_frame_at <= 0.20:
                    continue
                decision = controller.on_tracking_timeout(now)
            else:
                last_frame_at = frame.arrival_time_s
                decision = controller.update(frame)
            command = decision.command
            moving = not command.is_stopped()
            signature = (
                decision.state,
                decision.reason,
                round(command.forward_m_s, 4),
                round(command.right_m_s, 4),
                round(command.clockwise_deg_s, 3),
            )
            urgent_stop = was_moving and not moving
            due = now - last_emit_at >= (1.0 / 15.0)
            if urgent_stop or (due and (moving or signature != last_signature)):
                sequence += 1
                _write(_decision_payload(decision, sequence))
                last_emit_at = now
                last_signature = signature
            was_moving = moving
        return 0
    finally:
        with redirect_stdout(sys.stderr):
            source.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("robot", "leap"))
    parser.add_argument("--repository", required=True)
    parser.add_argument("--robot-mode", choices=("dry-run", "sdk", "s1-app"), default="dry-run")
    parser.add_argument("--connection", choices=("ap", "sta", "rndis"), default="sta")
    parser.add_argument("--protocol", choices=("tcp", "udp"), default="tcp")
    parser.add_argument("--robot-ip")
    parser.add_argument("--local-ip")
    parser.add_argument("--serial-number")
    parser.add_argument("--bridge-dll")
    parser.add_argument("--stop-file")
    parser.add_argument("--hand", choices=("left", "right", "any"), default="right")
    parser.add_argument("--max-speed", type=float, default=0.35)
    parser.add_argument("--max-yaw", type=float, default=35.0)
    parser.add_argument("--invert-strafe", action="store_true")
    parser.add_argument("--invert-yaw", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not 0.05 <= args.max_speed <= 0.35:
        raise SystemExit("--max-speed must be between 0.05 and 0.35")
    if not 5.0 <= args.max_yaw <= 35.0:
        raise SystemExit("--max-yaw must be between 5 and 35")
    if args.kind == "leap":
        if not args.bridge_dll or not args.stop_file:
            raise SystemExit("leap mode requires --bridge-dll and --stop-file")
        return _leap(args)
    return _robot(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        _write(
            {
                "type": "fatal",
                "errorType": type(error).__name__,
                "message": str(error)[:500],
            }
        )
        sys.exit(1)
