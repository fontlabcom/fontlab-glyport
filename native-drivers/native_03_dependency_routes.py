# this_file: native-drivers/native_03_dependency_routes.py
"""Check bytecode/ZIP routes and bounded process/service outcomes in FontLab."""

import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from driver_common import Driver


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/error":
            self.send_error(503)
            return
        self.send_response(200)
        self.end_headers()
        if self.path == "/slow":
            time.sleep(0.15)
        try:
            self.wfile.write(b"glyport-controlled-service")
        except BrokenPipeError:
            pass

    def log_message(self, *args):
        pass


with Driver(
    "Python 3.11 bytecode, ZIP, dependency and controlled service routes"
) as driver:
    driver.call(
        "bytecode magic and owned execution",
        """
import importlib.util, marshal
from fly.gp import ExecutionContext
from fly.gp.adaptation_entries import check_pyc
from fly.gp.errors import DependencyUnavailable
assert sys.version_info[:2] == (3, 11)
source = state.root / "bytecode.pyc"
source.write_bytes(importlib.util.MAGIC_NUMBER + bytes(12) + marshal.dumps(compile("value=42", "owned-bytecode.py", "exec")))
context = ExecutionContext(state.root, "glyphs3")
state.contexts.append(context)
assert context.run(source).status == "passed"
assert context.globals["value"] == 42
try:
    check_pyc(b"bad!" + bytes(12))
except DependencyUnavailable:
    pass
else:
    raise AssertionError("foreign bytecode accepted")
result = {"bytecode_value": 42, "foreign_magic_rejected": True}
""",
    )
    driver.call(
        "ZIP contents and retained imports",
        """
import zipfile
from fly.gp import ExecutionContext
from fly.gp.adaptation_entries import unpack_archive
archive = state.root / "misleading313.zip"
with zipfile.ZipFile(archive, "w") as stream:
    stream.writestr("owned_helper.py", "value=43")
root = unpack_archive(archive, state.root / "archive")
source = state.root / "archive_main.py"
source.write_text("import owned_helper\\ndef callback():\\n from owned_helper import value\\n return value\\n")
context = ExecutionContext(state.root, "glyphs4", dependency_paths=(root,))
state.contexts.append(context)
context.run(source)
assert context.wrap(context.globals["callback"])() == 43
from fly.gp.dependencies import dependency_route
assert dependency_route("drawBot").route == "adapter-required"
assert dependency_route("fontTools.ttLib").route == "python"
assert dependency_route("fontParts.world").route == "python"
result = {"zip_value": 43, "drawbot": "explicit backend required", "fontTools_fontParts": "python route; availability not claimed"}
""",
    )
    driver.call(
        "process success error timeout and cancel",
        """
from fly.gp.dependencies import run_process
from fly.gp.errors import Cancelled, DependencyUnavailable
assert run_process([process_python, "-c", "print(44)"], timeout=.8).stdout.strip() == "44"
for code, timeout in (("raise SystemExit(7)", .8), ("import time; time.sleep(3)", .05)):
    try:
        run_process([process_python, "-c", code], timeout=timeout)
    except DependencyUnavailable:
        pass
    else:
        raise AssertionError("process failure was lost")
try:
    run_process([process_python, "-c", "pass"], timeout=.5, cancelled=lambda: True)
except Cancelled:
    pass
else:
    raise AssertionError("cancellation was lost")
import threading
event = threading.Event()
timer = threading.Timer(.03, event.set)
timer.start()
try:
    run_process([process_python, "-c", "import time; time.sleep(3)"], timeout=.8, cancelled=event.is_set)
except Cancelled:
    pass
else:
    raise AssertionError("in-flight cancellation was lost")
finally:
    timer.join()
result = {"success": 44, "nonzero_timeout_cancel": "typed"}
""",
        process_python=sys.executable,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        driver.call(
            "local controlled HTTP success and failure",
            """
from fly.gp.dependencies import request_service
from fly.gp.errors import Cancelled, DependencyUnavailable
assert request_service(endpoint, timeout=.3) == b"glyport-controlled-service"
try:
    request_service(endpoint + "error", timeout=.3)
except DependencyUnavailable:
    pass
else:
    raise AssertionError("HTTP 503 accepted")
try:
    request_service(endpoint + "slow", timeout=.03)
except DependencyUnavailable:
    pass
else:
    raise AssertionError("HTTP timeout was lost")
try:
    request_service(endpoint, timeout=.3, cancelled=lambda: True)
except Cancelled:
    pass
else:
    raise AssertionError("service cancellation lost")
result = {"controlled_http": "passed", "remote_services": "unexecuted"}
""",
            endpoint=f"http://127.0.0.1:{server.server_port}/",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
