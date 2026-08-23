"""Event worker importing only Brain2Devices' MindWave implementation."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path
from typing import Any


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=15)
    return parser


_write_lock = threading.Lock()


def _write(kind: str, **values: object) -> None:
    with _write_lock:
        print(json.dumps({"type": kind, **values}, separators=(",", ":")), flush=True)


def main() -> None:
    arguments = _parser().parse_args()
    sys.path.insert(0, str((arguments.repository / "src").resolve()))
    from brain2devices.hardware.mindwave import (  # type: ignore[import-not-found]
        PyMindWaveHeadset,
    )

    headset = PyMindWaveHeadset(
        attempts=arguments.attempts,
        timeout_seconds=arguments.timeout_seconds,
    )
    try:
        headset.connect(
            on_reading=lambda reading: _write(
                "reading",
                attention=reading.attention,
                meditation=reading.meditation,
                signalQuality=reading.signal_quality,
            ),
            on_blink=lambda strength: _write("blink", strength=strength),
            on_status=lambda connected, message: _write(
                "status", connected=connected, message=message
            ),
        )
        _write("ready")
        for raw in sys.stdin:
            try:
                request: Any = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(request, dict) and request.get("operation") == "shutdown":
                break
    except Exception as error:
        _write("fatal", message=str(error)[:500])
    finally:
        try:
            headset.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
