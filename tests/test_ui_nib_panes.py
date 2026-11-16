# this_file: tests/test_ui_nib_panes.py
"""NSSplitView, NSGridView and NSVisualEffectView from XIB/NIB (R031 corpus).
Fixture: self-authored ``Panes.xib`` and its ibtool NIB."""

from pathlib import Path

import pytest
from test_ui_nib import _canonical
from ui_doubles import QWidget, make_qt

from fontlab_glyport.ui.cocoa import NSMakeRect, NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "Panes.xib", FIXTURES / "Panes.nib"
OUTLETS = ("dialog", "split", "leftPane", "grid", "effect", "cornerLabel")


class QSplitter(QWidget):
    __slots__ = ("_sizes", "handle", "orientation", "panes")

    def __init__(self):
        super().__init__()
        self.orientation, self.panes, self._sizes = "Horizontal", [], []
        self.handle = 5

    def setHandleWidth(self, width):
        self.handle = width

    def setOrientation(self, orientation):
        self.orientation = orientation

    def addWidget(self, widget):
        widget.setParent(self)
        self.panes.append(widget)
        self._sizes.append(0)

    def sizes(self):
        return list(self._sizes)

    def setSizes(self, sizes):
        self._sizes = [int(s) for s in sizes]


def _kit():
    qt = make_qt()
    qt.QtGui.QSplitter = QSplitter
    return make_appkit_classes(qt, error_sink=print)


def _load(source):
    objc = make_objc_module({})
    owner_class = type(
        "PanesOwner", (NSObject,), {name: objc.IBOutlet() for name in OUTLETS}
    )
    kit, owner = _kit(), owner_class.alloc().init()
    instance = instantiate(load_graph(source), owner, kit)
    return kit, owner, instance


def test_panes_when_xib_and_nib_then_equal_graphs():
    xib, nib = graph_from_xib(XIB), graph_from_nib(NIB)
    nodes = {n["source_id"]: n["properties"] for n in xib.to_json()["nodes"]}
    assert nodes["sp"]["vertical"] and nodes["sp"]["dividerStyle"] == 2
    assert (nodes["gr"]["rows"], nodes["gr"]["columns"]) == (2, 2)
    assert (nodes["gr"]["rowSpacing"], nodes["gr"]["columnSpacing"]) == (6.0, 8.0)
    assert _canonical(nib) == _canonical(xib)


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_panes_then_splitter_grid_and_effect_view(source):
    kit, owner, instance = _load(source)
    assert all(getattr(owner, name) is not None for name in OUTLETS)
    split = owner.split
    assert isinstance(split, kit["NSSplitView"]) and split.isVertical()
    assert split._qt.orientation == "Horizontal", "vertical dividers: side by side"
    assert (
        split._qt.panes[0] is owner.leftPane._qt and len(split.arrangedSubviews()) == 2
    )
    assert split._qt.sizes() == [150, 249] and split._qt.handle == 1, "thin divider"
    split.setPosition_ofDividerAtIndex_(200, 0)
    assert split._qt.sizes() == [200, 199]
    grid = owner.grid
    assert isinstance(grid, kit["NSGridView"]) and grid.numberOfRows() == 2
    assert owner.cornerLabel.superview() is grid
    assert owner.cornerLabel.stringValue() == "Four"
    assert isinstance(owner.effect, kit["NSVisualEffectView"])
    assert len(owner.effect.subviews()) == 1
    assert instance.diagnostics == []
    kit["close"]()


def test_split_view_when_built_in_code_then_orientation_and_panes():
    kit = _kit()
    split = kit["NSSplitView"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 200))
    split.setVertical_(False)
    top = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 80))
    split.addArrangedSubview_(top)
    assert split._qt.orientation == "Vertical" and split._qt.sizes() == [80]
    top.removeFromSuperview()
    assert split.arrangedSubviews() == []
    kit["close"]()
