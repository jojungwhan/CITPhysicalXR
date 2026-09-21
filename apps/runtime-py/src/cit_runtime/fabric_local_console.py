"""Open the loopback Fabric console without copying its administrator secret."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import stat
import sys
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import cast
from urllib.parse import quote

_ORIGIN = "http://127.0.0.1:8766"
_ENVIRONMENT_LIMIT = 16_384
_RESPONSE_LIMIT = 16_384
_TOKEN_LINE = re.compile(r'^CITXR_FABRIC_BOOTSTRAP_TOKEN="([A-Za-z0-9_-]{32,512})"$')
_TICKET = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="citxr-local-console",
        description="Open a one-time local Control Tower console session.",
    )
    parser.add_argument(
        "--environment-file",
        type=Path,
        default=Path.home() / ".config" / "citxr" / "remote-plug-runtime.env",
    )
    return parser


def _read_bootstrap_token(path: Path) -> str:
    if path.is_symlink():
        raise ValueError("The Control Tower environment file must not be a symbolic link")
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _ENVIRONMENT_LIMIT:
        raise ValueError("The Control Tower environment file is invalid")
    getuid = cast(Callable[[], int] | None, getattr(os, "getuid", None))
    if getuid is not None:
        if metadata.st_uid != getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise PermissionError(
                "The Control Tower environment file must be owned by this user and mode 0600"
            )
    content = path.read_text(encoding="utf-8")
    matches = [
        matched.group(1)
        for line in content.splitlines()
        if (matched := _TOKEN_LINE.fullmatch(line)) is not None
    ]
    if len(matches) != 1:
        raise ValueError("The Control Tower administrator credential is missing or invalid")
    return matches[0]


def _create_console_ticket(token: str) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", 8766, timeout=5)
    try:
        connection.request(
            "POST",
            "/api/v1/fabric/auth/console-tickets",
            body=b"",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        response = connection.getresponse()
        payload = response.read(_RESPONSE_LIMIT + 1)
    except (OSError, http.client.HTTPException) as error:
        raise RuntimeError("The loopback Control Tower service is unavailable") from error
    finally:
        connection.close()
    if not 200 <= response.status < 300:
        raise RuntimeError(f"Control Tower rejected local console access (HTTP {response.status})")
    if len(payload) > _RESPONSE_LIMIT:
        raise RuntimeError("Control Tower returned an oversized console response")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Control Tower returned an invalid console response") from error
    ticket = document.get("ticket") if isinstance(document, dict) else None
    if not isinstance(ticket, str) or _TICKET.fullmatch(ticket) is None:
        raise RuntimeError("Control Tower did not return a valid one-time console ticket")
    return ticket


def _console_url(ticket: str) -> str:
    if _TICKET.fullmatch(ticket) is None:
        raise ValueError("The one-time console ticket is invalid")
    return f"{_ORIGIN}/fabric#console-ticket={quote(ticket, safe='')}"


def main() -> None:
    arguments = _parser().parse_args()
    try:
        token = _read_bootstrap_token(arguments.environment_file.expanduser())
        url = _console_url(_create_console_ticket(token))
        del token
        opened = webbrowser.open(url, new=1, autoraise=True)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Could not open the local Control Tower console: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    if opened:
        print("Opened a one-time Control Tower console session in the local browser.")
    else:
        print("No local browser was found. Open this one-time URL within 90 seconds:")
        print(url)


if __name__ == "__main__":
    main()
