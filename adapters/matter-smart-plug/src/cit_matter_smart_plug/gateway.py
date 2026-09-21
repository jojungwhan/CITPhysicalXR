"""Supervise all commissioned Matter plugs on an always-on local gateway."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import signal
import socket
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .matter_client import MatterEndpoint, MatterServerClient, discover_plug_endpoints

LOGGER = logging.getLogger(__name__)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SENSITIVE_PARENT_VARIABLES = {
    "CITXR_FABRIC_BOOTSTRAP_TOKEN",
    "CITXR_MATTER_ADAPTER_TOKEN",
}
_INVENTORY_REFRESH_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class GatewayConfiguration:
    adapter_url: str
    adapter_token: str
    matter_server_url: str
    site_id: str
    room_id: str
    host_id: str
    activation_root: Path

    @classmethod
    def from_environment(cls) -> GatewayConfiguration:
        activation_root = Path(
            os.environ.get(
                "CIT_MATTER_ACTIVATION_ROOT",
                str(Path.home() / ".local" / "state" / "cit-physical-xr" / "matter-active"),
            )
        )
        configuration = cls(
            adapter_url=os.environ.get(
                "CIT_MATTER_ADAPTER_URL",
                "ws://127.0.0.1:8766/api/v1/adapters/connect",
            ),
            adapter_token=os.environ.get("CITXR_MATTER_ADAPTER_TOKEN", ""),
            matter_server_url=os.environ.get(
                "CIT_MATTER_SERVER_URL",
                "ws://127.0.0.1:5580/ws",
            ),
            site_id=os.environ.get("CIT_MATTER_SITE_ID", "local-site"),
            room_id=os.environ.get("CIT_MATTER_ROOM_ID", "local-room"),
            host_id=os.environ.get("CIT_MATTER_HOST_ID", _safe_hostname()),
            activation_root=activation_root,
        )
        configuration.validate()
        return configuration

    def validate(self) -> None:
        for label, value in (
            ("site ID", self.site_id),
            ("room ID", self.room_id),
            ("host ID", self.host_id),
        ):
            if _IDENTIFIER.fullmatch(value) is None:
                raise ValueError(f"Matter gateway {label} is invalid")
        if (
            len(self.adapter_token) < 32
            or len(self.adapter_token) > 512
            or self.adapter_token != self.adapter_token.strip()
            or any(character.isspace() for character in self.adapter_token)
        ):
            raise ValueError("CITXR_MATTER_ADAPTER_TOKEN is missing or invalid")
        parsed_adapter = urlsplit(self.adapter_url)
        if (
            parsed_adapter.scheme != "ws"
            or parsed_adapter.hostname != "127.0.0.1"
            or parsed_adapter.port is None
            or parsed_adapter.path != "/api/v1/adapters/connect"
            or parsed_adapter.username is not None
            or parsed_adapter.password is not None
            or parsed_adapter.query
            or parsed_adapter.fragment
        ):
            raise ValueError("CIT_MATTER_ADAPTER_URL must be the exact loopback Fabric endpoint")
        parsed_matter = urlsplit(self.matter_server_url)
        if (
            parsed_matter.scheme != "ws"
            or parsed_matter.hostname != "127.0.0.1"
            or parsed_matter.port is None
            or parsed_matter.path != "/ws"
            or parsed_matter.username is not None
            or parsed_matter.password is not None
            or parsed_matter.query
            or parsed_matter.fragment
        ):
            raise ValueError("CIT_MATTER_SERVER_URL must be the exact loopback Matter endpoint")
        if not self.activation_root.is_absolute():
            raise ValueError("CIT_MATTER_ACTIVATION_ROOT must be an absolute path")


async def run_gateway(configuration: GatewayConfiguration) -> None:
    """Start one bounded adapter per available commissioned plug and supervise them."""

    known_endpoints = await _inventory(configuration.matter_server_url)
    endpoints = tuple(endpoint for endpoint in known_endpoints if endpoint.available)
    if not endpoints:
        raise RuntimeError("No available commissioned Matter smart-plug endpoints were found")
    configuration.activation_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    configuration.activation_root.chmod(0o700)

    processes: list[asyncio.subprocess.Process] = []
    activation_files: list[Path] = []
    waiters: list[asyncio.Task[Any]] = []
    stop_requested = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed_signals: list[signal.Signals] = []
    for handled_signal in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(handled_signal, stop_requested.set)
        except (NotImplementedError, RuntimeError):
            continue
        installed_signals.append(handled_signal)

    try:
        for endpoint in endpoints:
            activation_file = configuration.activation_root / f"{endpoint.cit_node_id}.flag"
            activation_file.write_text("connected\n", encoding="ascii")
            activation_file.chmod(0o600)
            activation_files.append(activation_file)
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "cit_matter_smart_plug",
                env=_adapter_environment(configuration, endpoint, activation_file),
            )
            processes.append(process)
            LOGGER.info(
                "Started supervised Matter adapter node_id=%s pid=%s",
                endpoint.cit_node_id,
                process.pid,
            )

        process_waiters = [asyncio.create_task(process.wait()) for process in processes]
        stop_waiter = asyncio.create_task(stop_requested.wait())
        inventory_waiter = asyncio.create_task(
            _wait_for_new_available_endpoint(
                configuration.matter_server_url,
                frozenset(_endpoint_key(endpoint) for endpoint in endpoints),
            )
        )
        waiters.extend(process_waiters)
        waiters.append(stop_waiter)
        waiters.append(inventory_waiter)
        done, pending = await asyncio.wait(
            (*process_waiters, stop_waiter, inventory_waiter),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_waiter in done:
            pass
        elif inventory_waiter in done:
            raise RuntimeError(
                "A newly available Matter plug was found; restarting supervised adapters"
            )
        else:
            failed_indexes = [
                index for index, waiter in enumerate(process_waiters) if waiter in done
            ]
            failed = failed_indexes[0]
            raise RuntimeError(
                f"Matter adapter {endpoints[failed].cit_node_id} exited unexpectedly "
                f"with status {processes[failed].returncode}"
            )
        for waiter in pending:
            waiter.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    finally:
        for waiter in waiters:
            if not waiter.done():
                waiter.cancel()
        await asyncio.gather(*waiters, return_exceptions=True)
        for handled_signal in installed_signals:
            loop.remove_signal_handler(handled_signal)
        for activation_file in activation_files:
            activation_file.unlink(missing_ok=True)
        await _stop_processes(processes)


async def _inventory(server_url: str) -> tuple[MatterEndpoint, ...]:
    client = MatterServerClient(server_url, timeout_seconds=30)
    await client.connect()
    try:
        return tuple(discover_plug_endpoints(client.nodes.values()))
    finally:
        await client.close()


async def _wait_for_new_available_endpoint(
    server_url: str,
    managed_endpoint_keys: frozenset[tuple[int, int]],
    *,
    interval_seconds: float = _INVENTORY_REFRESH_SECONDS,
) -> None:
    """Trigger a supervised restart when a recovered or new plug can be attached."""

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            endpoints = await _inventory(server_url)
        except Exception as error:
            LOGGER.warning(
                "Matter inventory refresh failed error_type=%s",
                type(error).__name__,
            )
            continue
        if any(
            endpoint.available and _endpoint_key(endpoint) not in managed_endpoint_keys
            for endpoint in endpoints
        ):
            return


def _endpoint_key(endpoint: MatterEndpoint) -> tuple[int, int]:
    return endpoint.matter_node_id, endpoint.endpoint_id


def _adapter_environment(
    configuration: GatewayConfiguration,
    endpoint: MatterEndpoint,
    activation_file: Path,
) -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items() if key not in _SENSITIVE_PARENT_VARIABLES
    }
    environment.update(
        {
            "CIT_FABRIC_ADAPTER_TOKEN": configuration.adapter_token,
            "CIT_MATTER_ADAPTER_URL": configuration.adapter_url,
            "CIT_MATTER_SESSION_ID": "matter-gateway",
            "CIT_MATTER_SITE_ID": configuration.site_id,
            "CIT_MATTER_ROOM_ID": configuration.room_id,
            "CIT_MATTER_HOST_ID": configuration.host_id,
            "CIT_MATTER_CIT_NODE_ID": endpoint.cit_node_id,
            "CIT_MATTER_ACTIVATION_FILE": str(activation_file),
            "CIT_MATTER_SERVER_URL": configuration.matter_server_url,
            "CIT_MATTER_NODE_ID": str(endpoint.matter_node_id),
            "CIT_MATTER_ENDPOINT_ID": str(endpoint.endpoint_id),
            "CIT_MATTER_DISPLAY_NAME": endpoint.display_name,
            "CIT_MATTER_VENDOR_NAME": endpoint.vendor_name or "Matter",
            "CIT_MATTER_PRODUCT_NAME": endpoint.product_name or "On/Off Plug-in Unit",
        }
    )
    return environment


async def _stop_processes(processes: list[asyncio.subprocess.Process]) -> None:
    running = [process for process in processes if process.returncode is None]
    if not running:
        return
    try:
        async with asyncio.timeout(12):
            await asyncio.gather(*(process.wait() for process in running))
            return
    except TimeoutError:
        pass
    for process in running:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.terminate()
    try:
        async with asyncio.timeout(5):
            await asyncio.gather(*(process.wait() for process in running))
            return
    except TimeoutError:
        pass
    for process in running:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
    await asyncio.gather(*(process.wait() for process in running), return_exceptions=True)


def _safe_hostname() -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]", "-", socket.gethostname()).strip("-.")
    return normalized[:128] if normalized else "matter-gateway"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        asyncio.run(run_gateway(GatewayConfiguration.from_environment()))
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
