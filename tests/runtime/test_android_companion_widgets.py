from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPOSITORY_ROOT / "apps" / "control-tower-companion" / "app" / "src" / "main"
ANDROID = "{http://schemas.android.com/apk/res/android}"


def test_android_companion_exposes_separate_toggle_and_launcher_widgets() -> None:
    manifest = ElementTree.parse(APP_ROOT / "AndroidManifest.xml")
    receivers = {
        receiver.attrib[f"{ANDROID}name"]: receiver
        for receiver in manifest.findall("./application/receiver")
    }

    toggle = receivers[".SmartPlugWidgetProvider"]
    launcher = receivers[".ControlTowerLauncherWidgetProvider"]
    assert toggle.attrib[f"{ANDROID}label"] == "@string/toggle_widget_name"
    assert launcher.attrib[f"{ANDROID}label"] == "@string/launcher_widget_name"
    toggle_metadata = toggle.find("meta-data")
    launcher_metadata = launcher.find("meta-data")
    assert toggle_metadata is not None
    assert launcher_metadata is not None
    assert toggle_metadata.attrib[f"{ANDROID}resource"] == "@xml/smart_plug_widget_info"
    assert launcher_metadata.attrib[f"{ANDROID}resource"] == (
        "@xml/control_tower_launcher_widget_info"
    )

    toggle_provider = (
        APP_ROOT / "java/com/cit/controltower/companion/SmartPlugWidgetProvider.java"
    ).read_text(encoding="utf-8")
    launcher_provider = (
        APP_ROOT / "java/com/cit/controltower/companion/ControlTowerLauncherWidgetProvider.java"
    ).read_text(encoding="utf-8")
    assert "UnlockClient.toggle(" in toggle_provider
    assert "PendingIntent.getBroadcast(" in toggle_provider
    assert "MainActivity.class" not in toggle_provider
    assert "PendingIntent.getActivity(" in launcher_provider
    assert "MainActivity.class" in launcher_provider
    assert "UnlockClient" not in launcher_provider


def test_companion_screen_can_pin_each_widget_independently() -> None:
    activity = (APP_ROOT / "java/com/cit/controltower/companion/MainActivity.java").read_text(
        encoding="utf-8"
    )

    assert "requestToggleWidget()" in activity
    assert "requestLauncherWidget()" in activity
    assert "SmartPlugWidgetProvider.class" in activity
    assert "ControlTowerLauncherWidgetProvider.class" in activity
