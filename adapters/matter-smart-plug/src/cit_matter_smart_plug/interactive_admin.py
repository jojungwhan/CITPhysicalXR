"""Secret-safe interactive wrapper for local Linux Matter setup."""

from __future__ import annotations

import argparse
import getpass
import json
import subprocess
import sys


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cit-matter-setup")
    parser.add_argument("operation", choices=("inventory", "configure-wifi", "commission"))
    return parser


def _payload(operation: str) -> dict[str, str] | None:
    if operation == "inventory":
        return None
    if operation == "configure-wifi":
        ssid = input("Exact 2.4 GHz Wi-Fi name: ")
        password = getpass.getpass("Wi-Fi password: ")
        if not 1 <= len(ssid.encode("utf-8")) <= 32:
            raise ValueError("Wi-Fi name must contain 1 to 32 UTF-8 bytes")
        if not 8 <= len(password) <= 63:
            raise ValueError("Wi-Fi password must contain 8 to 63 characters")
        return {"ssid": ssid, "password": password}
    setup_code = getpass.getpass("Printed Matter QR text or manual setup code: ")
    if not 11 <= len(setup_code) <= 103:
        raise ValueError("Matter setup code length is invalid")
    return {"setupCode": setup_code}


def main() -> None:
    arguments = _parser().parse_args()
    payload = _payload(arguments.operation)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "cit_matter_smart_plug.admin",
            arguments.operation,
            "--server-url",
            "ws://127.0.0.1:5580/ws",
        ],
        check=False,
        input=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
        text=True,
        timeout=300,
    )
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
