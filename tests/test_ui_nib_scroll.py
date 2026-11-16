# this_file: tests/test_ui_nib_scroll.py
"""NSScrollView from XIB/NIB (R031 corpus). Fixture: self-authored ``Scroll.xib``
and its ibtool NIB. The clip view's document view becomes the QScrollArea's
widget; clip views and scrollers are not built."""

from pathlib import Path

import pytest
from test_ui_nib import _canonical
from ui_doubles import LOG, QWidget, make_qt

from fontlab_glyport.ui.cocoa import NSMakeRect, NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "Scroll.xib", FIXTURES / "Scroll.nib"
OUTLETS = ("dialog", "scroller", "document", "deepButton", "both")


class QScrollArea(QWidget):
    __slots__ = ("bars", "content")

    def __init__(self):
        super().__init__()
        self.content, self.bars = None, {}

    def setWidget(self, widget):
        widget.setParent(self)
        self.content = widget

    def widget(self):
        return self.content

    def takeWidget(self):
        widget, self.content = self.content, None
        widget.setParent(None)
        return widget

    def setVerticalScrollBarPolicy(self, policy):
        self.bars["vertical"] = policy

    def setHorizontalScrollBarPolicy(self, policy):
        self.bars["horizontal"] = policy


def _kit():
    qt = make_qt()
    qt.QtGui.QScrollArea = QScrollArea
    for name in ("ScrollBarAsNeeded", "ScrollBarAlwaysOff", "ScrollBarAlwaysOn"):
        setattr(qt.QtCore.Qt, name, name)
    return make_appkit_classes(qt, error_sink=print)


def _load(source):
    objc = make_objc_module({})
    owner_class = type(
        "ScrollOwner", (NSObject,), {name: objc.IBOutlet() for name in OUTLETS}
    )
    kit, owner = _kit(), owner_class.alloc().init()
    instance = instantiate(load_graph(source), owner, kit)
    return kit, owner, instance


def test_scroll_when_xib_and_nib_then_equal_graphs_without_clip_or_scrollers():
    assert _canonical(graph_from_nib(NIB)) == _canonical(graph_from_xib(XIB))
    nodes = graph_from_xib(XIB).to_json()["nodes"]
    classes = {n["source_class"] for n in nodes}
    assert "xib:clipView" not in classes and "xib:scroller" not in classes
    first = next(n for n in nodes if n["source_id"] == "sv")["properties"]
    assert (first["hasVerticalScroller"], first["hasHorizontalScroller"]) == (
        True,
        False,
    )
    assert first["autohidesScrollers"] and "clipViewClass" not in first
    (document,) = [n for n in nodes if n["properties"].get("documentView")][:1]
    assert document["source_id"] == "doc"


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_scroll_view_then_document_in_scroll_area(source):
    kit, owner, instance = _load(source)
    assert all(getattr(owner, name) is not None for name in OUTLETS)
    scroller, document = owner.scroller, owner.document
    assert isinstance(scroller, kit["NSScrollView"])
    assert scroller.documentView() is document
    assert scroller._qt.content is document._qt
    assert owner.deepButton.superview() is document
    rect = document._qt.geometry
    assert (rect.width(), rect.height()) == (125, 300)
    assert scroller._qt.bars == {
        "vertical": "ScrollBarAsNeeded",
        "horizontal": "ScrollBarAlwaysOff",
    }
    assert owner.both._qt.bars == {
        "vertical": "ScrollBarAlwaysOn",
        "horizontal": "ScrollBarAlwaysOn",
    }
    assert instance.diagnostics == []
    kit["close"]()


def test_scroll_view_when_closed_then_document_deleted_with_the_scroll_area():
    kit, owner, _instance = _load(NIB)
    document = owner.document
    kit["close"]()
    deleted = [entry[1] for entry in LOG if entry[0] == "deleteLater"]
    assert document._qt not in deleted and document._qt._deleted


def test_scroll_view_when_document_replaced_or_resized_then_widget_follows():
    kit = _kit()
    scroll = kit["NSScrollView"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 100))
    first = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 50, 500))
    second = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 80))
    scroll.setDocumentView_(first)
    scroll.setDocumentView_(second)
    assert scroll._qt.content is second._qt and first._qt.parentWidget() is None
    second.setFrameSize_((80, 900))
    assert second._qt.geometry.height() == 900
    scroll.setHasHorizontalScroller_(False)
    assert scroll._qt.bars["horizontal"] == "ScrollBarAlwaysOff"
    kit["close"]()


def test_scroll_when_custom_clip_view_then_diagnostic():
    data = graph_from_xib(XIB).to_json()
    node = next(n for n in data["nodes"] if n["source_id"] == "sv")
    node["properties"]["clipViewClass"] = "CustomClipView"
    from fontlab_glyport.ui.graph import UIGraph

    kit = _kit()
    instance = instantiate(UIGraph.from_json(data), NSObject.alloc().init(), kit)
    assert instance.diagnostics == ["clip view class CustomClipView not used"]
    kit["close"]()
