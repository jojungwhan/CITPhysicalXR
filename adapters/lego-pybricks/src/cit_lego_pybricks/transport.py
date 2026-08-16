"""The injectable BLE boundary (FR-052).

The PRD requires the Bluetooth layer to be replaceable, and the reason is not
elegance: a classroom laptop, a CI runner, and a developer's machine with no
radio at all must all be able to run the same adapter code. Everything above
this file therefore talks to :class:`HubTransport`, which knows nothing about
Bluetooth -- it moves lines of text to and from a hub, and can hand the hub a
program.

Two implementations exist:

- :class:`~cit_lego_pybricks.fakes.FakeHubTransport`, a hub simulated in
  memory. Every test in this package runs against it.
- :class:`~cit_lego_pybricks.ble.PybricksdevTransport`, the real radio, built on
  the Pybricks project's own ``pybricksdev``. It is an optional dependency and
  is never imported unless a real hub is configured.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class HubTransport(Protocol):
    """Move protocol lines to and from one hub.

    Implementations must not interpret the lines. Framing, sequencing, and every
    safety decision belong to the adapter and the runtime above it; a transport
    that started answering frames itself would be a second place where a robot
    can be told to move.
    """

    hub_name: str

    @property
    def connected(self) -> bool: ...

    async def connect(self) -> None:
        """Open the link. Raises ``HubTransportError`` with a diagnostic."""

    async def disconnect(self) -> None:
        """Close the link. Must be safe to call when already closed."""

    async def send_line(self, line: str) -> None:
        """Write one terminated protocol line to the hub's stdin."""

    def drain_lines(self) -> tuple[str, ...]:
        """Return and clear the lines the hub has sent since the last call."""

    async def download_program(self, source: str, *, name: str) -> None:
        """Compile and install a program on the hub (FR-048).

        Separate from :meth:`send_line` on purpose. Sending a line is what a
        lesson does constantly; installing a program replaces what the hub runs
        and is an explicit, instructor-initiated act.
        """
