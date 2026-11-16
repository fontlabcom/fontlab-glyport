# this_file: tests/test_issue106_round12.py
"""Reference minor versions and cwd restoration under failed scope cleanup."""

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from fontlab_glyport.entrypoints import _native_host
from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.execution import ExecutionContext
from fontlab_glyport.glyphsapp.fontlab_bridge import FontLabGlyphsBridge
from fontlab_glyport.profiles import select_profile


@pytest.mark.parametrize(
    "guard",
    [
        "if Glyphs.versionNumber < 4.1: raise SystemExit(1)",
        "minimum = 4.1\nif Glyphs.versionNumber < minimum: raise SystemExit(1)",
        "if 4.1 > Glyphs.versionNumber: raise SystemExit(1)",
    ],
)
def test_f48_reference_minor_guard_selects_glyphs4(guard):
    assert select_profile(sources={"script.py": guard.encode()}).profile == "glyphs4"


def test_f48_native_adapter_exposes_full_reference_version_host_free(
    tmp_path, monkeypatch
):
    # _native_host creates lazy adapters; injecting import sentinels requires no host.
    monkeypatch.setitem(sys.modules, "fontlab", NS())
    monkeypatch.setitem(sys.modules, "PythonQt", NS(QtGui=NS()))
    context = ExecutionContext(tmp_path, "glyphs4", implicit_imports=("GlyphsApp",))
    context.adapters.update(_native_host().adapter_factory(context, None))
    path = tmp_path / "main.py"
    path.write_text(
        "if Glyphs.versionNumber < 4.1: raise SystemExit(1)\n"
        "seen = (Glyphs.versionNumber, Glyphs.versionString, Glyphs.buildNumber)\n"
    )
    try:
        stage = context.run(path)
        assert stage.status == "passed"
        assert context.globals["seen"] == (4.1, "4.1.1", 4108)
        assert context.fontlab_session.bridge.version_number() == 4.1
    finally:
        context.close()


def test_f49_cleanup_failure_cannot_skip_cwd_restoration(tmp_path, monkeypatch):
    caller, scripts = tmp_path / "caller", tmp_path / "scripts"
    caller.mkdir()
    scripts.mkdir()
    monkeypatch.chdir(caller)
    original_path, original_finders = sys.path, list(sys.meta_path)
    original_modules = dict(sys.modules)
    context = ExecutionContext(tmp_path, "glyphs4")
    path = scripts / "main.py"
    path.write_text(
        "import sys\nsys.path = None\nraise ValueError('original failure')\n"
    )
    try:
        with pytest.raises((TypeError, ValueError)):
            context.run(path)
        assert Path.cwd() == caller, "cwd restoration is independent of path collection"
        assert sys.path == original_path, "scope teardown still restores import paths"
        assert context._finder not in sys.meta_path
        assert context.namespace not in sys.modules
    finally:
        # Keep a red test run from leaking the intentionally corrupted process state.
        sys.path = original_path
        sys.meta_path[:] = original_finders
        for name in tuple(sys.modules):
            if name == context.namespace or name.startswith(context.namespace + "."):
                sys.modules.pop(name)
        sys.modules.update(original_modules)
        context.close()


def test_f49_failed_scope_cleanup_restores_paths_without_retaining_new_modules(
    tmp_path,
):
    (tmp_path / "helper.py").write_text("value = 1\n")
    context = ExecutionContext(tmp_path, "glyphs4")
    original_path = sys.path
    try:
        with pytest.raises(TypeError), context:
            context.import_module("helper")
            sys.path = None
        assert sys.path == original_path
        assert context._modules == {}, "a failed scope must not retain its new imports"
        assert context._finder not in sys.meta_path
    finally:
        sys.path = original_path
        context.close()


def test_f48_custom_version_keeps_explicit_patch_text_and_unknown_patch_refuses():
    custom = FontLabGlyphsBridge(
        log=lambda text: None, version=(4.2, 4201), version_string="4.2.3"
    )
    assert (
        custom.version_number(),
        custom.version_string(),
        custom.build_number(),
    ) == (4.2, "4.2.3", 4201)
    missing = FontLabGlyphsBridge(log=lambda text: None, version=(4.2, 4201))
    with pytest.raises(UnsupportedCapability) as caught:
        missing.version_string()
    assert caught.value.capability == "Glyphs.versionString"
