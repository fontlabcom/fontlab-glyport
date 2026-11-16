# this_file: tests/test_vanilla_session.py
# SPDX-License-Identifier: Apache-2.0
"""The Glyport session preserves the original window ownership contract."""

import builtins
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SRC = str(Path(__file__).resolve().parents[1] / "src")


def test_session_import_is_cold_and_loads_no_qt_vanilla_or_cocoa_chain():
    from fontlab_glyport.ui.session import VanillaSession

    assert VanillaSession.__module__ == "fontlab_glyport.ui.session"
    code = """
import sys
import fontlab_glyport.ui.session
loaded = [
    name for name in sys.modules
    if name == 'PythonQt'
    or name.startswith(('fontlab_glyport.ui.vanilla', 'fontlab_glyport.ui.cocoa'))
]
assert not loaded, loaded
"""
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        timeout=15,
        env={**os.environ, "PYTHONPATH": SRC},
    )


@pytest.mark.parametrize("name", ["fontlab_glyport.ui.dialogs", "other_dependency", None])
def test_factory_import_errors_propagate_unchanged(monkeypatch, name):
    from fontlab_glyport.ui.session import VanillaSession

    original = builtins.__import__
    error = ModuleNotFoundError("missing dependency", name=name)

    def importing(module, *args, **kwargs):
        if module == "fontlab_glyport.ui.dialogs":
            raise error
        return original(module, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importing)
    with pytest.raises(ModuleNotFoundError) as caught:
        VanillaSession(qt=object())
    assert caught.value is error


def test_default_qt_uses_existing_binding_and_callback_error_propagates(monkeypatch):
    from fontlab_glyport.ui.session import VanillaSession, _raise_callback_error

    core, gui = object(), object()
    monkeypatch.setitem(
        sys.modules, "PythonQt", SimpleNamespace(QtCore=core, QtGui=gui)
    )

    def factory(qt, **kwargs):
        assert qt.QtCore is core and qt.QtGui is gui
        return SimpleNamespace()

    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.dialogs",
        SimpleNamespace(make_dialogs_module=factory),
    )
    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.vanilla",
        SimpleNamespace(make_vanilla_module=factory),
    )
    with VanillaSession() as session:
        assert session.vanilla is not None
    error = ValueError("callback failed")
    with pytest.raises(ValueError) as caught:
        _raise_callback_error(error, object())
    assert caught.value is error


def test_failed_window_disconnects_children_and_releases_native_owner(monkeypatch):
    from fontlab_glyport.ui.session import VanillaSession

    calls = []
    view = SimpleNamespace(
        _owner="retained", deleteLater=lambda: calls.append("deleted")
    )

    class Window:
        def __init__(self):
            self._view = view
            self._children = {
                "child": SimpleNamespace(
                    _disconnect=lambda: calls.append("disconnected")
                )
            }
            raise ValueError("constructor failed")

    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.dialogs",
        SimpleNamespace(make_dialogs_module=lambda *a, **k: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.vanilla",
        SimpleNamespace(
            make_vanilla_module=lambda *a, **k: SimpleNamespace(
                Window=Window, __all__=["Window"]
            )
        ),
    )
    session = VanillaSession(qt=object())
    with pytest.raises(ValueError, match="constructor failed"):
        session.vanilla.Window()
    session.close()
    assert calls == ["disconnected", "deleted"] and view._owner is None
    assert not session._windows
