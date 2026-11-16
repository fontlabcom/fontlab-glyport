# this_file: tests/test_runtime_review_fixes.py
"""Regression cases for every R-L3 review finding; no native host is required."""

import os
import plistlib
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import ModuleType

import pytest
from ui_doubles import make_qt

from fontlab_glyport import install_plugin, run_script
from fontlab_glyport.dependencies import process_adapter, request_service, run_process
from fontlab_glyport.entrypoints import (
    ExecutionHost,
    PluginRegistration,
    _snapshot_adaptation,
)
from fontlab_glyport.errors import (
    Cancelled,
    DependencyUnavailable,
    UnsupportedCapability,
)
from fontlab_glyport.profiles import select_profile
from fontlab_glyport.receipt import ReceiptEnvironment


def fixture_host():
    return ExecutionHost(
        lambda operation: operation(),
        ReceiptEnvironment("fixture", "1", "3.11", "5.15", "test", "test"),
    )


def bundle(tmp_path):
    root = tmp_path / "Fixture.glyphsPlugin"
    (root / "Contents/Resources").mkdir(parents=True)
    (root / "Contents/Info.plist").write_bytes(
        plistlib.dumps(
            {
                "GlyphsVersion": "3",
                "NSPrincipalClass": "Fixture",
                "PyMainFileNames": ["plugin.py"],
            }
        )
    )
    (root / "Contents/Resources/plugin.py").write_text(
        "class Fixture: pass\nhits = []\ndef unload():\n from AppKit import NSMakePoint\n hits.append(NSMakePoint(2, 3).x)\n"
    )
    return root


@pytest.mark.parametrize("valid", [True, False])
def test_plugin_teardown_and_rollback_run_in_context(tmp_path, valid):
    host = fixture_host()
    hits = []

    def register(context, assessment):
        hits.append(context.globals["hits"])
        return PluginRegistration(
            context.globals["unload"], evidence=("fixture:hook",) if valid else ()
        )

    host.plugin_installer = register
    if valid:
        handle = install_plugin(bundle(tmp_path), host=host)
        handle.unload()
    else:
        with pytest.raises(UnsupportedCapability, match="evidence"):
            install_plugin(bundle(tmp_path), host=host)
    assert hits == [[2]], "unload must retain scoped imports on success and rollback"


def install_native_doubles(monkeypatch):
    qt = make_qt()
    monkeypatch.setattr(
        qt.QtGui.QApplication, "instance", staticmethod(lambda: object()), raising=False
    )
    monkeypatch.setitem(sys.modules, "PythonQt", qt)
    monkeypatch.setitem(sys.modules, "fontlab", ModuleType("fontlab"))
    return qt


def test_default_native_vanilla_callback_and_window_teardown(tmp_path, monkeypatch):
    install_native_doubles(monkeypatch)
    source = tmp_path / "window.py"
    source.write_text(
        "# GLYPHS_VERSION: 3\nfrom vanilla import Window, Button\nhits=[]\ndef click(sender):\n from AppKit import NSMakePoint\n hits.append(NSMakePoint(4,5).x)\nw=Window((200,100), 'owned')\nw.b=Button((10,10,80,20), 'Go', callback=click)\nw.open()\n"
    )
    handle = run_script(source)
    window, hits = handle.context.globals["w"], handle.context.globals["hits"]
    native = window.getNSWindow()
    try:
        window.b.getNSView().user_click()
        assert hits == [4]
        assert window in handle.windows
    finally:
        handle.close()
    assert native._deleted, "closing the public handle must retire Vanilla windows"


def test_default_native_registrar_present_and_absent(tmp_path, monkeypatch):
    install_native_doubles(monkeypatch)
    monkeypatch.setitem(sys.modules, "fontlab_glyport.plugins", None)
    root = bundle(tmp_path)
    with pytest.raises(
        UnsupportedCapability, match=r"fontlab_glyport.plugins.register_plugin"
    ):
        install_plugin(root)
    plugins = ModuleType("fontlab_glyport.plugins")
    called = []

    def register_plugin(context, assessment):
        called.append(assessment.principal_class)
        return PluginRegistration(
            context.globals["unload"], evidence=("fixture:native-registrar",)
        )

    plugins.register_plugin = register_plugin
    monkeypatch.setitem(sys.modules, "fontlab_glyport.plugins", plugins)
    handle = install_plugin(root)
    hits = handle.context.globals["hits"]
    handle.close()
    assert called == ["Fixture"]
    assert hits == [2]


