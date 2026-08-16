"""Building hardware discovery providers from a class configuration.

This is the only place in the runtime that knows a physical adapter exists by
name, and it is deliberately small: a configuration file names devices, this
module turns each entry into a discovery provider, and everything downstream
sees the same :class:`DiscoveryProvider` the fakes use.

The configuration never carries a Bluetooth address. The PRD forbids committing
one, and binding by the advertised hub name means there is nothing device-secret
to leak in the first place (FR-052).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cit_lego_pybricks import HubBinding, HubSafetyLimits, PybricksDiscoveryProvider

from .config import ConfigurationError, load_config
from .registry import DiscoveryProvider
from .runtime import Runtime
from .supervisor import MotionBounds, SafetyPolicy

LEGO_ADAPTER = "lego-pybricks"

#: The profile a LEGO lesson runs under until an instructor chooses another.
#: Half speed, two-second steps, dead-man held: the same shape as every other
#: physical profile, in the units the student SDK speaks.
LEGO_STUDENT_POLICY = SafetyPolicy(
    policy_id="lego-student",
    bounds=MotionBounds(max_speed=0.5, max_duration_seconds=2.0),
)


def configured_device_ids(config: Mapping[str, Any]) -> tuple[str, ...]:
    devices = config.get("devices")
    if not isinstance(devices, Mapping):
        return ()
    return tuple(sorted(str(device_id) for device_id in devices))


def lego_bindings(config: Mapping[str, Any]) -> tuple[HubBinding, ...]:
    """Read every ``lego-pybricks`` entry, or say exactly what is missing."""

    devices = config.get("devices")
    if not isinstance(devices, Mapping):
        return ()

    bindings: list[HubBinding] = []
    for device_id, entry in sorted(devices.items()):
        if not isinstance(entry, Mapping) or entry.get("adapter") != LEGO_ADAPTER:
            continue
        hub_name = entry.get("hubName")
        hub_model = entry.get("hubModel")
        ports = entry.get("ports")
        if not isinstance(hub_name, str) or not hub_name:
            raise ConfigurationError(
                f"Device {device_id!r} uses the {LEGO_ADAPTER} adapter but has no 'hubName'. "
                "Set it to the name the hub advertises over Bluetooth."
            )
        if not isinstance(hub_model, str) or not hub_model:
            raise ConfigurationError(
                f"Device {device_id!r} has no 'hubModel'. Port letters and capabilities "
                "differ between hubs, so the runtime will not guess."
            )
        if not isinstance(ports, Mapping) or not ports:
            raise ConfigurationError(
                f"Device {device_id!r} has no 'ports'. List what is plugged into the hub, "
                "for example {A: motor, B: motor, C: distance}."
            )
        limits = HubSafetyLimits(
            max_motor_percent=int(entry.get("maxMotorPercent", 75)),
            max_command_milliseconds=int(entry.get("maxCommandMilliseconds", 2000)),
        )
        try:
            binding = HubBinding(
                device_id=str(device_id),
                display_name=str(entry.get("displayName", device_id)),
                hub_name=hub_name,
                model_id=hub_model,
                ports={str(port): str(kind) for port, kind in ports.items()},
                safety_profile=str(entry.get("safetyProfile", "lego-student")),
                limits=limits,
            )
            binding.port_map()
        except (KeyError, ValueError) as error:
            raise ConfigurationError(f"Device {device_id!r}: {error}") from error
        bindings.append(binding)
    return tuple(bindings)


def build_providers(config: Mapping[str, Any]) -> Sequence[DiscoveryProvider]:
    """Every hardware provider this configuration asks for."""

    bindings = lego_bindings(config)
    if not bindings:
        return ()
    return (PybricksDiscoveryProvider(bindings),)


def physical_devices_enabled(config: Mapping[str, Any]) -> bool:
    runtime = config.get("runtime")
    if not isinstance(runtime, Mapping):
        return False
    return bool(runtime.get("physicalDevicesEnabled", False))


def runtime_from_config(path: str | Path) -> Runtime:
    """Build a runtime from a class configuration file.

    A configuration that names hubs while physical devices are switched off is
    refused rather than quietly ignored: an instructor who wired up a hub and
    got silence would reasonably conclude the hub was broken.
    """

    config = load_config(path)
    providers = build_providers(config)
    enabled = physical_devices_enabled(config)
    if providers and not enabled:
        configured = ", ".join(configured_device_ids(config))
        raise ConfigurationError(
            f"This configuration binds physical devices ({configured}) but sets "
            "runtime.physicalDevicesEnabled to false. Set it to true to allow this "
            "machine to connect to them, or remove the devices section."
        )
    return Runtime(
        providers=providers,
        policies=(LEGO_STUDENT_POLICY,),
        physical_enabled=enabled,
    )
