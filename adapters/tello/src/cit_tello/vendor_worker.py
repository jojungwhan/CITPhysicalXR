"""JSON-lines worker importing only Brain2Devices' Tello implementation."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--ip-address")
    return parser


def _response(request_id: object, *, ok: bool, **values: object) -> None:
    print(
        json.dumps({"requestId": request_id, "ok": ok, **values}, separators=(",", ":")),
        flush=True,
    )


def _telemetry_payload(drone: Any) -> dict[str, object]:
    telemetry = drone.telemetry()
    handshake = drone.handshake_status()
    address = drone.address_status()
    return {
        "batteryPercent": telemetry.battery_percent,
        "heightCentimeters": telemetry.height_cm,
        "temperatureCelsius": telemetry.temperature_c,
        "flightState": "unknown",
        "handshake": asdict(handshake),
        "address": asdict(address),
        "source": "brain2devices",
    }


def main() -> None:
    arguments = _parser().parse_args()
    sys.path.insert(0, str((arguments.repository / "src").resolve()))
    from brain2devices.hardware.tello import DjitelloPyDrone  # type: ignore[import-not-found]

    drone = DjitelloPyDrone(ip_address=arguments.ip_address)
    for raw in sys.stdin:
        request_id: object = None
        try:
            request: object = json.loads(raw)
            if not isinstance(request, dict):
                raise ValueError("Request must be an object")
            request_id = request.get("requestId")
            operation = request.get("operation")
            if operation == "connect":
                drone.connect()
                _response(request_id, ok=True, **_telemetry_payload(drone))
            elif operation == "telemetry":
                _response(request_id, ok=True, **_telemetry_payload(drone))
            elif operation == "land":
                drone.land()
                _response(request_id, ok=True, landed=True, reason=request.get("reason"))
            elif operation == "emergency_stop":
                drone.emergency()
                _response(
                    request_id,
                    ok=True,
                    emergencyStopped=True,
                    reason=request.get("reason"),
                )
            elif operation == "shutdown":
                try:
                    drone.disconnect()
                except Exception:
                    pass
                _response(request_id, ok=True, stopped=True)
                return
            else:
                raise ValueError(f"Unsupported operation {operation!r}")
        except Exception as error:
            _response(request_id, ok=False, message=str(error)[:500])


if __name__ == "__main__":
    main()
