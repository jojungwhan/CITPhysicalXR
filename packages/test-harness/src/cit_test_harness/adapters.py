"""Shape checks shared by fake and future hardware adapter contract suites."""

from __future__ import annotations

from cit_device_simulator import DeviceAdapter


class AdapterContractViolation(TypeError):
    """Raised before behavioral tests when an adapter misses the public surface."""


def require_device_adapter(adapter: object) -> DeviceAdapter:
    """Return an adapter after checking the runtime-checkable public protocol."""

    if not isinstance(adapter, DeviceAdapter):
        raise AdapterContractViolation(
            f"{type(adapter).__name__} does not implement the DeviceAdapter contract"
        )
    return adapter
