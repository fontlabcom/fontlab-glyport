# this_file: tests/test_ui_nib_box.py
"""NSBox from XIB/NIB (R031 corpus). Fixture: self-authored ``Box.xib`` and its
ibtool NIB. A box is a QGroupBox; its content view keeps Interface Builder's
frame (ibtool lays a titled box's content out again, so the NIB frames of the
titled box's content differ from the XIB's)."""

from pathlib import Path

import pytest
from test_ui_nib import _canonical
from ui_doubles import make_qt
from ui_doubles_controls import QGroupBox

from fontlab_glyport.ui.cocoa import NSMakeRect, NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.graph import UIGraph
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "Box.xib", FIXTURES / "Box.nib"
OUTLETS = ("dialog", "group", "line", "plain", "inner")


class FlatGroupBox(QGroupBox):
    __slots__ = ("flat",)

    def __init__(self):
        super().__init__()
        self.flat = False

    def setFlat(self, flat):
        self.flat = flat


def _without_titled_box_frames(graph):
    """Drop the frames ibtool recomputes: the titled box's content subtree."""
    data = graph.to_json()
    parents = {n["node_id"]: n.get("parent_id") for n in data["nodes"]}
    titled = {
        n["node_id"] for n in data["nodes"] if n["properties"].get("title") == "Options"
    }

    def inside(node_id):
        parent = parents.get(node_id)
        return parent is not None and (parent in titled or inside(parent))

    for node in data["nodes"]:
        if inside(node["node_id"]):
            node["properties"].pop("frame", None)
    return _canonical(UIGraph.from_json(data))


def _load(source):
    objc = make_objc_module({})
    owner_class = type(
        "BoxOwner", (NSObject,), {name: objc.IBOutlet() for name in OUTLETS}
    )
    qt = make_qt()
    qt.QtGui.QGroupBox = FlatGroupBox
    kit, owner = make_appkit_classes(qt, error_sink=print), owner_class.alloc().init()
    instance = instantiate(load_graph(source), owner, kit)
    return kit, owner, instance


def test_box_when_xib_and_nib_then_equal_graphs_up_to_ibtool_layout():
    xib, nib = graph_from_xib(XIB), graph_from_nib(NIB)
    assert _without_titled_box_frames(nib) == _without_titled_box_frames(xib)
    boxes = {
        n["source_id"]: n["properties"]
        for n in xib.to_json()["nodes"]
        if n["source_class"] == "NSBox"
    }
    assert (boxes["grp"]["title"], boxes["grp"]["boxType"]) == ("Options", 0)
    assert boxes["sep"]["boxType"] == 2 and boxes["sep"]["title"] == ""
    assert boxes["cst"]["titlePosition"] == 0 and boxes["cst"]["borderType"] == 1


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_boxes_then_group_boxes_with_content_views(source):
    kit, owner, instance = _load(source)
    assert all(getattr(owner, name) is not None for name in OUTLETS)
    group = owner.group
    assert isinstance(group, kit["NSBox"]) and group.title() == "Options"
    assert group._qt.title == "Options"
    assert owner.inner.superview() is group.contentView()
    assert group.contentView().superview() is group
    assert owner.line.boxType() == 2 and owner.line.contentView() is None
    assert owner.line._qt.title == "" and owner.line._qt.flat
    assert owner.plain._qt.title == "" and not owner.plain._qt.flat
    assert instance.diagnostics == []
    kit["close"]()


def test_box_when_built_in_code_then_title_and_content_view_apply():
    qt = make_qt()
    qt.QtGui.QGroupBox = FlatGroupBox
    kit = make_appkit_classes(qt, error_sink=print)
    box = kit["NSBox"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 60))
    content = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 90, 40))
    box.setContentView_(content)
    box.setTitle_("Hello")
    assert box.contentView() is content and box._qt.title == "Hello"
    box.setTitlePosition_(0)
    assert box._qt.title == "" and box.title() == "Hello"
    box.setTransparent_(True)
    assert box._qt.flat
    other = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
    box.setContentView_(other)
    assert content.superview() is None and other.superview() is box
    kit["close"]()
