# this_file: src/fontlab_glyport/dependencies.py
"""Dependency-specific routes and bounded external process/service operations."""

import http.client
import io
import math
import os
import signal
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import HTTPHandler, HTTPSHandler, build_opener

from .errors import Cancelled, DependencyUnavailable


@dataclass(frozen=True)
class DependencyRoute:
    module: str
    route: str
    message: str


def dependency_route(module: str) -> DependencyRoute:
    root = module.split(".")[0]
    if root in {"drawBot", "drawbot"}:
        return DependencyRoute(
            module,
            "adapter-required",
            "DrawBot requires an explicitly configured rendering backend; native AppKit loading is unavailable.",
        )
    if root in {"fontTools", "fontParts", "robofab"}:
        return DependencyRoute(
            module,
            "python",
            f"{root} requires an importable Python dependency compatible with the host ABI; no automatic installation.",
        )
    return DependencyRoute(
        module,
        "python",
        f"Resolve {module} through owned dependency paths or the host interpreter.",
    )


def _deadline(timeout: float) -> float:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    return time.monotonic() + timeout


def _cancel(cancelled: Callable[[], bool]) -> None:
    if cancelled():
        raise Cancelled("External dependency operation cancelled.")


def _cleanup_process(process) -> tuple[str, str]:
    """Bound pipe draining independently of escaped descendants holding EOF."""
    try:
        return process.communicate(timeout=0.05)
    except subprocess.TimeoutExpired as error:
        stdout, stderr = error.output or "", error.stderr or ""
        for pipe in (process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()
        # Only reap the killed direct child, never wait on descendant pipes.
        process.wait(timeout=0.1)
        return tuple(
            value.decode(errors="replace") if isinstance(value, bytes) else value
            for value in (stdout, stderr)
        )


def run_process(
    argv: Sequence[str],
    *,
    timeout: float,
    cancelled: Callable[[], bool] = lambda: False,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    """Run explicit argv without a shell; kill/reap on timeout, cancel or error."""
    deadline = _deadline(timeout)
    if isinstance(argv, (str, bytes)) or not argv:
        raise ValueError("argv must be a nonempty sequence, never a shell string")
    _cancel(cancelled)
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=os.name == "posix",
        )
    except OSError as error:
        raise DependencyUnavailable(
            f"Cannot start external process {argv[0]}: {error}",
            capability="process:external",
        ) from error
    try:
        while True:
            _cancel(cancelled)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DependencyUnavailable(
                    "External process timed out.", capability="process:external"
                )
            try:
                stdout, stderr = process.communicate(timeout=min(0.05, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
    except BaseException as error:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        try:
            stdout, stderr = _cleanup_process(process)
        except (OSError, subprocess.TimeoutExpired) as cleanup_error:
            error.cleanup_error = cleanup_error
            stdout, stderr = "", ""
        if isinstance(error, (Cancelled, DependencyUnavailable)):
            error.stdout, error.stderr, error.returncode = (
                stdout,
                stderr,
                process.returncode,
            )
        raise
    if process.returncode:
        error = DependencyUnavailable(
            f"External process exit {process.returncode}: {stderr.strip()}",
            capability="process:external",
        )
        error.returncode, error.stdout, error.stderr = (
            process.returncode,
            stdout,
            stderr,
        )
        error.completed = True
        raise error
    return subprocess.CompletedProcess(list(argv), process.returncode, stdout, stderr)


def _remaining(deadline: float, cancelled: Callable[[], bool]) -> float:
    _cancel(cancelled)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("service overall deadline exceeded")
    return remaining


class _DeadlineReader(io.RawIOBase):
    """Bound every socket read, including trickling HTTP headers/chunk framing."""

    def __init__(self, sock, deadline, cancelled):
        self.sock, self.deadline, self.cancelled = sock, deadline, cancelled
        self.raw = sock.makefile("rb", buffering=0)

    def readable(self):
        return True

    def readinto(self, buffer):
        self.sock.settimeout(_remaining(self.deadline, self.cancelled))
        return self.raw.readinto(buffer)

    def close(self):
        try:
            self.raw.close()
        finally:
            super().close()


class _DeadlineSocket:
    def __init__(self, sock, deadline, cancelled):
        self.sock, self.deadline, self.cancelled = sock, deadline, cancelled

    def __getattr__(self, name):
        return getattr(self.sock, name)

    def makefile(self, mode):
        if mode != "rb":
            raise ValueError("HTTP response must be read as binary")
        return io.BufferedReader(
            _DeadlineReader(self.sock, self.deadline, self.cancelled)
        )


def _http(url: str, deadline: float, cancelled: Callable[[], bool]) -> bytes:
    def connection(base):
        class DeadlineConnection(base):
            def connect(self):
                self.timeout = _remaining(deadline, cancelled)
                super().connect()
                self.sock = _DeadlineSocket(self.sock, deadline, cancelled)

        return DeadlineConnection

    class HTTP(HTTPHandler):
        def http_open(self, request):
            return self.do_open(connection(http.client.HTTPConnection), request)

    class HTTPS(HTTPSHandler):
        def https_open(self, request):
            return self.do_open(connection(http.client.HTTPSConnection), request)

    opener = build_opener(HTTP(), HTTPS())
    with opener.open(url, timeout=_remaining(deadline, cancelled)) as response:
        chunks = []
        while True:
            _remaining(deadline, cancelled)
            chunk = response.read1(65536)
            if not chunk:
                if response.length is not None and response.length > 0:
                    raise http.client.IncompleteRead(b"".join(chunks), response.length)
                return b"".join(chunks)
            chunks.append(chunk)


def request_service(
    url: str,
    *,
    timeout: float,
    cancelled: Callable[[], bool] = lambda: False,
    transport: Callable | None = None,
) -> bytes:
    """Read HTTP incrementally with one deadline and cancellation between reads.

    Injected two-argument transports own their blocking I/O. The default also
    bounds individual header/body socket reads by the remaining overall time.
    """
    deadline = _deadline(timeout)
    if not url.startswith(("http://", "https://")):
        raise ValueError("service URL must use http or https")
    _cancel(cancelled)
    try:
        result = (
            transport(url, _remaining(deadline, cancelled))
            if transport
            else _http(url, deadline, cancelled)
        )
        _remaining(deadline, cancelled)
    except (OSError, URLError, http.client.HTTPException) as error:
        _cancel(cancelled)
        raise DependencyUnavailable(
            f"External service failed: {error}", capability="service:external"
        ) from error
    _cancel(cancelled)
    return result


def process_adapter(cancelled: Callable[[], bool], translate=None):
    """Provide bounded subprocess.run; Popen/shell modes require a host adapter.

    Stdlib subprocess imports in unrelated host code retain their own module.
    A missing deadline fails before spawning instead of blocking the host loop.
    """
    from .execution import placeholder

    module = placeholder("subprocess", translate)

    def run(
        args,
        *,
        timeout=None,
        cwd=None,
        capture_output=True,
        text=True,
        check=False,
        **options,
    ):
        if timeout is None:
            raise DependencyUnavailable(
                "subprocess.run requires an explicit timeout in FontLab.",
                capability="process:external",
            )
        if options or not capture_output or not text:
            raise DependencyUnavailable(
                "subprocess.run supports captured text output and explicit argv; configure a host process adapter for other options.",
                capability="process:external",
            )
        try:
            return run_process(args, timeout=timeout, cwd=cwd, cancelled=cancelled)
        except DependencyUnavailable as error:
            if getattr(error, "completed", False):
                if check:
                    raise subprocess.CalledProcessError(
                        error.returncode, args, error.stdout, error.stderr
                    ) from error
                return subprocess.CompletedProcess(
                    args, error.returncode, error.stdout, error.stderr
                )
            raise

    module.run = run
    module.CompletedProcess = subprocess.CompletedProcess
    module.CalledProcessError = subprocess.CalledProcessError
    module.__all__ = ("run", "CompletedProcess", "CalledProcessError")
    return module
