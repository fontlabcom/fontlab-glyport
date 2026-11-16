# this_file: tests/test_runtime_routes.py
"""Owned fixtures cover imports, archive and process failure paths."""

import importlib.util
import marshal
import sys
import threading
import zipfile
from types import ModuleType

import pytest

from fontlab_glyport import ExecutionContext, UnsupportedCapability
from fontlab_glyport.adaptation_entries import (
    PY311_MAGIC,
    check_pyc,
    read_code,
    unpack_archive,
)
from fontlab_glyport.dependencies import dependency_route, request_service, run_process
from fontlab_glyport.errors import Cancelled, DependencyUnavailable


def test_modern_imports_retained_for_callbacks(tmp_path):
    source = tmp_path / "main.py"
    source.write_text(
        "from AppKit import NSMakePoint\nfrom Foundation import NSMakeRange\nimport Cocoa, objc\n@objc.python_method\ndef callback():\n from AppKit import NSMakeRect\n return NSMakeRect(1,2,3,4).origin.x + NSMakePoint(5,6).y + NSMakeRange(0,2).length\n"
    )
    previous = sys.modules.get("AppKit")
    host = ModuleType("AppKit")
    sys.modules["AppKit"] = host
    try:
        for profile in ("glyphs3", "glyphs4"):
            ctx = ExecutionContext(tmp_path, profile)
            ctx.run(source)
            callback = ctx.wrap(ctx.globals["callback"])
            assert callback() == 9
            assert sys.modules["AppKit"] is host
            ctx.close()
            with pytest.raises(RuntimeError):
                callback()
    finally:
        if previous is None:
            sys.modules.pop("AppKit", None)
        else:
            sys.modules["AppKit"] = previous


def test_unknown_selector_source_location(tmp_path):
    source = tmp_path / "main.py"
    source.write_text("from AppKit import NSApplication\n")
    with pytest.raises(UnsupportedCapability) as caught:
        ExecutionContext(tmp_path, "glyphs3").run(source)
    assert caught.value.capability == "AppKit.NSApplication"
    assert caught.value.location.path == str(source)


def test_pyc_checks_311_magic_and_corruption(tmp_path):
    assert check_pyc(PY311_MAGIC + bytes(12)) == "3.11"
    for raw in (b"", b"abcd" + bytes(12), b"\xf3\x03\r\n" + bytes(12)):
        with pytest.raises(DependencyUnavailable, match="3.11"):
            check_pyc(raw)
    path = tmp_path / "bad.pyc"
    path.write_bytes(PY311_MAGIC + bytes(12) + b"invalid marshal")
    with pytest.raises(DependencyUnavailable):
        read_code(path)


@pytest.mark.skipif(sys.version_info[:2] != (3, 11), reason="3.11 VM required")
def test_sourceless_pyc_execution(tmp_path):
    path = tmp_path / "script.pyc"
    path.write_bytes(
        importlib.util.MAGIC_NUMBER
        + bytes(12)
        + marshal.dumps(compile("value = 42", "script.py", "exec"))
    )
    ctx = ExecutionContext(tmp_path, "glyphs3")
    assert ctx.run(path).status == "passed"
    assert ctx.globals["value"] == 42
    ctx.close()


def test_archive_scoped_imports(tmp_path):
    archive = tmp_path / "dependency313.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("helper/__init__.py", "from .child import value\n")
        z.writestr("helper/child.py", "value = 42\n")
    original = archive.read_bytes()
    root = unpack_archive(archive, tmp_path / "owned")
    source = tmp_path / "main.py"
    source.write_text(
        "import helper\ndef callback():\n from helper import value\n return value\n"
    )
    ctx = ExecutionContext(tmp_path, "glyphs3", dependency_paths=(root,))
    ctx.run(source)
    assert ctx.wrap(ctx.globals["callback"])() == 42
    assert archive.read_bytes() == original
    assert "helper" not in sys.modules
    ctx.close()


@pytest.mark.parametrize(
    "member", ["../escape.py", "/absolute.py", "a/../../escape.py", "a\\evil.py"]
)
def test_archive_rejects_unsafe_members(tmp_path, member):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(member, "pass")
    with pytest.raises(DependencyUnavailable):
        unpack_archive(archive, tmp_path / "owned")
    assert not (tmp_path / "owned").exists()


def test_archive_checks_magic_not_filename(tmp_path):
    archive = tmp_path / "dependency311.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("module.pyc", b"bad!" + bytes(20))
    with pytest.raises(DependencyUnavailable, match="3.11"):
        unpack_archive(archive, tmp_path / "owned")
    assert not (tmp_path / "owned").exists()


def test_dependency_routes():
    assert dependency_route("fontTools.ttLib").route == "python"
    assert dependency_route("fontParts.world").route == "python"
    assert dependency_route("drawBot").route == "adapter-required"
    assert "DrawBot" in dependency_route("drawBot").message


def test_process_outcomes():
    assert (
        run_process([sys.executable, "-c", "print(42)"], timeout=2).stdout.strip()
        == "42"
    )
    with pytest.raises(DependencyUnavailable, match="exit 7") as caught:
        run_process(
            [
                sys.executable,
                "-c",
                "import sys; print('bad',file=sys.stderr); sys.exit(7)",
            ],
            timeout=2,
        )
    assert "bad" in caught.value.stderr
    with pytest.raises(DependencyUnavailable, match="timed out"):
        run_process([sys.executable, "-c", "import time; time.sleep(3)"], timeout=0.05)
    event = threading.Event()
    timer = threading.Timer(0.05, event.set)
    timer.start()
    try:
        with pytest.raises(Cancelled):
            run_process(
                [sys.executable, "-c", "import time; time.sleep(3)"],
                timeout=2,
                cancelled=event.is_set,
            )
    finally:
        timer.join()
    with pytest.raises(DependencyUnavailable, match="start"):
        run_process(["/nonexistent/glyport-process"], timeout=1)


def test_service_error_and_cancel():
    with pytest.raises(Cancelled):
        request_service("http://localhost/", timeout=0.1, cancelled=lambda: True)

    def fail(url, timeout):
        raise TimeoutError("fixture")

    with pytest.raises(DependencyUnavailable, match="service"):
        request_service("http://localhost/", timeout=0.1, transport=fail)
