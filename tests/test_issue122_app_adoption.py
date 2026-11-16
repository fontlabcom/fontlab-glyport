# this_file: tests/test_issue122_app_adoption.py
"""Glyport uses App's affine, editor_painters and qtsafe; it keeps no copies (issue 122 T6)."""

import importlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import fontlabapp.contours.affine as app_affine
import fontlabapp.qt.painting.editor as app_painters
import pytest

import fontlab_glyport
from fontlab_glyport.errors import HostUnavailable, UnsupportedCapability

SRC = Path(fontlab_glyport.__file__).resolve().parent


def test_context_when_imported_then_affine_helpers_are_the_app_functions():
    from fontlab_glyport.drawing import context

    for name in ("concat", "invert", "apply", "rotation", "from_qtransform"):
        assert getattr(context, name) is getattr(app_affine, name), name
    assert context.IDENTITY == app_affine.IDENTITY


def test_host_when_imported_then_paint_context_and_constants_are_the_app_objects():
    from fontlab_glyport.plugins import host

    assert host.PaintContext is app_painters.PaintContext, "isinstance must hold"
    for name in ("BEFORE_NATIVE_LAYER", "AFTER_NATIVE_LAYER", "LAYER_FILTERS"):
        assert getattr(host, name) == getattr(app_painters, name), name


def test_editor_when_imported_then_it_subclasses_the_app_registry():
    from fontlab_glyport.drawing.editor import EditorPainters

    assert issubclass(EditorPainters, app_painters.EditorPainters)


def test_editor_when_before_native_layer_then_unsupported_capability():
    from fontlab_glyport.drawing.editor import EditorPainters

    painters = EditorPainters(object(), object(), error_sink=lambda *a: None)
    with pytest.raises(UnsupportedCapability) as caught:
        painters.register("before_native_layer", lambda context: None)
    assert caught.value.capability == "FontLab.painter.before_native_layer"
    assert not painters.painters, "refusal must not register"


def test_editor_when_layer_resolver_given_then_it_is_kept():
    from fontlab_glyport.drawing.editor import EditorPainters

    resolver = lambda info: info
    painters = EditorPainters(
        object(), object(), error_sink=lambda *a: None, layer_resolver=resolver
    )
    assert painters.layer_resolver is resolver


def test_editor_source_when_counted_then_at_most_40_lines():
    lines = (SRC / "drawing" / "editor.py").read_text().splitlines()
    assert len(lines) <= 40, len(lines)


def test_ui_qtsafe_when_imported_then_module_is_gone():
    assert not (SRC / "ui" / "qtsafe.py").exists()
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fontlab_glyport.ui.qtsafe")


def test_src_when_searched_then_no_ui_qtsafe_reference():
    hits = [
        str(path)
        for path in SRC.rglob("*.py")
        for text in (path.read_text(),)  # read each file once
        if any(name in text for name in ("ui.qtsafe", "from .qtsafe"))
    ]
    assert hits == [], hits


def test_main_window_when_fontlab_has_no_window_then_host_unavailable():
    from fontlab_glyport.plugins.fontlab_host import FontLabPluginHost

    host = FontLabPluginHost.__new__(FontLabPluginHost)
    host._main = None
    host.fl = SimpleNamespace(MainWindow=lambda: None)
    gui = SimpleNamespace(QApplication=SimpleNamespace(topLevelWidgets=list))
    host.qt = SimpleNamespace(QtGui=gui)
    with pytest.raises(HostUnavailable, match="main window not found"):
        host.main_window()


def test_main_window_when_fontlab_has_one_then_it_is_cached():
    from fontlab_glyport.plugins.fontlab_host import FontLabPluginHost

    window = object()
    host = FontLabPluginHost.__new__(FontLabPluginHost)
    host._main = None
    host.fl = SimpleNamespace(MainWindow=lambda: window)
    host.qt = None
    assert host.main_window() is window and host._main is window


