/**
 * The Python side of the student worker.
 *
 * This runs inside Pyodide. It installs a bridge whose transport posts an RPC
 * to the host page and awaits the reply, then executes the student's module and
 * drives whatever `@every` and `@when` handlers it registered.
 *
 * Why the student's code is executed with `exec` here, when the PRD forbids
 * "arbitrary eval": the prohibition is about the *runtime* exposing an
 * execute-this endpoint to the network. This is the opposite -- the student's
 * own program, running inside the WASM sandbox, with no filesystem, no sockets,
 * and a bridge that can only make five named calls. Running student Python is
 * the entire feature; the containment is that it cannot reach anything.
 */

export const WORKER_PYTHON = `
import asyncio
import inspect
import sys
import traceback

import citxr
from citxr import Bridge, program, run_interval, set_bridge
from citxr.api import _reset_devices


class HostTransport:
    """Posts one RPC to the page and waits for its answer."""

    def __init__(self, send):
        self._send = send

    async def call(self, method, payload):
        result = await self._send(method, dict(payload))
        # The page answers with a JavaScript object, which arrives as a JsProxy.
        # Student code and the bridge both expect a real mapping, so convert
        # before anyone calls .get() on it.
        to_py = getattr(result, "to_py", None)
        if to_py is not None:
            result = to_py()
        return result if isinstance(result, dict) else dict(result or {})


class _Capture:
    """Sends print() to the Studio console instead of nowhere."""

    def __init__(self, emit, stream):
        self._emit = emit
        self._stream = stream

    def write(self, text):
        if text:
            self._emit(self._stream, text)
        return len(text)

    def flush(self):
        return None


async def run_student_program(source, send, emit, interval_iterations):
    """Execute the student's module, then drive what it registered."""

    _reset_devices()
    program().clear()
    bridge = Bridge(HostTransport(send))
    set_bridge(bridge)

    stdout, stderr = sys.stdout, sys.stderr
    sys.stdout = _Capture(emit, "stdout")
    sys.stderr = _Capture(emit, "stderr")

    namespace = {"__name__": "__student__"}
    try:
        # Compile separately so a syntax error reports the student's filename
        # and line rather than pointing inside this harness.
        compiled = compile(source, "student_program.py", "exec")
        exec(compiled, namespace)

        main = namespace.get("main")
        if main is not None and inspect.iscoroutinefunction(main):
            await main()

        for subscription in list(program().intervals):
            await run_interval(subscription, iterations=interval_iterations)

        return {"ok": True}
    except citxr.CancelledError:
        return {"ok": True, "cancelled": True}
    except BaseException as error:  # noqa: BLE001 - reported, never swallowed
        line = None
        for frame in traceback.extract_tb(error.__traceback__):
            if frame.filename == "student_program.py":
                line = frame.lineno
        if line is None and isinstance(error, SyntaxError):
            line = error.lineno
        return {
            "ok": False,
            "errorType": type(error).__name__,
            "message": str(error),
            "line": line,
            "traceback": "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ),
        }
    finally:
        sys.stdout, sys.stderr = stdout, stderr


def cancel_student_program():
    from citxr.bridge import _ACTIVE

    if _ACTIVE:
        _ACTIVE[0].cancel()
`;
