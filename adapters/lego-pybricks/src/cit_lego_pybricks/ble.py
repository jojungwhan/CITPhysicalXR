"""The real radio, built on the Pybricks project's own ``pybricksdev``.

**This module has never been executed against a hub.** It was written on a
machine with no Bluetooth adapter, so everything below is unverified against
hardware and must be treated as bring-up work rather than as a working feature.
`docs/LEGO_SETUP.md` carries the checklist. The rest of the adapter is tested,
because the rest of the adapter talks to :class:`HubTransport` and not to this.

Why ``pybricksdev`` rather than raw GATT: the Pybricks BLE service, its
characteristic UUIDs, its command and event byte codes, and the framing of
``WriteStdin``/``WriteStdout`` are the firmware project's own protocol, and they
change with the firmware. Hardcoding those constants here would mean CIT
silently owning a copy of someone else's wire format. ``pybricksdev`` is MIT,
maintained by the same project, and is what the PRD names in section 2.3.

The three assumptions to confirm on first hardware contact:

1. ``pybricksdev.ble.find_device(name, timeout=...)`` resolves a hub by its
   advertised name.
2. ``PybricksHub.write(data)`` reaches the running program's ``stdin``, and the
   program's ``print()`` output arrives through the hub's line handler.
3. ``PybricksHub.run(path, wait=False)`` compiles with ``mpy-cross`` and
   installs the program (FR-048).

If any of the three is wrong, only this file changes.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .diagnostics import (
    HubTransportError,
    bluetooth_unavailable,
    hub_not_found,
    link_lost,
    transport_missing,
)

DEFAULT_SCAN_SECONDS = 10.0


class PybricksdevTransport:
    """One BLE link to one hub, addressed by the name it advertises."""

    def __init__(self, *, hub_name: str, scan_seconds: float = DEFAULT_SCAN_SECONDS) -> None:
        self.hub_name = hub_name
        self._scan_seconds = scan_seconds
        self._hub: Any | None = None
        self._lines: deque[str] = deque(maxlen=256)

    @property
    def connected(self) -> bool:
        hub = self._hub
        if hub is None:
            return False
        connected = getattr(hub, "connected", True)
        return bool(connected)

    async def connect(self) -> None:
        find_device, hub_class = _import_pybricksdev()

        try:
            device = await find_device(self.hub_name, timeout=self._scan_seconds)
        except TimeoutError as error:
            raise HubTransportError(hub_not_found(self.hub_name, self._scan_seconds)) from error
        except OSError as error:
            raise HubTransportError(bluetooth_unavailable(str(error))) from error
        except Exception as error:  # pragma: no cover - vendor error taxonomy
            raise HubTransportError(bluetooth_unavailable(str(error))) from error

        if device is None:
            raise HubTransportError(hub_not_found(self.hub_name, self._scan_seconds))

        hub = _line_capturing_hub(hub_class, self._lines)
        try:
            await hub.connect(device)
        except Exception as error:  # pragma: no cover - vendor error taxonomy
            raise HubTransportError(bluetooth_unavailable(str(error))) from error
        self._hub = hub

    async def disconnect(self) -> None:
        hub = self._hub
        self._hub = None
        if hub is None:
            return
        try:
            await hub.disconnect()
        except Exception:  # pragma: no cover - a closed link is the goal
            return

    async def send_line(self, line: str) -> None:
        hub = self._hub
        if hub is None:
            raise HubTransportError(link_lost(self.hub_name, "the link is closed"))
        try:
            await hub.write(line.encode("ascii"))
        except Exception as error:  # pragma: no cover - vendor error taxonomy
            raise HubTransportError(link_lost(self.hub_name, str(error))) from error

    def drain_lines(self) -> tuple[str, ...]:
        lines = tuple(self._lines)
        self._lines.clear()
        return lines

    async def download_program(self, source: str, *, name: str) -> None:
        """FR-048. Compile and install; never called by starting a lesson."""

        hub = self._hub
        if hub is None:
            raise HubTransportError(link_lost(self.hub_name, "the link is closed"))
        with TemporaryDirectory(prefix="citxr-lego-") as directory:
            path = Path(directory) / f"{name}.py"
            path.write_text(source, encoding="utf-8")
            try:
                await hub.run(str(path), wait=False)
            except Exception as error:  # pragma: no cover - vendor error taxonomy
                raise HubTransportError(link_lost(self.hub_name, str(error))) from error


def _import_pybricksdev() -> tuple[Any, Any]:
    try:
        from pybricksdev.ble import find_device
        from pybricksdev.connections.pybricks import PybricksHub
    except ImportError as error:
        raise HubTransportError(transport_missing("pybricksdev")) from error
    return find_device, PybricksHub


def _line_capturing_hub(hub_class: Any, sink: deque[str]) -> Any:
    """Wrap the vendor hub so its stdout lines land in our own buffer."""

    class _CapturingHub(hub_class):  # type: ignore[misc]
        def line_handler(self, line: bytes) -> None:
            sink.append(line.decode("utf-8", errors="replace"))

    hub = _CapturingHub()
    # The vendor class prints hub output to the terminal by default, which would
    # scroll protocol frames past a teacher trying to read an error.
    if hasattr(hub, "print_output"):
        hub.print_output = False
    return hub
