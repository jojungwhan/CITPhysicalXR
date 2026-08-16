"""Bluetooth failures a person can act on (FR-052, UI 11.6).

The PRD writes this requirement as a worked example, and the example is about a
LEGO hub:

```text
LEGO SPIKE connection failed.

The hub was discovered but did not expose the expected Pybricks protocol.
Detected name: Pybricks Hub
Expected protocol: 1.3+
Suggested action: restart the hub, verify Pybricks firmware, then reconnect.
```

So a failure here is a value with the four parts of that message, not a string
assembled at the call site. The runtime shows it, the log records it, and the
tests assert that the detail line actually names the hub.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HubDiagnostic:
    """One actionable failure. ``code`` is stable; the prose is for a human."""

    code: str
    summary: str
    detail: str
    recovery: str

    def message(self) -> str:
        return "\n".join(
            (
                self.summary,
                "",
                self.detail,
                f"Suggested action: {self.recovery}",
            )
        )


class HubTransportError(RuntimeError):
    """A transport failure that carries its own diagnostic."""

    def __init__(self, diagnostic: HubDiagnostic) -> None:
        super().__init__(diagnostic.message())
        self.diagnostic = diagnostic


def bluetooth_unavailable(reason: str) -> HubDiagnostic:
    return HubDiagnostic(
        code="BLUETOOTH_UNAVAILABLE",
        summary="LEGO hub connection failed: this computer has no usable Bluetooth adapter.",
        detail=f"The Bluetooth stack refused to start scanning. Reported reason: {reason}",
        recovery=(
            "Check that Bluetooth is switched on and that a Low Energy adapter is present, "
            "then run discovery again."
        ),
    )


def transport_missing(package: str) -> HubDiagnostic:
    return HubDiagnostic(
        code="TRANSPORT_UNAVAILABLE",
        summary="LEGO hub connection failed: the Bluetooth transport is not installed.",
        detail=(
            f"The adapter needs {package}, which is an optional dependency so that a "
            "classroom machine without a hub does not have to install a radio stack."
        ),
        recovery="Install it on this machine with `uv sync --extra hardware`, then reconnect.",
    )


def hub_not_found(hub_name: str, seconds: float) -> HubDiagnostic:
    return HubDiagnostic(
        code="HUB_NOT_FOUND",
        summary=f"LEGO hub {hub_name!r} was not found.",
        detail=(
            f"No hub advertising that name answered within {seconds:.0f} seconds. "
            "A hub only advertises while its Bluetooth light is pulsing blue."
        ),
        recovery=(
            "Press the hub's Bluetooth button until the light pulses blue, check the hub name "
            "in the class configuration, then reconnect."
        ),
    )


def protocol_mismatch(detected_name: str, expected_profile: str) -> HubDiagnostic:
    return HubDiagnostic(
        code="PROTOCOL_MISMATCH",
        summary="LEGO SPIKE connection failed.",
        detail=(
            "The hub was discovered but did not expose the expected Pybricks protocol.\n"
            f"Detected name: {detected_name}\n"
            f"Expected protocol: {expected_profile}+"
        ),
        recovery="restart the hub, verify Pybricks firmware, then reconnect.",
    )


def model_mismatch(configured: str, reported: str) -> HubDiagnostic:
    return HubDiagnostic(
        code="HUB_MODEL_MISMATCH",
        summary="LEGO hub connection refused: this is not the hub the class expects.",
        detail=(
            f"The configuration binds this device to a {configured}, but the hub that "
            f"answered reports itself as a {reported}. Port letters and capabilities differ "
            "between hubs, so the runtime will not guess."
        ),
        recovery=(
            "Connect the hub the class is configured for, or update the hub model in the "
            "class configuration."
        ),
    )


def handshake_timeout(hub_name: str, seconds: float) -> HubDiagnostic:
    return HubDiagnostic(
        code="HUB_HANDSHAKE_TIMEOUT",
        summary=f"LEGO hub {hub_name!r} connected but never answered the runtime.",
        detail=(
            f"The hub accepted the connection but sent no HELLO within {seconds:.1f} seconds. "
            "That usually means the hub agent program is not running on it."
        ),
        recovery=(
            "Start the CIT hub agent program on the hub (see docs/LEGO_SETUP.md), then reconnect."
        ),
    )


def link_lost(hub_name: str, reason: str) -> HubDiagnostic:
    return HubDiagnostic(
        code="HUB_LINK_LOST",
        summary=f"The link to LEGO hub {hub_name!r} was lost.",
        detail=f"Motors were told to stop by the hub's own watchdog. Reported reason: {reason}",
        recovery=(
            "Move the hub closer to the computer, check its battery, then reconnect and arm it "
            "again before it can move."
        ),
    )
