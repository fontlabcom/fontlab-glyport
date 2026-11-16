# this_file: tests/test_ui_nib_text.py
"""NSTextView from XIB/NIB (R031 corpus). Fixture: self-authored ``Text.xib``
and its ibtool NIB: an editable plain text view with text and a delegate, and
a read-only one, each in a scroll view."""

from pathlib import Path

import pytest
from test_ui_nib import _canonical
from ui_doubles import QWidget, Signal, make_qt
from ui_doubles_table import install

from fontlab_glyport.ui.cocoa import NSMakeRect, NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.graph import UIGraph
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "Text.xib", FIXTURES / "Text.nib"


class QPlainTextEdit(QWidget):
    """PythonQt QPlainTextEdit: textChanged fires on every change, also
    programmatic ones (setPlainText, insertPlainText)."""

    __slots__ = ("_plain", "_read_only", "textChanged")

    def __init__(self):
        super().__init__()
        self._plain, self._read_only = "", False
        self.textChanged = Signal(self, "textChanged")

    def toPlainText(self):
        return self._plain

    def setPlainText(self, text):
        self._plain = text
        self.textChanged.emit()

    def insertPlainText(self, text):
        self._plain += text
        self.textChanged.emit()

    def setReadOnly(self, flag):
        self._read_only = bool(flag)

    def setTextInteractionFlags(self, flags):
        int(flags)

    def isReadOnly(self):
        return self._read_only

    def user_type(self, text):
        self.insertPlainText(text)


def _kit():
    qt = install(make_qt())
    qt.QtGui.QPlainTextEdit = QPlainTextEdit
    qt.QtCore.Qt.NoTextInteraction, qt.QtCore.Qt.TextEditorInteraction = 0, 19
    return make_appkit_classes(qt, error_sink=print)


def _load(source):
    objc = make_objc_module({})

    class TextOwner(NSObject):
        dialog = objc.IBOutlet()
        notes = objc.IBOutlet()
        log = objc.IBOutlet()

        def init(self):
            self.changes = []
            return self

        def textDidChange_(self, notification):
            self.changes.append(notification.object().string())

    kit, owner = _kit(), TextOwner.alloc().init()
    instance = instantiate(load_graph(source), owner, kit)
    return kit, owner, instance


def _frameless(graph):
    data = graph.to_json()
    for node in data["nodes"]:
        if node["source_class"] == "NSTextView":  # ibtool sizes text views again
            node["properties"].pop("frame")
    return _canonical(UIGraph.from_json(data))


def test_text_when_xib_and_nib_then_equal_graphs():
    assert _frameless(graph_from_nib(NIB)) == _frameless(graph_from_xib(XIB))
    nodes = graph_from_xib(XIB).to_json()["nodes"]
    notes = next(n for n in nodes if n["source_id"] == "tv")["properties"]
    assert notes["string"] == "Hello there" and notes["editable"]
    log = next(n for n in nodes if n["source_id"] == "tv2")["properties"]
    assert log["string"] == "" and not log["editable"] and log["selectable"]


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_text_views_then_text_editing_and_delegate(source):
    kit, owner, instance = _load(source)
    notes, log = owner.notes, owner.log
    assert isinstance(notes, kit["NSTextView"]) and notes.string() == "Hello there"
    assert notes.isEditable() and not log.isEditable() and log._qt.isReadOnly()
    assert notes.enclosingScrollView().documentView() is notes
    notes._qt.user_type("!")
    assert owner.changes == ["Hello there!"]
    notes.setString_("reset")  # programmatic: no textDidChange_
    assert owner.changes == ["Hello there!"] and notes.string() == "reset"
    log.insertText_("line 1\n")
    assert log.string() == "line 1\n" and owner.changes == ["Hello there!"]
    assert instance.diagnostics == []
    kit["close"]()
    assert notes._qt.textChanged.slots == []


def test_text_view_when_built_in_code_then_string_and_editability():
    kit = _kit()
    view = kit["NSTextView"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 40))
    view.setString_("abc")
    view.setEditable_(False)
    assert view.string() == "abc" and not view.isEditable()
    assert view.textStorage().string() == "abc" and view.textStorage().length() == 3
    view.textStorage().mutableString().setString_("xyz")
    assert view.string() == "xyz"
    view.scrollRangeToVisible_((0, 0))
    kit["close"]()
