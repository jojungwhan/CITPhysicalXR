from __future__ import annotations

import ast
import json
from pathlib import Path

from cit_integration_sdk import external_source
from cit_runtime.fabric_course import (
    builtin_course_pack_ids,
    load_builtin_course_pack,
    load_course_pack,
)
from cit_runtime.fabric_integration_catalog import load_integration_catalog

ROOT = Path(__file__).resolve().parents[2]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_fabric_core_imports_no_vendor_or_adapter_package() -> None:
    forbidden = (
        "brain2devices",
        "cit_brain2devices_demo",
        "cit_lego_pybricks",
        "cit_matter_smart_plug",
        "cit_mindwave_mobile2",
        "cit_robomaster_leap",
        "cit_tello",
        "djitellopy",
        "pybricksdev",
        "pymindwave2",
        "robomaster",
    )
    core = ROOT / "apps" / "runtime-py" / "src" / "cit_runtime"
    for path in core.glob("fabric*.py"):
        imports = _imports(path)
        assert not any(name.startswith(forbidden) for name in imports), (path, imports)


def test_tello_and_mindwave_workers_import_only_their_own_brain2devices_port() -> None:
    tello = _imports(ROOT / "adapters" / "tello" / "src" / "cit_tello" / "vendor_worker.py")
    mindwave = _imports(
        ROOT / "adapters" / "mindwave-mobile2" / "src" / "cit_mindwave_mobile2" / "vendor_worker.py"
    )
    assert "brain2devices.hardware.tello" in tello
    assert "brain2devices.hardware.mindwave" not in tello
    assert "brain2devices.hardware.mindwave" in mindwave
    assert "brain2devices.hardware.tello" not in mindwave


def test_matter_smart_plug_bridge_reuses_the_shared_fabric_wire_client() -> None:
    bridge = ROOT / "adapters" / "matter-smart-plug" / "src" / "cit_matter_smart_plug" / "bridge.py"
    imports = _imports(bridge)
    assert "cit_integration_sdk" in imports
    assert not any(name.startswith("websockets") for name in imports)


def test_only_matter_smart_plug_adapter_is_deployable() -> None:
    adapters = ROOT / "adapters"

    assert (adapters / "matter-smart-plug" / "pyproject.toml").is_file()
    assert not (adapters / "tuya-smart-plug").exists()
    assert not (adapters / "tasmota-smart-plug").exists()


def test_builtin_course_resources_are_generated_from_authoritative_yaml() -> None:
    source_ids = tuple(
        sorted(path.parent.name for path in (ROOT / "course-packs").glob("*/course-pack.yaml"))
    )
    assert builtin_course_pack_ids() == source_ids
    for course_id in source_ids:
        source = ROOT / "course-packs" / course_id / "course-pack.yaml"
        assert load_builtin_course_pack(course_id) == load_course_pack(source)


def test_integration_catalog_has_no_duplicate_ids_and_matches_split_plugins() -> None:
    catalog = load_integration_catalog()
    ids = [item.integrationId for item in catalog.integrations]
    assert len(ids) == len(set(ids))
    assert "cit.leap-motion" in catalog.require("leap-motion").selectors.pluginIds
    assert "cit.robomaster-s1" in catalog.require("robomaster-s1").selectors.pluginIds
    sphero = catalog.require("sphero-bolt")
    assert sphero.ioType == "bidirectional"
    assert sphero.icon == "sphero"
    assert sphero.selectors.pluginIds == ["cit.sphero-bolt"]
    assert sphero.selectors.models == ["sphero-bolt"]
    assert catalog.require("tello-drones").selectors.pluginIds == [
        "cit.tello",
        "cit.brain2devices-fleet",
    ]
    assert catalog.require("mindwave-mobile2").selectors.pluginIds == ["cit.mindwave-mobile2"]
    assert catalog.require("mindwave-tello-demo").selectors.pluginIds == ["cit.brain2devices-demo"]
    assert catalog.require("even-realities-g2").selectors.models == ["even-realities-g2"]
    assert catalog.require("meta-rayban").selectors.models == ["meta-rayban"]
    assert catalog.require("even-realities-g2").selectors.pluginIds == ["cit.agent-mesh-bridge"]
    assert catalog.require("meta-rayban").selectors.pluginIds == ["cit.agent-mesh-bridge"]


def test_external_source_revisions_are_generated_once_for_python_and_windows() -> None:
    generated = json.loads(
        (ROOT / "tools" / "hardware" / "external-sources.generated.json").read_text(
            encoding="utf-8"
        )
    )
    for key in ("brain2devices", "robomaster-gesture-control"):
        source = external_source(key)
        assert generated["sources"][key]["revision"] == source.revision
        assert generated["sources"][key]["repository"] == source.repository
