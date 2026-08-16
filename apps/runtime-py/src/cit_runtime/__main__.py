"""``python -m cit_runtime`` starts the local runtime on the loopback interface."""

from __future__ import annotations

import argparse

from .api import serve


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cit_runtime",
        description="Run the CIT Physical XR local runtime (simulation by default).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind (loopback only)")
    parser.add_argument("--port", type=int, default=8791, help="TCP port to listen on")
    parser.add_argument(
        "--allow-non-loopback",
        action="store_true",
        help=(
            "Bind a routable interface. Only for an isolated network you control; "
            "the PRD forbids exposing device control to the public internet."
        ),
    )
    arguments = parser.parse_args()
    serve(
        host=arguments.host,
        port=arguments.port,
        allow_non_loopback=arguments.allow_non_loopback,
    )


if __name__ == "__main__":
    main()
