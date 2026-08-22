"""Read-only LAN preflight used by the Windows hardware launcher."""

from __future__ import annotations

import argparse
import asyncio
import os

from .backend import TinyTuyaConfiguration, TinyTuyaLanPlug


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cit-tuya-smart-plug-probe")
    parser.add_argument("--device-address", required=True)
    parser.add_argument("--protocol-version", required=True)
    parser.add_argument("--switch-dps", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=3.0)
    return parser


async def _run(arguments: argparse.Namespace) -> None:
    device_id = os.environ.get("CIT_TUYA_DEVICE_ID")
    local_key = os.environ.get("CIT_TUYA_LOCAL_KEY")
    if device_id is None or local_key is None:
        raise ValueError("Protected Tuya device environment is unavailable")
    backend = TinyTuyaLanPlug(
        TinyTuyaConfiguration(
            device_id=device_id,
            local_key=local_key,
            device_address=arguments.device_address,
            protocol_version=arguments.protocol_version,
            switch_dps=arguments.switch_dps,
            timeout_seconds=arguments.timeout,
        )
    )
    try:
        state = await backend.start()
    finally:
        await backend.close()
    print(f"PASS read-only Tuya LAN status: {'ON' if state else 'OFF'}", flush=True)


def main() -> None:
    asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    main()
