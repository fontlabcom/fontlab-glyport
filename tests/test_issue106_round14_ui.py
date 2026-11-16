# this_file: tests/test_issue106_round14_ui.py
"""Round-four imports and UI calls, tested without FontLab or Cocoa."""

import plistlib

from ui_doubles_session import make_session


def test_plist_dictionary_and_export_segment_constants(tmp_path):
    path = tmp_path / "Info.plist"
    path.write_bytes(plistlib.dumps({"CFBundleVersion": "123"}))
    ctx, _ = make_session(tmp_path)
    with ctx:
        foundation = ctx.import_module("Foundation")
        kit = ctx.import_module("AppKit")
        ga = ctx.import_module("GlyphsApp")
        info = foundation.NSDictionary.dictionaryWithContentsOfFile_(str(path))
        assert info["CFBundleVersion"] == "123"
        assert info.objectForKey_("absent") is None
        assert (
            foundation.NSDictionary.dictionaryWithContentsOfFile_(str(path) + "missing")
            is None
        )
        assert (ga.OTF, ga.SEGMENT) == ("OTF", 19)
        assert kit.NSImageColorSyncProfileData == "NSImageColorSyncProfileData"
    ctx.close()


def test_edit_text_constructor_accepts_none(tmp_path):
    ctx, _ = make_session(tmp_path)
    with ctx:
        vanilla = ctx.import_module("vanilla")
        field = vanilla.EditText((0, 0, 50, 20), text=None)
        assert field.get() == ""
    ctx.close()


def test_window_became_key_binding_dispatches_on_activation(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS

    from ui_doubles import QWidget

    monkeypatch.setattr(QWidget, "changeEvent", lambda self, event: None, raising=False)
    ctx, _ = make_session(tmp_path)
    with ctx:
        vanilla = ctx.import_module("vanilla")
        window = vanilla.FloatingWindow((100, 100))
        calls = []
        window.bind("became key", calls.append)
        view = window.getNSWindow()
        window._env.qt.QtCore.QEvent = NS(WindowActivate=24, WindowDeactivate=25)
        view.changeEvent(NS(type=lambda: 24))
        assert calls == [window]
        view.changeEvent(NS(type=lambda: 25))
        assert calls == [window]
        window.close()
    ctx.close()


def test_scroll_view_embeds_and_replaces_vanilla_group(tmp_path):
    from test_ui_nib_scroll import QScrollArea

    ctx, session = make_session(tmp_path)
    session.qt.QtGui.QScrollArea = QScrollArea
    for name in ("ScrollBarAsNeeded", "ScrollBarAlwaysOff", "ScrollBarAlwaysOn"):
        setattr(session.qt.QtCore.Qt, name, name)
    with ctx:
        vanilla = ctx.import_module("vanilla")
        window = vanilla.FloatingWindow((100, 100))
        window.scroll = vanilla.ScrollView(
            (0, 0, 100, 100), None, hasVerticalScroller=True
        )
        content = vanilla.Group((0, 0, 200, 300))
        scroll = window.scroll.getNSScrollView()
        scroll.setDocumentView_(content.getNSView())
        assert scroll._qt.widget() is content.getNSView()
        assert scroll.hasVerticalScroller() and not scroll.hasHorizontalScroller()
        replacement = vanilla.Group((0, 0, 200, 400))
        scroll.setDocumentView_(replacement.getNSView())
        assert scroll._qt.widget() is replacement.getNSView()
        assert content.getNSView()._parent is None
        window.close()
    ctx.close()


def test_scroll_document_callbacks_disconnect_before_window_deletion(tmp_path):
    from test_ui_nib_scroll import QScrollArea

    ctx, session = make_session(tmp_path)
    session.qt.QtGui.QScrollArea = QScrollArea
    for name in ("ScrollBarAsNeeded", "ScrollBarAlwaysOff", "ScrollBarAlwaysOn"):
        setattr(session.qt.QtCore.Qt, name, name)
    calls = []
    with ctx:
        vanilla = ctx.import_module("vanilla")
        window = vanilla.FloatingWindow((100, 100))
        document = vanilla.Group((0, 0, 200, 300))
        document.button = vanilla.Button((0, 0, 60, 20), "Run", callback=calls.append)
        window.scroll = vanilla.ScrollView((0, 0, 100, 100))
        window.scroll.getNSScrollView().setDocumentView_(document.getNSView())
        document.button._view.clicked.emit()
        assert calls == [document.button]
        window.close()
        document.button._view.clicked.emit()
        assert calls == [document.button], (
            "callbacks disconnect before Qt deletes the document"
        )
    ctx.close()
