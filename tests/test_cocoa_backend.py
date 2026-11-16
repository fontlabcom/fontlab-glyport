# this_file: tests/test_cocoa_backend.py
"""Backend routing uses injected modules; native acceptance is separate."""

import sys
from types import ModuleType

import pytest

from fontlab_glyport import cocoa_backend as backend
from fontlab_glyport.execution import ExecutionContext


def test_windows_auto_never_imports_native(monkeypatch):
    monkeypatch.setattr(backend.sys, "platform", "win32")
    monkeypatch.setattr(backend.importlib, "import_module", lambda n: pytest.fail(n))
    assert backend.select_backend("auto")[0] == "qt"
    with pytest.raises(ImportError, match="macOS"):
        backend.select_backend("native")


def test_missing_native_fallback_and_explicit_error(monkeypatch):
    monkeypatch.setattr(backend.sys, "platform", "darwin")

    def missing(name):
        raise ModuleNotFoundError("missing objc")

    monkeypatch.setattr(backend.importlib, "import_module", missing)
    selected, reason, modules = backend.select_backend("auto")
    assert selected == "qt" and "missing objc" in reason and not modules
    with pytest.raises(ImportError, match="missing objc"):
        backend.select_backend("native")


@pytest.mark.parametrize("choice", ["auto", "native"])
def test_native_scoped_identity_metadata_and_lazy_lookup(
    tmp_path, monkeypatch, choice, cocoa_modules
):
    monkeypatch.setattr(backend.sys, "platform", "darwin")
    modules = cocoa_modules()
    sentinel = modules["AppKit"].NSColor
    before = dict(vars(modules["AppKit"]))
    context = ExecutionContext(tmp_path, "glyphs4")
    context.configure_cocoa(choice)
    with context:
        assert context.import_module("AppKit") is modules["AppKit"]
        assert context._import("AppKit", fromlist=("NSColor",)).NSColor is sentinel
    context.close()
    assert vars(modules["AppKit"]) == before
    assert sys.modules["AppKit"] is modules["AppKit"]


def test_invalid_backend():
    with pytest.raises(ValueError, match="cocoa_backend"):
        backend.select_backend("other")


def test_scoped_force_qt_masks_native_and_restores(
    tmp_path, monkeypatch, cocoa_modules
):
    native = cocoa_modules()["AppKit"]
    child = ModuleType("AppKit.child")
    child.__file__ = "/scratch/.local/glyport-80-native/AppKit/child.py"
    monkeypatch.setitem(sys.modules, "AppKit", native)
    monkeypatch.setitem(sys.modules, "AppKit.child", child)
    context = ExecutionContext(tmp_path, "glyphs4")
    context.configure_cocoa("qt")
    with context:
        assert sys.modules["AppKit"] is context.import_module("AppKit")
        assert "AppKit.child" not in sys.modules
    assert sys.modules["AppKit"] is native
    assert sys.modules["AppKit.child"] is child
    context.close()


@pytest.mark.parametrize("choice", ["auto", "native"])
def test_scoped_rejects_cached_foreign_modules(tmp_path, monkeypatch, choice):
    monkeypatch.setattr(sys, "platform", "darwin")
    modules = {name: ModuleType(name) for name in backend.COCOA_ROOTS}
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    context = ExecutionContext(tmp_path, "glyphs4")
    with pytest.raises(ImportError, match="collision|genuine"):
        context.configure_cocoa(choice)
    context.close()
    assert all(sys.modules[name] is module for name, module in modules.items())


@pytest.mark.parametrize("preloaded", [False, True])
def test_forced_qt_routes_ordinary_cold_helper(
    tmp_path, monkeypatch, preloaded, cocoa_modules
):
    import importlib

    helper = tmp_path / "external_cocoa_helper.py"
    helper.write_text(
        "import importlib\ndef load():\n return importlib.import_module('Cocoa')\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "Cocoa", raising=False)
    if preloaded:
        cocoa_modules(roots=("objc",))
    context = ExecutionContext(tmp_path, "glyphs4")
    context.configure_cocoa("qt")
    with context:
        imported = importlib.import_module("external_cocoa_helper")
        assert imported.load() is context.import_module("Cocoa")
    assert "Cocoa" not in sys.modules
    sys.modules.pop("external_cocoa_helper", None)
    context.close()


@pytest.mark.parametrize(
    "base", ["/scratch/site-packages", "/scratch/.local/glyport-80-native"]
)
def test_native_provenance_independent_of_install_directory(
    base, cocoa_modules, monkeypatch
):
    modules = cocoa_modules(base)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert all(backend.native_module(name, module) for name, module in modules.items())
    assert backend.select_backend("native")[0] == "native"
    foreign = ModuleType("AppKit.foreign")
    foreign.__file__ = "/unrelated/AppKit/foreign.py"
    assert not backend.native_module("AppKit.foreign", foreign)


def test_matching_auto_request_reuses_retained_selection(tmp_path, monkeypatch):
    calls = []

    def choose(request):
        calls.append(request)
        return (
            ("qt", "fixture missing native dependency", {})
            if len(calls) == 1
            else ("native", None, {})
        )

    monkeypatch.setattr(backend, "select_backend", choose)
    first = ExecutionContext(tmp_path, "glyphs4")
    second = ExecutionContext(tmp_path, "glyphs4")
    try:
        first.configure_cocoa("auto")
        second.configure_cocoa("auto")
        assert second.cocoa_backend == "qt"
        assert second.cocoa_fallback_reason == first.cocoa_fallback_reason
        assert calls == ["auto"]
    finally:
        first.close()
        second.close()