def test_adaptation_warnings_survive_snapshots_and_close(tmp_path):
    source = tmp_path / "legacy.py"
    source.write_text("print 'owned-string'\n")
    handle = run_script(source, profile="glyphs2", host=fixture_host())
    _snapshot_adaptation(handle)
    warnings = [
        d
        for d in handle.receipt.diagnostics
        if d.code in {"PY2_STRING_AMBIGUITY", "PY2_SEMANTIC_REVIEW"}
    ]
    assert {d.code for d in warnings} == {"PY2_STRING_AMBIGUITY", "PY2_SEMANTIC_REVIEW"}
    assert all(
        d.location.path == str(source) and d.location.line == 1 for d in warnings
    )
    assert len(warnings) == len(set(warnings)), (
        "repeated snapshots must not duplicate warnings"
    )
    handle.close()
    assert all(d in handle.receipt.diagnostics for d in warnings)


@pytest.mark.parametrize(
    "raw", [b"# coding: no-such-codec\npass", b"# coding: ascii\ntext='\xff'\n"]
)
@pytest.mark.parametrize("override", ["auto", "glyphs3"])
def test_invalid_encoding_returns_profile_diagnostic(raw, override):
    result = select_profile(sources={"broken.py": raw}, override=override)
    errors = [d for d in result.diagnostics if d.code == "PROFILE_ENCODING_ERROR"]
    assert errors and errors[0].path == "broken.py"


@pytest.mark.skipif(os.name != "posix", reason="POSIX signals")
@pytest.mark.parametrize("check", [False, True])
def test_signal_exit_obeys_subprocess_check(check):
    adapter = process_adapter(lambda: False)
    args = [
        sys.executable,
        "-c",
        "import os,signal; os.kill(os.getpid(), signal.SIGTERM)",
    ]
    if check:
        with pytest.raises(subprocess.CalledProcessError) as caught:
            adapter.run(args, timeout=1, check=True)
        assert caught.value.returncode == -signal.SIGTERM
    else:
        assert adapter.run(args, timeout=1).returncode == -signal.SIGTERM


@pytest.mark.skipif(os.name != "posix", reason="POSIX sessions")
def test_process_cleanup_does_not_wait_for_escaped_descendant_eof():
    # The escaped grandchild keeps stdout open for 30 s; cleanup that waited for
    # its EOF would overrun the bound below by ~28 s. The 1 s deadline leaves the
    # child time to print the pid even when fork() is slow: fork cost grows with
    # the parent's RSS, and late in a full suite an 0.08 s deadline killed the
    # child before it printed (int('') here; reproduced with 4 GB of ballast).
    timeout = 1.0
    code = "import subprocess,sys,time; child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'], start_new_session=True); print(child.pid,flush=True); time.sleep(60)"
    started = time.monotonic()
    pid = None
    try:
        with pytest.raises(DependencyUnavailable) as caught:
            run_process([sys.executable, "-c", code], timeout=timeout)
        elapsed = time.monotonic() - started
        stdout = caught.value.stdout
        assert stdout.strip().isdigit(), (
            f"child printed no pid within {timeout} s: {stdout!r}"
        )
        pid = int(stdout.strip())
        assert elapsed < timeout + 0.6, "cleanup must not await descendant EOF"
    finally:
        if pid:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.fixture
def trickle_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                self.send_response(200)
                self.send_header("Content-Length", "12")
                self.end_headers()
                for index in range(12):
                    self.wfile.write(b"x")
                    self.wfile.flush()
                    time.sleep(0.03)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_http_enforces_overall_deadline_on_trickling_body(trickle_server):
    started = time.monotonic()
    with pytest.raises(DependencyUnavailable, match="service"):
        request_service(trickle_server, timeout=0.09)
    assert time.monotonic() - started < 0.25


def test_http_checks_cancel_between_incremental_reads(trickle_server):
    event = threading.Event()
    timer = threading.Timer(0.05, event.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(Cancelled):
            request_service(trickle_server, timeout=1, cancelled=event.is_set)
        assert time.monotonic() - started < 0.25
    finally:
        timer.join()


def test_http_truncated_content_length_reports_dependency_unavailable():
    from http.client import IncompleteRead

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "10")
            self.end_headers()
            self.wfile.write(b"abc")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        with pytest.raises(DependencyUnavailable) as caught:
            request_service(f"http://127.0.0.1:{server.server_port}/", timeout=1)
        assert caught.value.capability == "service:external"
        assert isinstance(caught.value.__cause__, IncompleteRead)
        assert caught.value.__cause__.partial == b"abc"
        assert caught.value.__cause__.expected == 7
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
