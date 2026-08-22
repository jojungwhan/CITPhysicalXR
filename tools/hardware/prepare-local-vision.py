"""Prepare the fixed, local YOLO-World model used by Classroom Control.

This setup step downloads code only through the locked Python environment and
downloads the fixed public model assets once. It never opens or analyzes a
camera frame.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path

MODEL_NAME = "yolov8s-worldv2.pt"
LABELS = ("lamp", "drone", "smart plug", "robot", "light")
CLIP_REVISION = "68dce32140994dfcb645a1320c4ebdc034fc19fd"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    state_root = arguments.state_root.expanduser().resolve()
    vision_root = state_root / "vision"
    vision_root.mkdir(parents=True, exist_ok=True)
    model_path = vision_root / MODEL_NAME
    marker_path = vision_root / "ready.json"
    ultralytics_version = importlib.metadata.version("ultralytics")
    expected = {
        "schemaVersion": 1,
        "model": MODEL_NAME,
        "labels": list(LABELS),
        "ultralyticsVersion": ultralytics_version,
        "clipRevision": CLIP_REVISION,
    }
    if model_path.is_file() and marker(marker_path) == expected:
        print(f"READY local object recognition: {model_path}")
        return 0

    # Disable Ultralytics' package-manager side effects. All Python code is
    # already pinned by uv; only the fixed public model weights may download.
    os.environ["YOLO_AUTOINSTALL"] = "false"
    os.environ["YOLO_VERBOSE"] = "false"
    os.environ["ULTRALYTICS_SAFE_LOAD"] = "true"
    from ultralytics import YOLOWorld

    previous_directory = Path.cwd()
    try:
        os.chdir(vision_root)
        model = YOLOWorld(str(model_path) if model_path.is_file() else MODEL_NAME)
        model.set_classes(list(LABELS))
    finally:
        os.chdir(previous_directory)
    if not model_path.is_file():
        raise RuntimeError("YOLO-World did not create the expected local model file")
    marker_path.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    print(f"READY local object recognition: {model_path}")
    return 0


def marker(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