def test_glyport_when_cold_imported_then_no_native_bindings_loaded():
    root = str(SRC.parent)
    script = """
import importlib.abc, sys
class HostFree(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'PythonQt', 'fontlab', 'fontgate', 'FL', 'fontpr'}:
            raise AssertionError('Unexpected host import: ' + fullname)
sys.meta_path.insert(0, HostFree())
sys.path.insert(0, sys.argv[1])
import fontlab_glyport.drawing.context, fontlab_glyport.drawing.editor
import fontlab_glyport.plugins.host
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, root],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --- issue 122 T7: App owned_menus and qt_dialogs ---------------------------------


def test_main_window_when_app_refuses_off_gui_thread_then_refusal_propagates():
    """Only the "no main window" case becomes HostUnavailable (T6 review)."""
    import threading

    from fontlab_glyport.plugins.fontlab_host import FontLabPluginHost

    host = FontLabPluginHost.__new__(FontLabPluginHost)
    host._main = None
    host.fl = SimpleNamespace(MainWindow=lambda: None)
    host.qt = SimpleNamespace(
        QtGui=SimpleNamespace(
            QApplication=SimpleNamespace(topLevelWidgets=list)
        )
    )
    caught: list[BaseException] = []

    def run() -> None:
        try:
            host.main_window()
        except BaseException as error:  # noqa: BLE001 - recorded for the assert
            caught.append(error)

    worker = threading.Thread(target=run)
    worker.start()
    worker.join()
    assert len(caught) == 1 and type(caught[0]) is RuntimeError, caught
    assert "GUI thread" in str(caught[0])


def test_plugin_host_when_defined_then_it_is_an_app_owned_menus():
    from fontlabapp.qt.menus import OwnedMenus

    from fontlab_glyport.plugins.fontlab_host import FontLabPluginHost

    assert issubclass(FontLabPluginHost, OwnedMenus)
    local = vars(FontLabPluginHost)
    for name in ("_slot", "_defer", "_reap", "_guarded", "_token", "close", "_menubar"):
        assert name not in local, f"{name} must come from App OwnedMenus"


def test_fontlab_host_source_when_read_then_no_local_tool_window_class():
    from fontlab_glyport.plugins import fontlab_host

    assert not hasattr(fontlab_host, "_tool_window_class")


def test_name_filters_when_imported_then_glyport_uses_the_app_function():
    import fontlabapp.qt.dialogs as app_dialogs

    from fontlab_glyport.glyphsapp import fontlab_dialogs
    from fontlab_glyport.ui import dialogs

    assert fontlab_dialogs.name_filters is app_dialogs.name_filters
    assert dialogs.name_filters is app_dialogs.name_filters


@pytest.mark.parametrize("path", ["apply", "cancel", "title_bar", "token"])
def test_dialog_when_session_ends_then_buttons_disconnect_before_close_and_delete(path):
    """Disconnect-before-deleteLater (AGENTS.md) holds on every exit path."""
    from host_doubles import LOG, MainWindow, QWidget, make_host_qt

    from fontlab_glyport.plugins.fontlab_host import FontLabPluginHost

    host = FontLabPluginHost(
        make_host_qt(), object(), error_sink=lambda e, s: None, main_window=MainWindow()
    )
    view = QWidget()
    token = host.run_dialog(view, "Grow", "Apply", lambda applied: None)
    window = view.parent
    buttons = {b.text: b for b in window.children if hasattr(b, "clicked")}
    original_close = window.close

    def logged_close():
        LOG.append(("close", window))
        return original_close()

    window.close = logged_close
    if path == "apply":
        buttons["Apply"].click()
    elif path == "cancel":
        buttons["Cancel"].click()
    elif path == "title_bar":
        original_close()
    else:
        host.remove(token)
    LOG.clear()
    host._reaper.fire()
    kinds = [entry[0] for entry in LOG]
    assert kinds.count("disconnect") == 2, LOG
    last_disconnect = max(i for i, k in enumerate(kinds) if k == "disconnect")
    first_close = kinds.index("close")
    first_delete = kinds.index("deleteLater")
    assert last_disconnect < first_close < first_delete, LOG
